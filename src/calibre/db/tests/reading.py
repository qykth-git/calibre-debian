#!/usr/bin/env python


__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

import datetime
import os
from io import BytesIO
from time import time

from calibre.db.tests.base import BaseTest
from calibre.utils.date import utc_tz
from calibre.utils.localization import calibre_langcode_to_name
from polyglot.builtins import iteritems, itervalues


def p(x):
    return datetime.datetime.strptime(x, '%Y-%m-%d').replace(tzinfo=utc_tz)


class ReadingTest(BaseTest):

    def test_read(self):  # {{{
        'Test the reading of data from the database'
        cache = self.init_cache(self.library_path)
        tests = {
                3: {
                    'title': 'Unknown',
                    'sort': 'Unknown',
                    'authors': ('Unknown',),
                    'author_sort': 'Unknown',
                    'series': None,
                    'series_index': 1.0,
                    'rating': None,
                    'tags': (),
                    'formats':(),
                    'identifiers': {},
                    'timestamp': datetime.datetime(2011, 9, 7, 19, 54, 41,
                        tzinfo=utc_tz),
                    'pubdate': datetime.datetime(2011, 9, 7, 19, 54, 41,
                        tzinfo=utc_tz),
                    'last_modified': datetime.datetime(2011, 9, 7, 19, 54, 41,
                        tzinfo=utc_tz),
                    'publisher': None,
                    'languages': (),
                    'comments': None,
                    '#enum': None,
                    '#authors':(),
                    '#date':None,
                    '#rating':None,
                    '#series':None,
                    '#series_index': None,
                    '#tags':(),
                    '#yesno':None,
                    '#comments': None,
                    'size':None,
                },

                2: {
                    'title': 'Title One',
                    'sort': 'One',
                    'authors': ('Author One',),
                    'author_sort': 'One, Author',
                    'series': 'A Series One',
                    'series_index': 1.0,
                    'tags':('Tag One', 'Tag Two'),
                    'formats': ('FMT1',),
                    'rating': 4.0,
                    'identifiers': {'test':'one'},
                    'timestamp': datetime.datetime(2011, 9, 5, 21, 6,
                        tzinfo=utc_tz),
                    'pubdate': datetime.datetime(2011, 9, 5, 21, 6,
                        tzinfo=utc_tz),
                    'publisher': 'Publisher One',
                    'languages': ('eng',),
                    'comments': '<p>Comments One</p>',
                    '#enum':'One',
                    '#authors':('Custom One', 'Custom Two'),
                    '#date':datetime.datetime(2011, 9, 5, 6, 0,
                        tzinfo=utc_tz),
                    '#rating':2.0,
                    '#series':'My Series One',
                    '#series_index': 1.0,
                    '#tags':('My Tag One', 'My Tag Two'),
                    '#yesno':True,
                    '#comments': '<div>My Comments One<p></p></div>',
                    'size':9,
                },
                1: {
                    'title': 'Title Two',
                    'sort': 'Title Two',
                    'authors': ('Author Two', 'Author One'),
                    'author_sort': 'Two, Author & One, Author',
                    'series': 'A Series One',
                    'series_index': 2.0,
                    'rating': 6.0,
                    'tags': ('Tag One', 'News'),
                    'formats':('FMT1', 'FMT2'),
                    'identifiers': {'test':'two'},
                    'timestamp': datetime.datetime(2011, 9, 6, 6, 0,
                        tzinfo=utc_tz),
                    'pubdate': datetime.datetime(2011, 8, 5, 6, 0,
                        tzinfo=utc_tz),
                    'publisher': 'Publisher Two',
                    'languages': ('deu',),
                    'comments': '<p>Comments Two</p>',
                    '#enum':'Two',
                    '#authors':('My Author Two',),
                    '#date':datetime.datetime(2011, 9, 1, 6, 0,
                        tzinfo=utc_tz),
                    '#rating':4.0,
                    '#series':'My Series Two',
                    '#series_index': 3.0,
                    '#tags':('My Tag Two',),
                    '#yesno':False,
                    '#comments': '<div>My Comments Two<p></p></div>',
                    'size':9,

                },
        }
        for book_id, test in iteritems(tests):
            for field, expected_val in iteritems(test):
                val = cache.field_for(field, book_id)
                if isinstance(val, tuple) and 'authors' not in field and 'languages' not in field:
                    val, expected_val = set(val), set(expected_val)
                self.assertEqual(expected_val, val,
                        f'Book id: {book_id} Field: {field} failed: {expected_val!r} != {val!r}')
        # }}}

    def test_sorting(self):  # {{{
        'Test sorting'
        cache = self.init_cache()
        ae = self.assertEqual

        lmap = {x:cache.field_for('languages', x) for x in (1, 2, 3)}
        lq = sorted(lmap, key=lambda x: calibre_langcode_to_name((lmap[x] or ('',))[0]))
        for field, order in iteritems({
            'title'  : [2, 1, 3],
            'authors': [2, 1, 3],
            'series' : [3, 1, 2],
            'tags'   : [3, 1, 2],
            'rating' : [3, 2, 1],
            # 'identifiers': [3, 2, 1], There is no stable sort since 1 and
            # 2 have the same identifier keys
            # 'last_modified': [3, 2, 1], There is no stable sort as two
            # records have the exact same value
            'timestamp': [2, 1, 3],
            'pubdate'  : [1, 2, 3],
            'publisher': [3, 2, 1],
            'languages': lq,
            'comments': [3, 2, 1],
            '#enum' : [3, 2, 1],
            '#authors' : [3, 2, 1],
            '#date': [3, 1, 2],
            '#rating':[3, 2, 1],
            '#series':[3, 2, 1],
            '#tags':[3, 2, 1],
            '#yesno':[2, 1, 3],
            '#comments':[3, 2, 1],
            'id': [1, 2, 3],
        }):
            x = list(reversed(order))
            ae(order, cache.multisort([(field, True)],
                ids_to_sort=x),
                    f'Ascending sort of {field} failed')
            ae(x, cache.multisort([(field, False)],
                ids_to_sort=order),
                    f'Descending sort of {field} failed')

        # Test sorting of is_multiple fields.

        # Author like fields should be sorted by generating sort names from the
        # actual values in entry order
        for field in ('authors', '#authors'):
            ae(
                cache.set_field(field, {1:('aa bb', 'bb cc', 'cc dd'), 2:('bb aa', 'xx yy'), 3: ('aa bb', 'bb aa')}), {1, 2, 3})
            ae([2, 3, 1], cache.multisort([(field, True)], ids_to_sort=(1, 2, 3)))
            ae([1, 3, 2], cache.multisort([(field, False)], ids_to_sort=(1, 2, 3)))

        # All other is_multiple fields should be sorted by sorting the values
        # for each book and using that as the sort key
        for field in ('tags', '#tags'):
            ae(
                cache.set_field(field, {1:('b', 'a'), 2:('c', 'y'), 3: ('b', 'z')}), {1, 2, 3})
            ae([1, 3, 2], cache.multisort([(field, True)], ids_to_sort=(1, 2, 3)))
            ae([2, 3, 1], cache.multisort([(field, False)], ids_to_sort=(1, 2, 3)))

        # Test tweak to sort dates by visible format
        from calibre.utils.config_base import Tweak
        ae(cache.set_field('pubdate', {1:p('2001-3-3'), 2:p('2002-2-3'), 3:p('2003-1-3')}), {1, 2, 3})
        ae([1, 2, 3], cache.multisort([('pubdate', True)]))
        with Tweak('gui_pubdate_display_format', 'MMM'), Tweak('sort_dates_using_visible_fields', True):
            c2 = self.init_cache()
            ae([3, 2, 1], c2.multisort([('pubdate', True)]))

        # Test bool sorting when not tristate
        cache.set_pref('bools_are_tristate', False)
        c2 = self.init_cache()
        ae([2, 3, 1], c2.multisort([('#yesno', True), ('id', False)]))

        # Test subsorting
        ae([3, 2, 1], cache.multisort([('identifiers', True),
            ('title', True)]), 'Subsort failed')
        from calibre.ebooks.metadata.book.base import Metadata
        for i in range(7):
            cache.create_book_entry(Metadata(f'title{i}'), apply_import_tags=False)
        cache.create_custom_column('one', 'CC1', 'int', False)
        cache.create_custom_column('two', 'CC2', 'int', False)
        cache.create_custom_column('three', 'CC3', 'int', False)
        cache.close()
        cache = self.init_cache()
        cache.set_field('#one', {(i+(5*m)):m for m in (0, 1) for i in range(1, 6)})
        cache.set_field('#two', {i+(m*3):m for m in (0, 1, 2) for i in (1, 2, 3)})
        cache.set_field('#two', {10:2})
        cache.set_field('#three', {i:i for i in range(1, 11)})
        ae(list(range(1, 11)), cache.multisort([('#one', True), ('#two', True)], ids_to_sort=sorted(cache.all_book_ids())))
        ae([4, 5, 1, 2, 3, 7, 8, 9, 10, 6], cache.multisort([('#one', True), ('#two', False)], ids_to_sort=sorted(cache.all_book_ids())))
        ae([5, 4, 3, 2, 1, 10, 9, 8, 7, 6], cache.multisort([('#one', True), ('#two', False), ('#three', False)], ids_to_sort=sorted(cache.all_book_ids())))
    # }}}

    def test_get_metadata(self):  # {{{
        'Test get_metadata() returns the same data for both backends'
        from calibre.library.database2 import LibraryDatabase2
        old = LibraryDatabase2(self.library_path)
        old_metadata = {i:old.get_metadata(
            i, index_is_id=True, get_cover=True, cover_as_data=True) for i in
                range(1, 4)}
        for mi in itervalues(old_metadata):
            mi.format_metadata = dict(mi.format_metadata)
            if mi.formats:
                mi.formats = tuple(mi.formats)
        old.conn.close()
        old = None

        cache = self.init_cache(self.library_path)

        new_metadata = {i:cache.get_metadata(
            i, get_cover=True, cover_as_data=True) for i in range(1, 4)}
        cache = None
        for mi2, mi1 in zip(list(new_metadata.values()), list(old_metadata.values())):
            self.compare_metadata(mi1, mi2)
    # }}}

    def test_serialize_metadata(self):  # {{{
        from calibre.library.field_metadata import fm_as_dict
        from calibre.utils.serialize import json_dumps, json_loads, msgpack_dumps, msgpack_loads
        cache = self.init_cache(self.library_path)
        fm = cache.field_metadata
        for d, l in ((json_dumps, json_loads), (msgpack_dumps, msgpack_loads)):
            fm2 = l(d(fm))
            self.assertEqual(fm_as_dict(fm), fm_as_dict(fm2))
        for i in range(1, 4):
            mi = cache.get_metadata(i, get_cover=True, cover_as_data=True)
            rmi = msgpack_loads(msgpack_dumps(mi))
            self.compare_metadata(mi, rmi, exclude='format_metadata has_cover formats id'.split())
            rmi = json_loads(json_dumps(mi))
            self.compare_metadata(mi, rmi, exclude='format_metadata has_cover formats id'.split())
    # }}}

    def test_get_cover(self):  # {{{
        'Test cover() returns the same data for both backends'
        from calibre.library.database2 import LibraryDatabase2
        old = LibraryDatabase2(self.library_path)
        covers = {i: old.cover(i, index_is_id=True) for i in old.all_ids()}
        old.conn.close()
        old = None
        cache = self.init_cache(self.library_path)
        for book_id, cdata in iteritems(covers):
            self.assertEqual(cdata, cache.cover(book_id), 'Reading of cover failed')
            f = cache.cover(book_id, as_file=True)
            try:
                self.assertEqual(cdata, f.read() if f else f, 'Reading of cover as file failed')
            finally:
                if f:
                    f.close()
            if cdata:
                with open(cache.cover(book_id, as_path=True), 'rb') as f:
                    self.assertEqual(cdata, f.read(), 'Reading of cover as path failed')
            else:
                self.assertEqual(cdata, cache.cover(book_id, as_path=True),
                                 'Reading of null cover as path failed')
        buf = BytesIO()
        self.assertFalse(cache.copy_cover_to(99999, buf), 'copy_cover_to() did not return False for non-existent book_id')
        self.assertFalse(cache.copy_cover_to(3, buf), 'copy_cover_to() did not return False for non-existent cover')

    # }}}

    def test_searching(self):  # {{{
        'Test searching returns the same data for both backends'
        from calibre.library.database2 import LibraryDatabase2
        old = LibraryDatabase2(self.library_path)
        oldvals = {query:set(old.search_getting_ids(query, '')) for query in (
            # Date tests
            # 'date:9/6/2011',
            'date:true', 'date:false', 'pubdate:1/9/2011',
            '#date:true', 'date:<100_daysago', 'date:>9/6/2011',
            '#date:>9/1/2011', '#date:=2011',

            # Number tests
            'rating:3', 'rating:>2', 'rating:=2', 'rating:true',
            'rating:false', 'rating:>4', 'tags:#<2', 'tags:#>7',
            'cover:false', 'cover:true', '#float:>11', '#float:<1k',
            '#float:10.01', '#float:false', 'series_index:1',
            'series_index:<3',

            # Bool tests
            '#yesno:true', '#yesno:false', '#yesno:_yes', '#yesno:_no',
            '#yesno:_empty',

            # Keypair tests
            'identifiers:true', 'identifiers:false', 'identifiers:test',
            'identifiers:test:false', 'identifiers:test:one',
            'identifiers:t:n', 'identifiers:=test:=two', 'identifiers:x:y',
            'identifiers:z',

            # Text tests
            'title:="Title One"', 'title:~title', '#enum:=one', '#enum:tw',
            '#enum:false', '#enum:true', 'series:one', 'tags:one', 'tags:true',
            'tags:false', 'uuid:2', 'one', '20.02', '"publisher one"',
            '"my comments one"', 'series_sort:one',

            # User categories
            '@Good Authors:One', '@Good Series.good tags:two',

            # Cover/Formats
            'cover:true', 'cover:false', 'formats:true', 'formats:false',
            'formats:#>1', 'formats:#=1', 'formats:=fmt1', 'formats:=fmt2',
            'formats:=fmt1 or formats:fmt2', '#formats:true', '#formats:false',
            '#formats:fmt1', '#formats:fmt2', '#formats:fmt1 and #formats:fmt2',
        )}
        old.conn.close()
        old = None

        cache = self.init_cache(self.cloned_library)
        for query, ans in iteritems(oldvals):
            nr = cache.search(query, '')
            self.assertEqual(ans, nr,
                f'Old result: {ans!r} != New result: {nr!r} for search: {query}')

        # Test searching by id, which was introduced in the new backend
        self.assertEqual(cache.search('id:1', ''), {1})
        self.assertEqual(cache.search('id:>1', ''), {2, 3})

        # Numeric/rating searches with relops in the old db were incorrect, so
        # test them specifically here
        cache.set_field('rating', {1:4, 2:2, 3:5})
        self.assertEqual(cache.search('rating:>2'), set())
        self.assertEqual(cache.search('rating:>=2'), {1, 3})
        self.assertEqual(cache.search('rating:<2'), {2})
        self.assertEqual(cache.search('rating:<=2'), {1, 2, 3})
        self.assertEqual(cache.search('rating:<=2'), {1, 2, 3})
        self.assertEqual(cache.search('rating:=2'), {1, 3})
        self.assertEqual(cache.search('rating:2'), {1, 3})
        self.assertEqual(cache.search('rating:!=2'), {2})

        cache.field_metadata.all_metadata()['#rating']['display']['allow_half_stars'] = True
        cache.set_field('#rating', {1:3, 2:4, 3:9})
        self.assertEqual(cache.search('#rating:1'), set())
        self.assertEqual(cache.search('#rating:1.5'), {1})
        self.assertEqual(cache.search('#rating:>4'), {3})
        self.assertEqual(cache.search('#rating:2'), {2})

        # template searches
        # Test text search
        self.assertEqual(cache.search('template:"{#formats}#@#:t:fmt1"'), {1,2})
        self.assertEqual(cache.search('template:"{authors}#@#:t:=Author One"'), {2})
        cache.set_field('pubdate', {1:p('2001-02-06'), 2:p('2001-10-06'), 3:p('2001-06-06')})
        cache.set_field('timestamp', {1:p('2002-02-06'), 2:p('2000-10-06'), 3:p('2001-06-06')})
        # Test numeric compare search
        self.assertEqual(cache.search("template:\"program: "
                                      "floor(days_between(field('pubdate'), "
                                      "field('timestamp')))#@#:n:>0\""), {2,3})
        # Test date search
        self.assertEqual(cache.search('template:{pubdate}#@#:d:<2001-09-01"'), {1,3})
        # Test boolean search
        self.assertEqual(cache.search('template:{series}#@#:b:true'), {1,2})
        self.assertEqual(cache.search('template:{series}#@#:b:false'), {3})

        # test primary search
        cache.set_field('title', {1: 'Gravity’s Raiñbow'})
        self.assertEqual(cache.search('title:"Gravity\'s Rainbow"'), {1})
        # Note that the old db searched uuid for un-prefixed searches, the new
        # db does not, for performance

    # }}}

    def test_get_categories(self):  # {{{
        'Check that get_categories() returns the same data for both backends'
        from calibre.library.database2 import LibraryDatabase2
        old = LibraryDatabase2(self.library_path)
        old_categories = old.get_categories()
        old.conn.close()
        cache = self.init_cache(self.library_path)
        new_categories = cache.get_categories()
        self.assertEqual(set(old_categories), set(new_categories),
            'The set of old categories is not the same as the set of new categories')

        def compare_category(category, old, new):
            for attr in ('name', 'original_name', 'id', 'count',
                         'is_hierarchical', 'is_editable', 'is_searchable',
                         'id_set', 'avg_rating', 'sort', 'use_sort_as_name',
                         'category'):
                oval, nval = getattr(old, attr), getattr(new, attr)
                if (
                    (category in {'rating', '#rating'} and attr in {'id_set', 'sort'}) or
                    (category == 'series' and attr == 'sort') or  # Sorting is wrong in old
                    (category == 'identifiers' and attr == 'id_set') or
                    (category == '@Good Series') or  # Sorting is wrong in old
                    (category == 'news' and attr in {'count', 'id_set'}) or
                    (category == 'formats' and attr == 'id_set')
                ):
                    continue
                self.assertEqual(oval, nval,
                    f'The attribute {attr} for {old.name} in category {category} does not match. Old is {oval!r}, New is {nval!r}')

        for category in old_categories:
            old, new = old_categories[category], new_categories[category]
            self.assertEqual(len(old), len(new),
                f'The number of items in the category {category} is not the same')
            for o, n in zip(old, new):
                compare_category(category, o, n)

    # }}}

    def test_get_formats(self):  # {{{
        'Test reading ebook formats using the format() method'
        from calibre.db.cache import NoSuchFormat
        from calibre.library.database2 import LibraryDatabase2
        old = LibraryDatabase2(self.library_path)
        ids = old.all_ids()
        lf = {i:set(old.formats(i, index_is_id=True).split(',')) if old.formats(
            i, index_is_id=True) else set() for i in ids}
        formats = {i:{f:old.format(i, f, index_is_id=True) for f in fmts} for
                   i, fmts in iteritems(lf)}
        old.conn.close()
        old = None
        cache = self.init_cache(self.library_path)
        for book_id, fmts in iteritems(lf):
            self.assertEqual(fmts, set(cache.formats(book_id)),
                             'Set of formats is not the same')
            for fmt in fmts:
                old = formats[book_id][fmt]
                self.assertEqual(old, cache.format(book_id, fmt),
                                 'Old and new format disagree')
                with cache.format(book_id, fmt, as_file=True) as f:
                    self.assertEqual(old, f.read(),
                                    'Failed to read format as file')
                with open(cache.format(book_id, fmt, as_path=True,
                                       preserve_filename=True), 'rb') as f:
                    self.assertEqual(old, f.read(),
                                 'Failed to read format as path')
                with open(cache.format(book_id, fmt, as_path=True), 'rb') as f:
                    self.assertEqual(old, f.read(),
                                 'Failed to read format as path')

        buf = BytesIO()
        self.assertRaises(NoSuchFormat, cache.copy_format_to, 99999, 'X', buf, 'copy_format_to() failed to raise an exception for non-existent book')
        self.assertRaises(NoSuchFormat, cache.copy_format_to, 1, 'X', buf, 'copy_format_to() failed to raise an exception for non-existent format')
        fmt = cache.formats(1)[0]
        path = cache.format_abspath(1, fmt)
        changed_path = os.path.join(os.path.dirname(path), 'x' + os.path.basename(path))
        os.rename(path, changed_path)
        self.assertEqual(cache.format_abspath(1, fmt), path)
        self.assertFalse(os.path.exists(changed_path))

    # }}}

    def test_author_sort_for_authors(self):  # {{{
        'Test getting the author sort for authors from the db'
        cache = self.init_cache()
        table = cache.fields['authors'].table
        table.set_sort_names({next(iter(table.id_map)): 'Fake Sort'}, cache.backend)

        authors = tuple(itervalues(table.id_map))
        nval = cache.author_sort_from_authors(authors)
        self.assertIn('Fake Sort', nval)

        db = self.init_old()
        self.assertEqual(db.author_sort_from_authors(authors), nval)
        db.close()
        del db

    # }}}

    def test_get_next_series_num(self):  # {{{
        'Test getting the next series number for a series'
        cache = self.init_cache()
        cache.set_field('series', {3:'test series'})
        cache.set_field('series_index', {3:13})
        table = cache.fields['series'].table
        series = tuple(itervalues(table.id_map))
        nvals = {s:cache.get_next_series_num_for(s) for s in series}
        db = self.init_old()
        self.assertEqual({s:db.get_next_series_num_for(s) for s in series}, nvals)
        db.close()

    # }}}

    def test_has_book(self):  # {{{
        'Test detecting duplicates'
        from calibre.ebooks.metadata.book.base import Metadata
        cache = self.init_cache()
        db = self.init_old()
        for title in itervalues(cache.fields['title'].table.book_col_map):
            for x in (db, cache):
                self.assertTrue(x.has_book(Metadata(title)))
                self.assertTrue(x.has_book(Metadata(title.upper())))
                self.assertFalse(x.has_book(Metadata(title + 'XXX')))
                self.assertFalse(x.has_book(Metadata(title[:1])))
        db.close()
    # }}}

    def test_datetime(self):  # {{{
        ' Test the reading of datetimes stored in the db '
        from calibre.db.tables import UNDEFINED_DATE, _c_speedup, c_parse
        from calibre.utils.date import parse_date

        # First test parsing of string to UTC time
        for raw in ('2013-07-22 15:18:29+05:30', '  2013-07-22 15:18:29+00:00', '2013-07-22 15:18:29', '2003-09-21 23:30:00-06:00'):
            self.assertTrue(_c_speedup(raw))
            ctime = c_parse(raw)
            pytime = parse_date(raw, assume_utc=True)
            self.assertEqual(ctime, pytime)

        self.assertEqual(c_parse(2003).year, 2003)
        for x in (None, '', 'abc'):
            self.assertEqual(UNDEFINED_DATE, c_parse(x))
    # }}}

    def test_restrictions(self):  # {{{
        ' Test searching with and without restrictions '
        cache = self.init_cache()
        se = self.assertSetEqual
        se(cache.all_book_ids(), cache.search(''))
        se({1, 2}, cache.search('', 'not authors:=Unknown'))
        se(set(), cache.search('authors:=Unknown', 'not authors:=Unknown'))
        se({2}, cache.search('not authors:"=Author Two"', 'not authors:=Unknown'))
        se({2}, cache.search('not authors:"=Author Two"', book_ids={1, 2}))
        se({2}, cache.search('not authors:"=Author Two"', 'not authors:=Unknown', book_ids={1,2,3}))
        se(set(), cache.search('authors:=Unknown', 'not authors:=Unknown', book_ids={1,2,3}))
        se(cache.all_book_ids(), cache.books_in_virtual_library(''))
        se(cache.all_book_ids(), cache.books_in_virtual_library('does not exist'))
        cache.set_pref('virtual_libraries', {'1':'title:"=Title One"', '12':'id:1 or id:2'})
        se({2}, cache.books_in_virtual_library('1'))
        se({1,2}, cache.books_in_virtual_library('12'))
        se({1}, cache.books_in_virtual_library('12', 'id:1'))
        se({2}, cache.books_in_virtual_library('1', 'id:1 or id:2'))
    # }}}

    def test_search_caching(self):  # {{{
        ' Test caching of searches '
        from calibre.db.search import LRUCache

        class TestCache(LRUCache):
            hit_counter = 0
            miss_counter = 0

            def get(self, key, default=None):
                ans = LRUCache.get(self, key, default=default)
                if ans is not None:
                    self.hit_counter += 1
                else:
                    self.miss_counter += 1

            @property
            def cc(self):
                self.hit_counter = self.miss_counter = 0

            @property
            def counts(self):
                return self.hit_counter, self.miss_counter

        cache = self.init_cache()
        cache._search_api.cache = c = TestCache()

        ae = self.assertEqual

        def test(hit, result, *args, **kw):
            c.cc
            num = kw.get('num', 2)
            ae(cache.search(*args), result)
            ae(c.counts, (num, 0) if hit else (0, num))
            c.cc

        test(False, {3}, 'Unknown')
        test(True, {3}, 'Unknown')
        test(True, {3}, 'Unknown')
        cache._search_api.MAX_CACHE_UPDATE = 0
        cache.set_field('title', {3:'xxx'})
        test(False, {3}, 'Unknown')  # cache cleared
        test(True, {3}, 'Unknown')
        c.limit = 5
        for i in range(6):
            test(False, set(), f'nomatch_{i}')
        test(False, {3}, 'Unknown')  # cached search expired
        test(False, {3}, '', 'unknown', num=1)
        test(True, {3}, '', 'unknown', num=1)
        test(True, {3}, 'Unknown', 'unknown', num=1)
        cache._search_api.MAX_CACHE_UPDATE = 100
        test(False, {2, 3}, 'title:=xxx or title:"=Title One"')
        cache.set_field('publisher', {3:'ppppp', 2:'other'})
        # Test cache update worked
        test(True, {2, 3}, 'title:=xxx or title:"=Title One"')
    # }}}

    def test_proxy_metadata(self):  # {{{
        ' Test the ProxyMetadata object used for composite columns '
        from calibre.ebooks.metadata.book.base import STANDARD_METADATA_FIELDS
        cache = self.init_cache()
        for book_id in cache.all_book_ids():
            mi = cache.get_metadata(book_id, get_user_categories=True)
            pmi = cache.get_proxy_metadata(book_id)
            self.assertSetEqual(set(mi.custom_field_keys()), set(pmi.custom_field_keys()))

            for field in STANDARD_METADATA_FIELDS | {'#series_index'}:
                if field == 'formats':
                    def f(x):
                        return (x if x is None else tuple(x))
                else:
                    def f(x):
                        return x
                self.assertEqual(f(getattr(mi, field)), f(getattr(pmi, field)),
                                f'Standard field: {field} not the same for book {book_id}')
                self.assertEqual(mi.format_field(field), pmi.format_field(field),
                                f'Standard field format: {field} not the same for book {book_id}')

                def f(x):
                    try:
                        x.pop('rec_index', None)
                    except Exception:
                        pass
                    return x
                if field not in {'#series_index'}:
                    v = pmi.get_standard_metadata(field)
                    self.assertTrue(v is None or isinstance(v, dict))
                    self.assertEqual(f(mi.get_standard_metadata(field, False)), f(v),
                                     f'get_standard_metadata() failed for field {field}')
            for field, meta in cache.field_metadata.custom_iteritems():
                if meta['datatype'] != 'composite':
                    self.assertEqual(f(getattr(mi, field)), f(getattr(pmi, field)),
                                    f'Custom field: {field} not the same for book {book_id}')
                    self.assertEqual(mi.format_field(field), pmi.format_field(field),
                                    f'Custom field format: {field} not the same for book {book_id}')

        # Test handling of recursive templates
        cache.create_custom_column('comp2', 'comp2', 'composite', False, display={'composite_template':'{title}'})
        cache.create_custom_column('comp1', 'comp1', 'composite', False, display={'composite_template':'foo{#comp2}'})
        cache.close()
        cache = self.init_cache()
        mi, pmi = cache.get_metadata(1), cache.get_proxy_metadata(1)
        self.assertEqual(mi.get('#comp1'), pmi.get('#comp1'))

        # Test overridden Metadata methods

        self.assertTrue(pmi.has_key('tags') == mi.has_key('tags'))

        self.assertFalse(pmi.has_key('taggs'), 'taggs attribute')
        self.assertTrue(pmi.has_key('taggs') == mi.has_key('taggs'))

        self.assertSetEqual(set(pmi.custom_field_keys()), set(mi.custom_field_keys()))

        self.assertEqual(pmi.get_extra('#series', 0), 3)
        self.assertEqual(pmi.get_extra('#series', 0), mi.get_extra('#series', 0))

        self.assertDictEqual(pmi.get_identifiers(), {'test': 'two'})
        self.assertDictEqual(pmi.get_identifiers(), mi.get_identifiers())

        self.assertTrue(pmi.has_identifier('test'))
        self.assertTrue(pmi.has_identifier('test') == mi.has_identifier('test'))

        self.assertListEqual(list(pmi.custom_field_keys()), list(mi.custom_field_keys()))

        # ProxyMetadata has the virtual fields while Metadata does not.
        self.assertSetEqual(set(pmi.all_field_keys())-{'id', 'series_sort', 'path',
                                                       'in_tag_browser', 'sort', 'ondevice',
                                                       'au_map', 'marked', '#series_index'},
                            set(mi.all_field_keys()))

        # mi.get_standard_metadata() doesn't include the rec_index metadata key
        fm_pmi = pmi.get_standard_metadata('series')
        fm_pmi.pop('rec_index')
        self.assertDictEqual(fm_pmi, mi.get_standard_metadata('series', make_copy=False))

        # The ProxyMetadata versions don't include the values. Note that the mi
        # version of get_standard_metadata won't return custom columns while the
        # ProxyMetadata version will
        fm_mi = mi.get_user_metadata('#series', make_copy=False)
        fm_mi.pop('#extra#')
        fm_mi.pop('#value#')
        self.assertDictEqual(pmi.get_standard_metadata('#series'), fm_mi)
        self.assertDictEqual(pmi.get_user_metadata('#series'), fm_mi)

        fm_mi = mi.get_all_user_metadata(make_copy=False)
        for one in fm_mi:
            fm_mi[one].pop('#extra#', None)
            fm_mi[one].pop('#value#', None)
        self.assertDictEqual(pmi.get_all_user_metadata(make_copy=False), fm_mi)

        # Check the unimplemented methods
        self.assertRaises(NotImplementedError, lambda: 'foo' in pmi)
        self.assertRaises(NotImplementedError, pmi.set, 'a', 'a')
        self.assertRaises(NotImplementedError, pmi.set_identifiers, 'a', 'a')
        self.assertRaises(NotImplementedError, pmi.set_identifier, 'a', 'a')
        self.assertRaises(NotImplementedError, pmi.all_non_none_fields)
        self.assertRaises(NotImplementedError, pmi.set_all_user_metadata, {})
        self.assertRaises(NotImplementedError, pmi.set_user_metadata, 'a', {})
        self.assertRaises(NotImplementedError, pmi.remove_stale_user_metadata, {})
        self.assertRaises(NotImplementedError, pmi.template_to_attribute, {}, {})
        self.assertRaises(NotImplementedError, pmi.smart_update, {})

    # }}}

    def test_marked_field(self):  # {{{
        ' Test the marked field '
        db = self.init_legacy()
        db.set_marked_ids({3:1, 2:3})
        ids = [1,2,3]
        db.multisort([('marked', True)], only_ids=ids)
        self.assertListEqual([1, 3, 2], ids)
        db.multisort([('marked', False)], only_ids=ids)
        self.assertListEqual([2, 3, 1], ids)
    # }}}

    def test_composites(self):  # {{{
        ' Test sorting and searching in composite columns '
        cache = self.init_cache()
        cache.create_custom_column('mult', 'CC1', 'composite', True, display={'composite_template': 'b,a,c'})
        cache.create_custom_column('single', 'CC2', 'composite', False, display={'composite_template': 'b,a,c'})
        cache.create_custom_column('number', 'CC3', 'composite', False, display={'composite_template': '{#float}', 'composite_sort':'number'})
        cache.create_custom_column('size', 'CC4', 'composite', False, display={'composite_template': '{#float:human_readable()}', 'composite_sort':'number'})
        cache.create_custom_column('ccdate', 'CC5', 'composite', False,
                display={'composite_template': "{:'format_date(raw_field('pubdate'), 'dd-MM-yy')'}", 'composite_sort':'date'})
        cache.create_custom_column('bool', 'CC6', 'composite', False, display={'composite_template': '{#yesno}', 'composite_sort':'bool'})
        cache.create_custom_column('ccm', 'CC7', 'composite', True, display={'composite_template': '{#tags}'})
        cache.create_custom_column('ccp', 'CC8', 'composite', True, display={'composite_template': '{publisher}'})
        cache.create_custom_column('ccf', 'CC9', 'composite', True, display={'composite_template': "{:'approximate_formats()'}"})

        cache = self.init_cache()
        # Test searching
        self.assertEqual({1,2,3}, cache.search('#mult:=a'))
        self.assertEqual(set(), cache.search('#mult:=b,a,c'))
        self.assertEqual({1,2,3}, cache.search('#single:=b,a,c'))
        self.assertEqual(set(), cache.search('#single:=b'))

        # Test numeric sorting
        cache.set_field('#float', {1:2, 2:10, 3:0.0001})
        self.assertEqual([3, 1, 2], cache.multisort([('#number', True)]))
        cache.set_field('#float', {1:3, 2:2*1024, 3:1*1024*1024})
        self.assertEqual([1, 2, 3], cache.multisort([('#size', True)]))

        # Test date sorting
        cache.set_field('pubdate', {1:p('2001-02-06'), 2:p('2001-10-06'), 3:p('2001-06-06')})
        self.assertEqual([1, 3, 2], cache.multisort([('#ccdate', True)]))

        # Test bool sorting
        self.assertEqual([2, 1, 3], cache.multisort([('#bool', True)]))

        # Test is_multiple sorting
        cache.set_field('#tags', {1:'b, a, c', 2:'a, b, c', 3:'a, c, b'})
        self.assertEqual([1, 2, 3], cache.multisort([('#ccm', True)]))

        # Test that lock downgrading during update of search cache works
        self.assertEqual(cache.search('#ccp:One'), {2})
        cache.set_field('publisher', {2:'One', 1:'One'})
        self.assertEqual(cache.search('#ccp:One'), {1, 2})

        self.assertEqual(cache.search('#ccf:FMT1'), {1, 2})
        cache.remove_formats({1:('FMT1',)})
        self.assertEqual('FMT2', cache.field_for('#ccf', 1))
    # }}}

    def test_find_identical_books(self):  # {{{
        ' Test find_identical_books '
        from calibre.db.utils import find_identical_books
        from calibre.ebooks.metadata.book.base import Metadata
        # 'find_identical_books': [(,), (Metadata('unknown'),), (Metadata('xxxx'),)],
        cache = self.init_cache(self.library_path)
        cache.set_field('languages', {1: ('fra', 'deu')})
        data = cache.data_for_find_identical_books()
        lm = cache.get_metadata(1)
        lm2 = cache.get_metadata(1)
        lm2.languages = ['eng']
        for mi, books in (
                (Metadata('title one', ['author one']), {2}),
                (Metadata('Unknown', ['Unknown']), {3}),
                (Metadata('title two', ['author one']), {1}),
                (lm, {1}),
                (lm2, set()),
        ):
            self.assertEqual(books, cache.find_identical_books(mi))
            self.assertEqual(books, find_identical_books(mi, data))
    # }}}

    def test_last_read_positions(self):  # {{{
        cache = self.init_cache(self.library_path)
        self.assertFalse(cache.get_last_read_positions(1, 'x', 'u'))
        self.assertRaises(Exception, cache.set_last_read_position, 12, 'x', cfi='c')
        epoch = time()
        cache.set_last_read_position(1, 'EPUB', 'user', 'device', 'cFi', epoch, 0.3)
        self.assertFalse(cache.get_last_read_positions(1, 'x', 'u'))
        self.assertEqual(cache.get_last_read_positions(1, 'ePuB', 'user'), [{'epoch':epoch, 'device':'device', 'cfi':'cFi', 'pos_frac':0.3}])
        cache.set_last_read_position(1, 'EPUB', 'user', 'device')
        self.assertFalse(cache.get_last_read_positions(1, 'ePuB', 'user'))
    # }}}

    def test_storing_conversion_options(self):  # {{{
        cache = self.init_cache(self.library_path)
        opts = {1: b'binary', 2: 'unicode'}
        cache.set_conversion_options(opts, 'PIPE')
        for book_id, val in iteritems(opts):
            got = cache.conversion_options(book_id, 'PIPE')
            if not isinstance(val, bytes):
                val = val.encode('utf-8')
            self.assertEqual(got, val)
    # }}}

    def test_template_db_functions(self):  # {{{
        from calibre.ebooks.metadata.book.formatter import SafeFormat
        formatter = SafeFormat()

        db = self.init_cache(self.library_path)
        db.create_custom_column('mult', 'CC1', 'composite', True, display={'composite_template': 'b,a,c'})

        # need an empty metadata object to pass to the formatter
        db = self.init_legacy(self.library_path)
        mi = db.get_metadata(1)

        # test counting books matching the search
        v = formatter.safe_format('program: book_count("series:true", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '2')

        # test counting books when none match the search
        v = formatter.safe_format('program: book_count("series:afafaf", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '0')

        # test is_multiple values
        v = formatter.safe_format('program: book_values("tags", "tags:true", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two'})

        # test not is_multiple values
        v = formatter.safe_format('program: book_values("series", "series:true", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, 'A Series One')

        # test returning values for a column not searched for
        v = formatter.safe_format('program: book_values("tags", "series:\\"A Series One\\"", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two'})

        # test getting a singleton value from books where the column is empty
        v = formatter.safe_format('program: book_values("series", "series:false", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '')

        # test getting a multiple value from books where the column is empty
        v = formatter.safe_format('program: book_values("tags", "tags:false", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '')

        # test fetching an unknown column
        v = formatter.safe_format('program: book_values("taaags", "tags:false", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, "TEMPLATE ERROR The column taaags doesn't exist")

        # test finding all books
        v = formatter.safe_format('program: book_values("id", "title:true", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'1', '2', '3'})

        # test getting value of a composite
        v = formatter.safe_format('program: book_values("#mult", "id:1", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'b', 'c', 'a'})

        # test getting value of a custom float
        v = formatter.safe_format('program: book_values("#float", "title:true", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'20.02', '10.01'})

        # test getting value of an int (rating)
        v = formatter.safe_format('program: book_values("rating", "title:true", ",", 0)', {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'4', '6'})
    # }}}

    def test_python_templates(self):  # {{{
        from calibre.ebooks.metadata.book.formatter import SafeFormat
        formatter = SafeFormat()

        # need an empty metadata object to pass to the formatter
        db = self.init_legacy(self.library_path)
        mi = db.get_metadata(1)

        # test counting books matching a search
        template = '''python:
def evaluate(book, ctx):
    ids = ctx.db.new_api.search("series:true")
    return str(len(ids))
'''
        v = formatter.safe_format(template, {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '2')

        # test counting books when none match the search
        template = '''python:
def evaluate(book, ctx):
    ids = ctx.db.new_api.search("series:afafaf")
    return str(len(ids))
'''
        v = formatter.safe_format(template, {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(v, '0')

        # test is_multiple values
        template = '''python:
def evaluate(book, ctx):
    tags = ctx.db.new_api.all_field_names('tags')
    return ','.join(list(tags))
'''
        v = formatter.safe_format(template, {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two'})

        # test using a custom context class
        template = '''python:
def evaluate(book, ctx):
    tags = ctx.db.new_api.all_field_names('tags')
    return ','.join(list(ctx.helper_function(tags)))
'''
        from calibre.utils.formatter import PythonTemplateContext

        class CustomContext(PythonTemplateContext):
            def helper_function(self, arg):
                s = set(arg)
                s.add('helper called')
                return s

        v = formatter.safe_format(template, {}, 'TEMPLATE ERROR', mi,
                                  python_context_object=CustomContext())
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two','helper called'})

        # test is_multiple values
        template = '''python:
def evaluate(book, ctx):
    tags = ctx.db.new_api.all_field_names('tags')
    return ','.join(list(tags))
'''
        v = formatter.safe_format(template, {}, 'TEMPLATE ERROR', mi)
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two'})

        # test calling a python stored template from a GPM template
        from calibre.utils.formatter_functions import load_user_template_functions, unload_user_template_functions
        load_user_template_functions('aaaaa',
                                     [['python_stored_template',
                                      '',
                                      0,
                                      '''python:
def evaluate(book, ctx):
    tags = set(ctx.db.new_api.all_field_names('tags'))
    tags.add(ctx.arguments[0])
    return ','.join(list(tags))
'''
                                      ]], None)
        v = formatter.safe_format('program: python_stored_template("one argument")', {},
                                  'TEMPLATE ERROR', mi)
        unload_user_template_functions('aaaaa')
        self.assertEqual(set(v.split(',')), {'Tag One', 'News', 'Tag Two', 'one argument'})
    # }}}
