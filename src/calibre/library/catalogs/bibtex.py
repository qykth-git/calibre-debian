#!/usr/bin/env python


__license__   = 'GPL v3'
__copyright__ = '2012, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

import codecs
import numbers
import os
import re
from collections import namedtuple

from calibre import strftime
from calibre.customize import CatalogPlugin
from calibre.customize.conversion import DummyReporter
from calibre.ebooks.metadata import format_isbn
from calibre.library.catalogs import FIELDS, TEMPLATE_ALLOWED_FIELDS
from calibre.utils.localization import _
from polyglot.builtins import string_or_bytes


class BIBTEX(CatalogPlugin):
    'BIBTEX catalog generator'

    Option = namedtuple('Option', 'option, default, dest, action, help')

    name = 'Catalog_BIBTEX'
    description = _('BIBTEX catalog generator')
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Sengian'
    version = (1, 0, 0)
    file_types = {'bib'}

    cli_options = [
            Option('--fields',
                default='all',
                dest='fields',
                action=None,
                help=_('The fields to output when cataloging books in the '
                    'database.  Should be a comma-separated list of fields.\n'
                    'Available fields: %(fields)s.\n'
                    'plus user-created custom fields.\n'
                    'Example: %(opt)s=title,authors,tags\n'
                    "Default: '%%default'\n"
                    "Applies to: BIBTEX output format")%dict(
                        fields=', '.join(FIELDS), opt='--fields')),

            Option('--sort-by',
                default='id',
                dest='sort_by',
                action=None,
                help=_('Output field to sort on.\n'
                'Available fields: author_sort, id, rating, size, timestamp, title.\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format")),

            Option('--create-citation',
                default='True',
                dest='impcit',
                action=None,
                help=_('Create a citation for BibTeX entries.\n'
                'Boolean value: True, False\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format")),

            Option('--add-files-path',
                default='True',
                dest='addfiles',
                action=None,
                help=_('Create a file entry if formats is selected for BibTeX entries.\n'
                'Boolean value: True, False\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format")),

            Option('--citation-template',
                default='{authors}{id}',
                dest='bib_cit',
                action=None,
                help=_('The template for citation creation from database fields.\n'
                    'Should be a template with {} enclosed fields.\n'
                    'Available fields: %s.\n'
                    "Default: '%%default'\n"
                    "Applies to: BIBTEX output format")%', '.join(TEMPLATE_ALLOWED_FIELDS)),

            Option('--choose-encoding',
                default='utf8',
                dest='bibfile_enc',
                action=None,
                help=_('BibTeX file encoding output.\n'
                'Available types: utf8, cp1252, ascii.\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format")),

            Option('--choose-encoding-configuration',
                default='strict',
                dest='bibfile_enctag',
                action=None,
                help=_('BibTeX file encoding flag.\n'
                'Available types: strict, replace, ignore, backslashreplace.\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format")),

            Option('--entry-type',
                default='book',
                dest='bib_entry',
                action=None,
                help=_('Entry type for BibTeX catalog.\n'
                'Available types: book, misc, mixed.\n'
                "Default: '%default'\n"
                "Applies to: BIBTEX output format"))]

    def run(self, path_to_output, opts, db, notification=DummyReporter()):
        from calibre.library.save_to_disk import preprocess_template
        from calibre.utils.bibtex import BibTeX
        from calibre.utils.date import isoformat
        from calibre.utils.filenames import ascii_text
        from calibre.utils.html2text import html2text
        from calibre.utils.logging import default_log as log

        library_name = os.path.basename(db.library_path)

        def create_bibtex_entry(entry, fields, mode, template_citation,
                                    bibtexdict, db, citation_bibtex=True, calibre_files=True):

            # Bibtex doesn't like UTF-8 but keep unicode until writing
            # Define starting chain or if book valid strict and not book return a Fail string

            bibtex_entry = []
            if mode != 'misc' and check_entry_book_valid(entry):
                bibtex_entry.append('@book{')
            elif mode != 'book':
                bibtex_entry.append('@misc{')
            else:
                # case strict book
                return ''

            if citation_bibtex:
                # Citation tag
                bibtex_entry.append(make_bibtex_citation(entry, template_citation,
                    bibtexdict))
                bibtex_entry = [' '.join(bibtex_entry)]

            for field in fields:
                if field.startswith('#'):
                    item = db.get_field(entry['id'], field, index_is_id=True)
                    m = db.new_api.field_metadata[field]
                    if isinstance(item, (bool, numbers.Number)):
                        item = repr(item)
                    elif m.get('is_multiple'):
                        item = m['is_multiple']['list_to_ui'].join(filter(None, item))
                elif field == 'title_sort':
                    item = entry['sort']
                elif field == 'library_name':
                    item = library_name
                else:
                    item = entry[field]

                # check if the field should be included (none or empty)
                if item is None:
                    continue
                try:
                    if len(item) == 0:
                        continue
                except TypeError:
                    pass

                if field == 'authors':
                    bibtex_entry.append(f'author = "{bibtexdict.bibtex_author_format(item)}"')

                elif field == 'id':
                    bibtex_entry.append(f'calibreid = "{int(item)}"')

                elif field == 'rating':
                    bibtex_entry.append(f'rating = "{int(item)}"')

                elif field == 'size':
                    bibtex_entry.append(f'{field} = "{int(item)} octets"')

                elif field == 'tags':
                    # A list to flatten
                    bibtex_entry.append('tags = "{}"'.format(bibtexdict.utf8ToBibtex(', '.join(item))))

                elif field == 'comments':
                    # \n removal
                    item = item.replace('\r\n', ' ')
                    item = item.replace('\n', ' ')
                    # unmatched brace removal (users should use \leftbrace or \rightbrace for single braces)
                    item = bibtexdict.stripUnmatchedSyntax(item, '{', '}')
                    # html to text
                    try:
                        item = html2text(item)
                    except Exception:
                        log.warn('Failed to convert comments to text')
                    bibtex_entry.append(f'note = "{bibtexdict.utf8ToBibtex(item)}"')

                elif field == 'isbn':
                    # Could be 9, 10 or 13 digits
                    bibtex_entry.append(f'isbn = "{format_isbn(item)}"')

                elif field == 'formats':
                    # Add file path if format is selected
                    formats = [format.rpartition('.')[2].lower() for format in item]
                    bibtex_entry.append('formats = "{}"'.format(', '.join(formats)))
                    if calibre_files:
                        files = [':{}:{}'.format(format, format.rpartition('.')[2].upper())
                            for format in item]
                        bibtex_entry.append('file = "{}"'.format(', '.join(files)))

                elif field == 'series_index':
                    bibtex_entry.append(f'volume = "{int(item)}"')

                elif field == 'timestamp':
                    bibtex_entry.append('timestamp = "{}"'.format(isoformat(item).partition('T')[0]))

                elif field == 'pubdate':
                    bibtex_entry.append(f'year = "{item.year}"')
                    bibtex_entry.append('month = "{}"'.format(bibtexdict.utf8ToBibtex(strftime('%b', item))))

                elif field.startswith('#') and isinstance(item, string_or_bytes):
                    bibtex_entry.append(f'custom_{field[1:]} = "{bibtexdict.utf8ToBibtex(item)}"')

                elif isinstance(item, string_or_bytes):
                    # elif field in ['title', 'publisher', 'cover', 'uuid', 'ondevice',
                    # 'author_sort', 'series', 'title_sort'] :
                    bibtex_entry.append(f'{field} = "{bibtexdict.utf8ToBibtex(item)}"')

            bibtex_entry = ',\n    '.join(bibtex_entry)
            bibtex_entry += ' }\n\n'

            return bibtex_entry

        def check_entry_book_valid(entry):
            # Check that the required fields are ok for a book entry
            for field in ['title', 'authors', 'publisher']:
                if entry[field] is None or len(entry[field]) == 0:
                    return False
            if entry['pubdate'] is None:
                return False
            else:
                return True

        def make_bibtex_citation(entry, template_citation, bibtexclass):

            # define a function to replace the template entry by its value
            def tpl_replace(objtplname):

                tpl_field = re.sub(r'[\{\}]', '', objtplname.group())

                if tpl_field in TEMPLATE_ALLOWED_FIELDS:
                    if tpl_field in ['pubdate', 'timestamp']:
                        tpl_field = isoformat(entry[tpl_field]).partition('T')[0]
                    elif tpl_field in ['tags', 'authors']:
                        tpl_field = entry[tpl_field][0]
                    elif tpl_field in ['id', 'series_index']:
                        tpl_field = str(entry[tpl_field])
                    else:
                        tpl_field = entry[tpl_field]
                    return ascii_text(tpl_field)
                else:
                    return ''

            if len(template_citation) >0:
                tpl_citation = bibtexclass.utf8ToBibtex(
                    bibtexclass.ValidateCitationKey(re.sub(r'\{[^{}]*\}',
                        tpl_replace, template_citation)))

                if len(tpl_citation) >0:
                    return tpl_citation

            if len(entry['isbn']) > 0:
                template_citation = '{}'.format(re.sub(r'[\D]','', entry['isbn']))

            else:
                template_citation = '{}'.format(str(entry['id']))

            return bibtexclass.ValidateCitationKey(template_citation)

        self.fmt = path_to_output.rpartition('.')[2]
        self.notification = notification

        # Combobox options
        bibfile_enc = ['utf8', 'cp1252', 'ascii']
        bibfile_enctag = ['strict', 'replace', 'ignore', 'backslashreplace']
        bib_entry = ['mixed', 'misc', 'book']

        # Needed because CLI return str vs int by widget
        try:
            bibfile_enc = bibfile_enc[opts.bibfile_enc]
            bibfile_enctag = bibfile_enctag[opts.bibfile_enctag]
            bib_entry = bib_entry[opts.bib_entry]
        except Exception:
            if opts.bibfile_enc in bibfile_enc:
                bibfile_enc = opts.bibfile_enc
            else:
                log.warn('Incorrect --choose-encoding flag, revert to default')
                bibfile_enc = bibfile_enc[0]
            if opts.bibfile_enctag in bibfile_enctag:
                bibfile_enctag = opts.bibfile_enctag
            else:
                log.warn('Incorrect --choose-encoding-configuration flag, revert to default')
                bibfile_enctag = bibfile_enctag[0]
            if opts.bib_entry in bib_entry:
                bib_entry = opts.bib_entry
            else:
                log.warn('Incorrect --entry-type flag, revert to default')
                bib_entry = bib_entry[0]

        if opts.verbose:
            opts_dict = vars(opts)
            log(f'{self.name}(): Generating {self.fmt}')
            if opts.connected_device['is_device_connected']:
                log(' connected_device: {}'.format(opts.connected_device['name']))
            if opts_dict['search_text']:
                log(" --search='{}'".format(opts_dict['search_text']))

            if opts_dict['ids']:
                log(' Book count: {}'.format(len(opts_dict['ids'])))
                if opts_dict['search_text']:
                    log(' (--search ignored when a subset of the database is specified)')

            if opts_dict['fields']:
                if opts_dict['fields'] == 'all':
                    log(' Fields: {}'.format(', '.join(FIELDS[1:])))
                else:
                    log(' Fields: {}'.format(opts_dict['fields']))

            log(f' Output file will be encoded in {bibfile_enc} with {bibfile_enctag} flag')

            log(" BibTeX entry type is {} with a citation like '{}' flag".format(bib_entry, opts_dict['bib_cit']))

        # If a list of ids are provided, don't use search_text
        if opts.ids:
            opts.search_text = None

        data = self.search_sort_db(db, opts)

        if not len(data):
            log.error(f"\nNo matching database entries for search criteria '{opts.search_text}'")

        # Get the requested output fields as a list
        fields = self.get_output_fields(db, opts)

        if not len(data):
            log.error(f"\nNo matching database entries for search criteria '{opts.search_text}'")

        # Initialize BibTeX class
        bibtexc = BibTeX()

        # Entries writing after Bibtex formatting (or not)
        if bibfile_enc != 'ascii':
            bibtexc.ascii_bibtex = False
        else:
            bibtexc.ascii_bibtex = True

        # Check citation choice and go to default in case of bad CLI
        if isinstance(opts.impcit, string_or_bytes):
            if opts.impcit == 'False':
                citation_bibtex= False
            elif opts.impcit == 'True':
                citation_bibtex= True
            else:
                log.warn('Incorrect --create-citation, revert to default')
                citation_bibtex= True
        else:
            citation_bibtex= opts.impcit

        # Check add file entry and go to default in case of bad CLI
        if isinstance(opts.addfiles, string_or_bytes):
            if opts.addfiles == 'False':
                addfiles_bibtex = False
            elif opts.addfiles == 'True':
                addfiles_bibtex = True
            else:
                log.warn('Incorrect --add-files-path, revert to default')
                addfiles_bibtex= True
        else:
            addfiles_bibtex = opts.addfiles

        # Preprocess for error and light correction
        template_citation = preprocess_template(opts.bib_cit)

        # Open output and write entries
        with codecs.open(path_to_output, 'w', bibfile_enc, bibfile_enctag)\
            as outfile:
            # File header
            nb_entries = len(data)

            # check in book strict if all is ok else throw a warning into log
            if bib_entry == 'book':
                nb_books = len(list(filter(check_entry_book_valid, data)))
                if nb_books < nb_entries:
                    log.warn(f'Only {nb_books} entries in {nb_entries} are book compatible')
                    nb_entries = nb_books

            # If connected device, add 'On Device' values to data
            if opts.connected_device['is_device_connected'] and 'ondevice' in fields:
                for entry in data:
                    entry['ondevice'] = db.catalog_plugin_on_device_temp_mapping[entry['id']]['ondevice']

            # outfile.write('%%%Calibre catalog\n%%%{0} entries in catalog\n\n'.format(nb_entries))
            outfile.write('@preamble{"This catalog of %d entries was generated by calibre on %s"}\n\n'  # noqa: UP031
                % (nb_entries, strftime('%A, %d. %B %Y %H:%M')))

            for entry in data:
                outfile.write(create_bibtex_entry(entry, fields, bib_entry, template_citation,
                    bibtexc, db, citation_bibtex, addfiles_bibtex))
