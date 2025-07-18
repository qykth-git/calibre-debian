#!/usr/bin/env python
# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid at kovidgoyal.net>

''' Post installation script for linux '''

import errno
import os
import stat
import sys
import textwrap
from functools import partial
from subprocess import check_call, check_output

from calibre import CurrentDir, __appname__, guess_type, prints
from calibre.constants import isbsd, islinux
from calibre.customize.ui import all_input_formats
from calibre.ptempfile import TemporaryDirectory
from calibre.utils.localization import _
from calibre.utils.resources import get_image_path as I
from calibre.utils.resources import get_path as P
from polyglot.builtins import iteritems

entry_points = {
        'console_scripts': [
            'ebook-device         = calibre.devices.cli:main',
            'ebook-meta           = calibre.ebooks.metadata.cli:main',
            'ebook-convert        = calibre.ebooks.conversion.cli:main',
            'ebook-polish         = calibre.ebooks.oeb.polish.main:main',
            'markdown-calibre     = markdown.__main__:run',
            'web2disk             = calibre.web.fetch.simple:main',
            'calibre-server       = calibre.srv.standalone:main',
            'lrf2lrs              = calibre.ebooks.lrf.lrfparser:main',
            'lrs2lrf              = calibre.ebooks.lrf.lrs.convert_from:main',
            'calibre-debug        = calibre.debug:main',
            'calibredb            = calibre.db.cli.main:main',
            'calibre-parallel     = calibre.utils.ipc.worker:main',
            'calibre-customize    = calibre.customize.ui:main',
            'calibre-complete     = calibre.utils.complete:main',
            'fetch-ebook-metadata = calibre.ebooks.metadata.sources.cli:main',
            'calibre-smtp         = calibre.utils.smtp:main',
        ],
        'gui_scripts': [
            __appname__+' = calibre.gui_launch:calibre',
            'lrfviewer    = calibre.gui2.lrf_renderer.main:main',
            'ebook-viewer = calibre.gui_launch:ebook_viewer',
            'ebook-edit   = calibre.gui_launch:ebook_edit',
        ],
      }


def polyglot_write(stream):
    stream_write = stream.write

    def write(x):
        if not isinstance(x, bytes):
            x = x.encode('utf-8')
        return stream_write(x)
    return write


class PreserveMIMEDefaults:  # {{{

    def __init__(self):
        self.initial_values = {}

    def __enter__(self):
        def_data_dirs = '/usr/local/share:/usr/share'
        paths = os.environ.get('XDG_DATA_DIRS', def_data_dirs)
        paths = paths.split(':')
        paths.append(os.environ.get('XDG_DATA_HOME', os.path.expanduser(
            '~/.local/share')))
        paths = list(filter(os.path.isdir, paths))
        if not paths:
            # Env var had garbage in it, ignore it
            paths = def_data_dirs.split(':')
        paths = list(filter(os.path.isdir, paths))
        self.paths = {os.path.join(x, 'applications/defaults.list') for x in
                paths}
        self.initial_values = {}
        for x in self.paths:
            try:
                with open(x, 'rb') as f:
                    self.initial_values[x] = f.read()
            except Exception:
                self.initial_values[x] = None

    def __exit__(self, *args):
        for path, val in iteritems(self.initial_values):
            if val is None:
                try:
                    os.remove(path)
                except Exception:
                    pass
            elif os.path.exists(path):
                try:
                    with open(path, 'r+b') as f:
                        if f.read() != val:
                            f.seek(0)
                            f.truncate()
                            f.write(val)
                except OSError as e:
                    if e.errno != errno.EACCES:
                        raise
# }}}


# Uninstall script {{{

UNINSTALL = '''\
#!/bin/sh
# Copyright (C) 2018 Kovid Goyal <kovid at kovidgoyal.net>

search_for_python() {{
    # We have to search for python as Ubuntu, in its infinite wisdom decided
    # to release 18.04 with no python symlink, making it impossible to run polyglot
    # python scripts.

    # We cannot use command -v as it is not implemented in the posh shell shipped with
    # Ubuntu/Debian. Similarly, there is no guarantee that which is installed.
    # Shell scripting is a horrible joke, thank heavens for python.
    local IFS=:
    if [ $ZSH_VERSION ]; then
        # zsh does not split by default
        setopt sh_word_split
    fi
    local candidate_path
    local candidate_python
    local pythons=python3:python2
    # disable pathname expansion (globbing)
    set -f
    for candidate_path in $PATH
    do
        if [ ! -z $candidate_path ]
        then
            for candidate_python in $pythons
            do
                if [ ! -z "$candidate_path" ]
                then
                    if [ -x "$candidate_path/$candidate_python" ]
                    then
                        printf "$candidate_path/$candidate_python"
                        return
                    fi
                fi
            done
        fi
    done
    set +f
    printf "python"
}}

PYTHON=$(search_for_python)
echo Using python executable: $PYTHON

$PYTHON -c "import sys; exec(sys.stdin.read());" "$0" <<'CALIBRE_LINUX_INSTALLER_HEREDOC'
#!{python}
# vim:fileencoding=UTF-8
from __future__ import print_function, unicode_literals
euid = {euid}

import os, subprocess, shutil, tempfile, sys

try:
    raw_input
except NameError:
    raw_input = input
sys.stdin = open('/dev/tty')

if os.geteuid() != euid:
    print('The installer was last run as user id:', euid, 'To remove all files you must run the uninstaller as the same user')
    if raw_input('Proceed anyway? [y/n]:').lower() != 'y':
        raise SystemExit(1)

frozen_path = {frozen_path!r}
if not frozen_path or not os.path.exists(os.path.join(frozen_path, 'resources', 'calibre-mimetypes.xml')):
    frozen_path = None

dummy_mime_path = tempfile.mkdtemp(prefix='mime-hack.')
for f in {mime_resources!r}:
    # dummyfile
    f = os.path.basename(f)
    file = os.path.join(dummy_mime_path, f)
    open(file, 'w').close()
    cmd = ['xdg-mime', 'uninstall', file]
    print('Removing mime resource:', f)
    ret = subprocess.call(cmd, shell=False)
    if ret != 0:
        print('WARNING: Failed to remove mime resource', f)

for x in tuple({manifest!r}) + tuple({appdata_resources!r}) + (sys.argv[-1], frozen_path, dummy_mime_path):
    if not x or not os.path.exists(x):
        continue
    print('Removing', x)
    try:
        if os.path.isdir(x):
            shutil.rmtree(x)
        else:
            os.unlink(x)
    except Exception as e:
        print('Failed to delete', x)
        print('\t', e)

icr = {icon_resources!r}
mimetype_icons = []

def remove_icon(context, name, size, update=False):
    cmd = ['xdg-icon-resource', 'uninstall', '--context', context, '--size', size, name]
    if not update:
        cmd.insert(2, '--noupdate')
    print('Removing icon:', name, 'from context:', context, 'at size:', size)
    ret = subprocess.call(cmd, shell=False)
    if ret != 0:
        print('WARNING: Failed to remove icon', name)

for i, (context, name, size) in enumerate(icr):
    if context == 'mimetypes':
        mimetype_icons.append((name, size))
        continue
    remove_icon(context, name, size, update=i == len(icr) - 1)

mr = {menu_resources!r}
for f in mr:
    cmd = ['xdg-desktop-menu', 'uninstall', f]
    print('Removing desktop file:', f)
    ret = subprocess.call(cmd, shell=False)
    if ret != 0:
        print('WARNING: Failed to remove menu item', f)

print()

if mimetype_icons and raw_input('Remove the e-book format icons? [y/n]:').lower() in ['', 'y']:
    for i, (name, size) in enumerate(mimetype_icons):
        remove_icon('mimetypes', name, size, update=i == len(mimetype_icons) - 1)
CALIBRE_LINUX_INSTALLER_HEREDOC
'''

# }}}


# Completion {{{

class ZshCompleter:  # {{{

    def __init__(self, opts):
        self.opts = opts
        self.dest = None
        base = os.path.dirname(self.opts.staging_sharedir)
        self.detect_zsh(base)
        if not self.dest and base == '/usr/share':
            # Ubuntu puts site-functions in /usr/local/share
            self.detect_zsh('/usr/local/share')

        self.commands = {}

    def detect_zsh(self, base):
        for x in ('vendor-completions', 'vendor-functions', 'site-functions'):
            c = os.path.join(base, 'zsh', x)
            if os.path.isdir(c) and os.access(c, os.W_OK):
                self.dest = os.path.join(c, '_calibre')
                break

    def get_options(self, parser, cover_opts=('--cover',), opf_opts=('--opf',),
                    file_map={}):
        if hasattr(parser, 'option_list'):
            options = parser.option_list
            for group in parser.option_groups:
                options += group.option_list
        else:
            options = parser
        for opt in options:
            lo, so = opt._long_opts, opt._short_opts
            if opt.takes_value():
                lo = [x+'=' for x in lo]
                so = [x+'+' for x in so]
            ostrings = lo + so
            ostrings = '{{{}}}'.format(','.join(ostrings)) if len(ostrings) > 1 else ostrings[0]
            exclude = ''
            if opt.dest is None:
                exclude = "'(- *)'"
            h = opt.help or ''
            h = h.replace('"', "'").replace('[', '(').replace(
                ']', ')').replace('\n', ' ').replace(':', '\\:').replace('`', "'")
            h = h.replace('%default', str(opt.default))
            arg = ''
            if opt.takes_value():
                arg = f':"{h}":'
                if opt.dest in {'extract_to', 'debug_pipeline', 'to_dir', 'outbox', 'with_library', 'library_path'}:
                    arg += "'_path_files -/'"
                elif opt.choices:
                    arg += '({})'.format('|'.join(opt.choices))
                elif set(file_map).intersection(set(opt._long_opts)):
                    k = tuple(set(file_map).intersection(set(opt._long_opts)))
                    exts = file_map[k[0]]
                    if exts:
                        exts = (f'*.{x}' for x in sorted(exts + [x.upper() for x in exts]))
                        arg += "'_files -g \"{}\"'".format(' '.join(exts))
                    else:
                        arg += '_files'
                elif (opt.dest in {'pidfile', 'attachment'}):
                    arg += '_files'
                elif set(opf_opts).intersection(set(opt._long_opts)):
                    arg += "'_files -g \"*.opf\"'"
                elif set(cover_opts).intersection(set(opt._long_opts)):
                    exts = (f'*.{x}' for x in sorted(pics + [x.upper() for x in pics]))
                    arg += "'_files -g \"{}\"'".format(' '.join(exts))

            help_txt = f'"[{h}]"'
            yield f'{exclude}{ostrings}{help_txt}{arg} '

    def opts_and_exts(self, name, op, exts, cover_opts=('--cover',),
                      opf_opts=('--opf',), file_map={}):
        if not self.dest:
            return
        exts = sorted({x.lower() for x in exts})
        extra = ('''"*:filename:_files -g '(#i)*.({})'" '''.format('|'.join(exts)),)
        opts = '\\\n  '.join(tuple(self.get_options(
            op(), cover_opts=cover_opts, opf_opts=opf_opts, file_map=file_map)) + extra)
        txt = '_arguments -s \\\n  ' + opts
        self.commands[name] = txt

    def opts_and_words(self, name, op, words, takes_files=False):
        if not self.dest:
            return
        extra = ("'*:filename:_files' ",) if takes_files else ()
        opts = '\\\n  '.join(tuple(self.get_options(op())) + extra)
        txt = '_arguments -s \\\n  ' + opts
        self.commands[name] = txt

    def do_ebook_convert(self, f):
        from calibre.customize.ui import available_output_formats
        from calibre.ebooks.conversion.cli import create_option_parser, group_titles
        from calibre.ebooks.conversion.plumber import supported_input_formats
        from calibre.utils.logging import DevNull
        from calibre.web.feeds.recipes.collection import get_builtin_recipe_titles
        input_fmts = sorted(set(supported_input_formats()))
        output_fmts = sorted(set(available_output_formats()))
        iexts = sorted({x.upper() for x in input_fmts}.union(input_fmts))
        oexts = sorted({x.upper() for x in output_fmts}.union(output_fmts))
        w = polyglot_write(f)
        # Arg 1
        w('\n_ebc_input_args() {')
        w('\n  local extras; extras=(')
        w('\n    {-h,--help}":Show Help"')
        w('\n    "--version:Show program version"')
        w('\n    "--list-recipes:List builtin recipe names"')
        for recipe in sorted(set(get_builtin_recipe_titles())):
            recipe = recipe.replace(':', '\\:').replace('"', '\\"')
            w(f'\n    "{recipe}.recipe"')
        w('\n  ); _describe -t recipes "ebook-convert builtin recipes" extras')
        w('\n  _files -g "{}"'.format(' '.join(f'*.{x}' for x in iexts)))
        w('\n}\n')

        # Arg 2
        w('\n_ebc_output_args() {')
        w('\n  local extras; extras=(')
        for x in output_fmts:
            w(f'\n    ".{x}:Convert to a .{x} file with the same name as the input file"')
        w('\n  ); _describe -t output "ebook-convert output" extras')
        w('\n  _files -g "{}"'.format(' '.join(f'*.{x}' for x in oexts)))
        w('\n  _path_files -/')
        w('\n}\n')

        log = DevNull()

        def get_parser(input_fmt='epub', output_fmt=None):
            of = ('dummy2.'+output_fmt) if output_fmt else 'dummy'
            return create_option_parser(('ec', 'dummy1.'+input_fmt, of, '-h'), log)[0]

        # Common options
        input_group, output_group = group_titles()
        p = get_parser()
        opts = p.option_list
        for group in p.option_groups:
            if group.title not in {input_group, output_group}:
                opts += group.option_list
        opts.append(p.get_option('--pretty-print'))
        opts.append(p.get_option('--input-encoding'))
        opts = '\\\n  '.join(tuple(
            self.get_options(opts, file_map={'--search-replace':()})))
        w('\n_ebc_common_opts() {')
        w('\n  _arguments -s \\\n  ' + opts)
        w('\n}\n')

        # Input/Output format options
        for fmts, group_title, func in (
            (input_fmts, input_group, '_ebc_input_opts_%s'),
            (output_fmts, output_group, '_ebc_output_opts_%s'),
        ):
            for fmt in fmts:
                is_input = group_title == input_group
                if is_input and fmt in {'rar', 'zip', 'oebzip'}:
                    continue
                p = (get_parser(input_fmt=fmt) if is_input
                     else get_parser(output_fmt=fmt))
                opts = None
                for group in p.option_groups:
                    if group.title == group_title:
                        opts = [o for o in group.option_list if
                                '--pretty-print' not in o._long_opts and
                                '--input-encoding' not in o._long_opts]
                if not opts:
                    continue
                opts = '\\\n  '.join(tuple(sorted(self.get_options(opts))))
                w('\n%s() {'%(func%fmt))
                w('\n  _arguments -s \\\n  ' + opts)
                w('\n}\n')

        w('\n_ebook_convert() {')
        w('\n  local iarg oarg context state_descr state line\n  typeset -A opt_args\n  local ret=1')
        w("\n  _arguments '1: :_ebc_input_args' '*::ebook-convert output:->args' && ret=0")
        w('\n  case $state in \n  (args)')
        w('\n    iarg=${line[1]##*.}; ')
        w("\n    _arguments '1: :_ebc_output_args' '*::ebook-convert options:->args' && ret=0")
        w('\n     case $state in \n    (args)')

        w('\n      oarg=${line[1]##*.}')
        w('\n      iarg="_ebc_input_opts_${(L)iarg}"; oarg="_ebc_output_opts_${(L)oarg}"')
        w('\n      _call_function - $iarg; _call_function - $oarg; _ebc_common_opts; ret=0')
        w('\n    ;;\n    esac')

        w('\n  ;;\n  esac\n  return ret')
        w('\n}\n')

    def do_ebook_edit(self, f):
        from calibre.ebooks.oeb.polish.import_book import IMPORTABLE
        from calibre.ebooks.oeb.polish.main import SUPPORTED
        from calibre.gui2.tweak_book.main import option_parser
        tweakable_fmts = sorted(SUPPORTED | IMPORTABLE)
        parser = option_parser()
        opt_lines = []
        for opt in parser.option_list:
            lo, so = opt._long_opts, opt._short_opts
            if opt.takes_value():
                lo = [x+'=' for x in lo]
                so = [x+'+' for x in so]
            ostrings = lo + so
            ostrings = '{{{}}}'.format(','.join(ostrings)) if len(ostrings) > 1 else f'"{ostrings[0]}"'
            h = opt.help or ''
            h = h.replace('"', "'").replace('[', '(').replace(
                ']', ')').replace('\n', ' ').replace(':', '\\:').replace('`', "'")
            h = h.replace('%default', str(opt.default))
            help_txt = f'"[{h}]"'
            opt_lines.append(ostrings + help_txt + ' \\')
        opt_lines = ('\n' + (' ' * 8)).join(opt_lines)

        polyglot_write(f)('''
_ebook_edit() {{
    local curcontext="$curcontext" state line ebookfile expl
    typeset -A opt_args

    _arguments -C -s \\
        {}
        "1:ebook file:_files -g '(#i)*.({})'" \\
        '*:file in ebook:->files' && return 0

    case $state in
        files)
            ebookfile=${{~${{(Q)line[1]}}}}

            if [[ -f "$ebookfile" && "$ebookfile" =~ '\\.[eE][pP][uU][bB]$' ]]; then
                _zip_cache_name="$ebookfile"
                _zip_cache_list=( ${{(f)"$(zipinfo -1 $_zip_cache_name 2>/dev/null)"}} )
            else
                return 1
            fi
            _wanted files expl 'file from ebook' \\
            _multi_parts / _zip_cache_list && return 0
            ;;
    esac

    return 1
}}
'''.format(opt_lines, '|'.join(tweakable_fmts)) + '\n\n')

    def do_calibredb(self, f):
        from calibre.customize.ui import available_catalog_formats
        from calibre.db.cli.main import COMMANDS, option_parser_for
        parsers, descs = {}, {}
        for command in COMMANDS:
            p = option_parser_for(command)()
            parsers[command] = p
            lines = [x.strip().partition('.')[0] for x in p.usage.splitlines() if x.strip() and
                     not x.strip().startswith('%prog')]
            descs[command] = lines[0]

        w = polyglot_write(f)
        w('\n_calibredb_cmds() {\n  local commands; commands=(\n')
        w('    {-h,--help}":Show help"\n')
        w('    "--version:Show version"\n')
        for command, desc in iteritems(descs):
            w('    "{}:{}"\n'.format(
                command, desc.replace(':', '\\:').replace('"', "'")))
        w('  )\n  _describe -t commands "calibredb command" commands \n}\n')

        subcommands = []
        for command, parser in iteritems(parsers):
            exts = []
            if command == 'catalog':
                exts = [x.lower() for x in available_catalog_formats()]
            elif command == 'set_metadata':
                exts = ['opf']
            exts = sorted(set(exts).union(x.upper() for x in exts))
            pats = (f'*.{x}' for x in exts)
            extra = ("'*:filename:_files -g \"{}\"' ".format(' '.join(pats)),) if exts else ()
            if command in {'add', 'add_format'}:
                extra = ("'*:filename:_files' ",)
            opts = '\\\n        '.join(tuple(self.get_options(
                parser)) + extra)
            txt = '  _arguments -s \\\n        ' + opts
            subcommands.append(f'({command})')
            subcommands.append(txt)
            subcommands.append(';;')

        w('\n_calibredb() {')
        w(
            r'''
    local state line state_descr context
    typeset -A opt_args
    local ret=1

    _arguments \
        '1: :_calibredb_cmds' \
        '*::calibredb subcommand options:->args' \
        && ret=0

    case $state in
    (args)
    case $line[1] in
      (-h|--help|--version)
          _message 'no more arguments' && ret=0
      ;;
    {}
    esac
    ;;
    esac

    return ret
    '''.format('\n    '.join(subcommands)))
        w('\n}\n\n')

    def write(self):

        if self.dest:
            for c in ('calibredb', 'ebook-convert', 'ebook-edit'):
                self.commands[c] = ' _{} "$@"'.format(c.replace('-', '_'))
            with open(self.dest, 'wb') as f:
                w = polyglot_write(f)
                w('#compdef ' + ' '.join(self.commands)+'\n')
                self.do_ebook_convert(f)
                self.do_calibredb(f)
                self.do_ebook_edit(f)
                w('case $service in\n')
                for c, txt in iteritems(self.commands):
                    w(f'{c})\n{txt}\n;;\n')
                w('esac\n')
# }}}


def get_bash_completion_path(root, share, info):
    if root == '/usr':
        # Try to get the system bash completion dir since we are installing to
        # /usr
        try:
            path = check_output('pkg-config --variable=completionsdir bash-completion'.split()).decode('utf-8').strip().partition(os.pathsep)[0]
        except Exception:
            info('Failed to find directory to install bash completions, using default.')
            path = '/usr/share/bash-completion/completions'
        if path and os.path.exists(path) and os.path.isdir(path):
            return path
    else:
        # Use the default bash-completion dir under staging_share
        return os.path.join(share, 'bash-completion', 'completions')


def write_completion(self, bash_comp_dest, zsh):
    from calibre.customize.ui import available_input_formats
    from calibre.debug import option_parser as debug_op
    from calibre.ebooks import BOOK_EXTENSIONS
    from calibre.ebooks.lrf.lrfparser import option_parser as lrf2lrsop
    from calibre.ebooks.metadata.cli import filetypes as meta_filetypes
    from calibre.ebooks.metadata.cli import option_parser as metaop
    from calibre.ebooks.metadata.sources.cli import option_parser as fem_op
    from calibre.ebooks.oeb.polish.import_book import IMPORTABLE
    from calibre.ebooks.oeb.polish.main import SUPPORTED
    from calibre.ebooks.oeb.polish.main import option_parser as polish_op
    from calibre.gui2.lrf_renderer.main import option_parser as lrfviewerop
    from calibre.gui2.main import option_parser as guiop
    from calibre.gui2.tweak_book.main import option_parser as tweak_op
    from calibre.gui2.viewer.main import option_parser as viewer_op
    from calibre.srv.standalone import create_option_parser as serv_op
    from calibre.utils.smtp import option_parser as smtp_op
    input_formats = sorted(all_input_formats())
    tweak_formats = sorted(x.lower() for x in SUPPORTED|IMPORTABLE)

    if bash_comp_dest and not os.path.exists(bash_comp_dest):
        os.makedirs(bash_comp_dest)

    complete = 'calibre-complete'
    if getattr(sys, 'frozen_path', None):
        complete = os.path.join(getattr(sys, 'frozen_path'), complete)

    def o_and_e(name, *args, **kwargs):
        bash_compfile = os.path.join(bash_comp_dest, name)
        with open(bash_compfile, 'wb') as f:
            f.write(opts_and_exts(name, *args, **kwargs))
        self.manifest.append(bash_compfile)
        zsh.opts_and_exts(name, *args, **kwargs)

    def o_and_w(name, *args, **kwargs):
        bash_compfile = os.path.join(bash_comp_dest, name)
        with open(bash_compfile, 'wb') as f:
            f.write(opts_and_words(name, *args, **kwargs))
        self.manifest.append(bash_compfile)
        zsh.opts_and_words(name, *args, **kwargs)

    o_and_e('calibre', guiop, BOOK_EXTENSIONS)
    o_and_e('lrf2lrs', lrf2lrsop, ['lrf'], file_map={'--output':['lrs']})
    o_and_e('ebook-meta', metaop,
            list(meta_filetypes()), cover_opts=['--cover', '-c'],
            opf_opts=['--to-opf', '--from-opf'])
    o_and_e('ebook-polish', polish_op,
            [x.lower() for x in SUPPORTED], cover_opts=['--cover', '-c'],
            opf_opts=['--opf', '-o'])
    o_and_e('lrfviewer', lrfviewerop, ['lrf'])
    o_and_e('ebook-viewer', viewer_op, input_formats)
    o_and_e('ebook-edit', tweak_op, tweak_formats)
    o_and_w('fetch-ebook-metadata', fem_op, [])
    o_and_w('calibre-smtp', smtp_op, [])
    o_and_w('calibre-server', serv_op, [])
    o_and_e('calibre-debug', debug_op, ['py', 'recipe', 'epub', 'mobi', 'azw', 'azw3', 'docx'], file_map={
        '--tweak-book':['epub', 'azw3', 'mobi'],
        '--subset-font':['ttf', 'otf'],
        '--exec-file':['py', 'recipe'],
        '--add-simple-plugin':['py'],
        '--inspect-mobi':['mobi', 'azw', 'azw3'],
        '--viewer':sorted(available_input_formats()),
    })
    with open(os.path.join(bash_comp_dest, 'ebook-device'), 'wb') as f:
        f.write(textwrap.dedent('''\
        _ebook_device_ls()
        {
        local pattern search listing prefix
        pattern="$1"
        search="$1"
        if [[ -n "{$pattern}" ]]; then
            if [[ "${pattern:(-1)}" == "/" ]]; then
            pattern=""
            else
            pattern="$(basename ${pattern} 2> /dev/null)"
            search="$(dirname ${search} 2> /dev/null)"
            fi
        fi

        if [[  "x${search}" == "x" || "x${search}" == "x." ]]; then
            search="/"
        fi

        listing="$(ebook-device ls ${search} 2>/dev/null)"

        prefix="${search}"
        if [[ "x${prefix:(-1)}" != "x/" ]]; then
            prefix="${prefix}/"
        fi

        echo $(compgen -P "${prefix}" -W "${listing}" "${pattern}")
        }

        _ebook_device()
        {
        local cur prev
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        COMPREPLY=()
        case "${prev}" in
            ls|rm|mkdir|touch|cat )
                COMPREPLY=( $(_ebook_device_ls "${cur}") )
                return 0
                ;;
            cp )
                if [[ ${cur} == dev:* ]]; then
                COMPREPLY=( $(_ebook_device_ls "${cur:7}") )
                return 0
                else
                _filedir
                return 0
                fi
                ;;
            dev )
                COMPREPLY=( $(compgen -W "cp ls rm mkdir touch cat info books df" "${cur}") )
                return 0
                ;;
            * )
                if [[ ${cur} == dev:* ]]; then
                COMPREPLY=( $(_ebook_device_ls "${cur:7}") )
                return 0
                else
                if [[ ${prev} == dev:* ]]; then
                    _filedir
                    return 0
                else
                    COMPREPLY=( $(compgen -W "dev:" "${cur}") )
                    return 0
                fi
                return 0
                fi
            ;;
        esac
        }
        complete -o nospace  -F _ebook_device ebook-device''').encode('utf-8'))
    self.manifest.append(os.path.join(bash_comp_dest, 'ebook-device'))
    with open(os.path.join(bash_comp_dest, 'ebook-convert'), 'wb') as f:
        f.write((f'complete -o nospace -C {complete} ebook-convert').encode('utf-8'))
    self.manifest.append(os.path.join(bash_comp_dest, 'ebook-convert'))
    zsh.write()
# }}}


class PostInstall:

    def task_failed(self, msg):
        self.warn(msg, 'with error:')
        import traceback
        tb = '\n\t'.join(traceback.format_exc().splitlines())
        self.info('\t'+tb)
        print()

    def warning(self, *args, **kwargs):
        print('\n'+'_'*20, 'WARNING','_'*20)
        prints(*args, **kwargs)
        print('_'*50)
        print('\n')
        self.warnings.append((args, kwargs))
        sys.stdout.flush()

    def __init__(self, opts, info=prints, warn=None, manifest=None):
        self.opts = opts
        self.info = info
        self.warn = warn
        self.warnings = []
        if self.warn is None:
            self.warn = self.warning

        if not self.opts.staging_bindir:
            self.opts.staging_bindir = os.path.join(self.opts.staging_root,
            'bin')
        if not self.opts.staging_sharedir:
            self.opts.staging_sharedir = os.path.join(self.opts.staging_root,
            'share', 'calibre')
        self.opts.staging_etc = '/etc' if self.opts.staging_root == '/usr' else \
                os.path.join(self.opts.staging_root, 'etc')

        prefix = getattr(self.opts, 'prefix', None)
        if prefix and prefix != self.opts.staging_root:
            self.opts.staged_install = True
            os.environ['XDG_DATA_DIRS'] = os.path.join(self.opts.staging_root, 'share')
            os.environ['XDG_UTILS_INSTALL_MODE'] = 'system'

        from calibre.utils.serialize import msgpack_loads
        scripts = msgpack_loads(P('scripts.calibre_msgpack', data=True))
        self.manifest = manifest or []
        if getattr(sys, 'frozen_path', False):
            if os.access(self.opts.staging_bindir, os.W_OK):
                self.info('Creating symlinks...')
                for exe in scripts:
                    dest = os.path.join(self.opts.staging_bindir, exe)
                    if os.path.lexists(dest):
                        os.unlink(dest)
                    tgt = os.path.join(getattr(sys, 'frozen_path'), exe)
                    self.info(f'\tSymlinking {tgt} to {dest}')
                    os.symlink(tgt, dest)
                    self.manifest.append(dest)
            else:
                self.warning(textwrap.fill(
                    'No permission to write to {}, not creating program launch symlinks,'
                    ' you should ensure that {} is in your PATH or create the symlinks yourself'.format(
                        self.opts.staging_bindir, getattr(sys, 'frozen_path', 'the calibre installation directory'))))

        self.icon_resources = []
        self.menu_resources = []
        self.mime_resources = []
        self.appdata_resources = []
        if islinux or isbsd:
            self.setup_completion()
        if islinux or isbsd:
            self.setup_desktop_integration()
        if not getattr(self.opts, 'staged_install', False):
            self.create_uninstaller()

        from calibre.utils.config import config_dir
        if os.path.exists(config_dir):
            os.chdir(config_dir)
            if islinux or isbsd:
                for f in os.listdir('.'):
                    if os.stat(f).st_uid == 0:
                        import shutil
                        shutil.rmtree(f) if os.path.isdir(f) else os.unlink(f)
                if os.stat(config_dir).st_uid == 0:
                    os.rmdir(config_dir)

        if warn is None and self.warnings:
            self.info(f'\n\nThere were {len(self.warnings)} warnings\n')
            for args, kwargs in self.warnings:
                self.info('*', *args, **kwargs)
                print()

    def create_uninstaller(self):
        base = self.opts.staging_bindir
        if not os.access(base, os.W_OK) and getattr(sys, 'frozen_path', False):
            base = sys.frozen_path
        dest = os.path.join(base, 'calibre-uninstall')
        self.info('Creating un-installer:', dest)
        raw = UNINSTALL.format(
            python='/usr/bin/python', euid=os.geteuid(),
            manifest=self.manifest, icon_resources=self.icon_resources,
            mime_resources=self.mime_resources, menu_resources=self.menu_resources,
            appdata_resources=self.appdata_resources, frozen_path=getattr(sys, 'frozen_path', None))
        try:
            with open(dest, 'wb') as f:
                f.write(raw.encode('utf-8'))
            os.chmod(dest, stat.S_IRWXU|stat.S_IRGRP|stat.S_IROTH)
            if os.geteuid() == 0:
                os.chown(dest, 0, 0)
        except Exception:
            if self.opts.fatal_errors:
                raise
            self.task_failed('Creating uninstaller failed')

    def setup_completion(self):  # {{{
        try:
            self.info('Setting up command-line completion...')
            zsh = ZshCompleter(self.opts)
            if zsh.dest:
                self.info('Installing zsh completion to:', zsh.dest)
                self.manifest.append(zsh.dest)
            bash_comp_dest = get_bash_completion_path(self.opts.staging_root, os.path.dirname(self.opts.staging_sharedir), self.info)
            if bash_comp_dest is not None:
                self.info('Installing bash completion to:', bash_comp_dest+os.sep)
            write_completion(self, bash_comp_dest, zsh)
        except TypeError as err:
            if 'resolve_entities' in str(err):
                print('You need python-lxml >= 2.0.5 for calibre')
                sys.exit(1)
            raise
        except OSError as e:
            if e.errno == errno.EACCES:
                self.warning('Failed to setup completion, permission denied')
            if self.opts.fatal_errors:
                raise
            self.task_failed('Setting up completion failed')
        except Exception:
            if self.opts.fatal_errors:
                raise
            self.task_failed('Setting up completion failed')
    # }}}

    def setup_desktop_integration(self):  # {{{
        try:
            self.info('Setting up desktop integration...')
            self.do_setup_desktop_integration()
        except Exception:
            if self.opts.fatal_errors:
                raise
            self.task_failed('Setting up desktop integration failed')

    def do_setup_desktop_integration(self):
        env = os.environ.copy()
        cc = check_call
        if getattr(sys, 'frozen_path', False) and 'LD_LIBRARY_PATH' in env:
            paths = env.get('LD_LIBRARY_PATH', '').split(os.pathsep)
            paths = [x for x in paths if x]
            npaths = [x for x in paths if x != sys.frozen_path+'/lib']
            env['LD_LIBRARY_PATH'] = os.pathsep.join(npaths)
            cc = partial(check_call, env=env)

        if getattr(self.opts, 'staged_install', False):
            for d in {'applications', 'desktop-directories', 'icons/hicolor', 'mime/packages'}:
                os.makedirs(os.path.join(self.opts.staging_root, 'share', d), exist_ok=True)

        with TemporaryDirectory() as tdir, CurrentDir(tdir):
            with PreserveMIMEDefaults():
                self.install_xdg_junk(cc, env)

    def install_xdg_junk(self, cc, env):

        def install_single_icon(iconsrc, basename, size, context, is_last_icon=False):
            filename = f'{basename}-{size}.png'
            render_img(iconsrc, filename, width=int(size), height=int(size))
            cmd = ['xdg-icon-resource', 'install', '--noupdate', '--context', context, '--size', str(size), filename, basename]
            if is_last_icon:
                del cmd[2]
            cc(cmd)
            self.icon_resources.append((context, basename, str(size)))

        def install_icons(iconsrc, basename, context, is_last_icon=False):
            sizes = (16, 32, 48, 64, 128, 256)
            for size in sizes:
                install_single_icon(iconsrc, basename, size, context, is_last_icon and size is sizes[-1])

        icons = [x.strip() for x in '''\
            mimetypes/lrf.png application-lrf mimetypes
            mimetypes/lrf.png text-lrs mimetypes
            mimetypes/mobi.png application-x-mobipocket-ebook mimetypes
            mimetypes/tpz.png application-x-topaz-ebook mimetypes
            mimetypes/azw2.png application-x-kindle-application mimetypes
            mimetypes/azw3.png application-x-mobi8-ebook mimetypes
            lt.png calibre-gui apps
            viewer.png calibre-viewer apps
            tweak.png calibre-ebook-edit apps
            '''.splitlines() if x.strip()]
        for line in icons:
            iconsrc, basename, context = line.split()
            install_icons(iconsrc, basename, context, is_last_icon=line is icons[-1])

        mimetypes = set()
        for x in all_input_formats():
            mt = guess_type('dummy.'+x)[0]
            if mt and 'chemical' not in mt and 'ctc-posml' not in mt:
                mimetypes.add(mt)
        mimetypes.discard('application/octet-stream')
        mimetypes = sorted(mimetypes)

        def write_mimetypes(f, extra=''):
            line = 'MimeType={};'.format(';'.join(mimetypes))
            if extra:
                line += extra + ';'
            f.write(line.encode('utf-8') + b'\n')

        from calibre.ebooks.oeb.polish.import_book import IMPORTABLE
        from calibre.ebooks.oeb.polish.main import SUPPORTED
        with open('calibre-lrfviewer.desktop', 'wb') as f:
            f.write(VIEWER.encode('utf-8'))
        with open('calibre-ebook-viewer.desktop', 'wb') as f:
            f.write(EVIEWER.encode('utf-8'))
            write_mimetypes(f)
        with open('calibre-ebook-edit.desktop', 'wb') as f:
            f.write(ETWEAK.encode('utf-8'))
            mt = {guess_type('a.' + x.lower())[0] for x in (SUPPORTED|IMPORTABLE)} - {None, 'application/octet-stream'}
            mt = sorted(mt)
            f.write(('MimeType={};\n'.format(';'.join(mt))).encode('utf-8'))
        with open('calibre-gui.desktop', 'wb') as f:
            f.write(GUI.encode('utf-8'))
            write_mimetypes(f, 'x-scheme-handler/calibre')
        des = ('calibre-gui.desktop', 'calibre-lrfviewer.desktop',
                'calibre-ebook-viewer.desktop', 'calibre-ebook-edit.desktop')
        appdata = os.path.join(os.path.dirname(self.opts.staging_sharedir), 'metainfo')
        translators = None
        if not os.path.exists(appdata):
            try:
                os.mkdir(appdata)
            except Exception:
                self.warning(f'Failed to create {appdata} not installing appdata files')
        if os.path.exists(appdata) and not os.access(appdata, os.W_OK):
            self.warning(f'Do not have write permissions for {appdata} not installing appdata files')
        else:
            from calibre.utils.localization import get_all_translators
            translators = dict(get_all_translators())

        APPDATA = get_appdata()
        for x in des:
            cmd = ['xdg-desktop-menu', 'install', '--noupdate', './'+x]
            cc(' '.join(cmd), shell=True)
            self.menu_resources.append(x)
            ak = x.partition('.')[0]
            if ak in APPDATA and translators is not None and os.access(appdata, os.W_OK):
                self.appdata_resources.append(write_appdata(ak, APPDATA[ak], appdata, translators))

        MIME_BASE = 'calibre-mimetypes.xml'
        MIME = P(MIME_BASE)
        self.mime_resources.append(MIME_BASE)
        if not getattr(self.opts, 'staged_install', False):
            cc(['xdg-mime', 'install', MIME])
            cc(['xdg-desktop-menu', 'forceupdate'])
        else:
            from shutil import copyfile
            copyfile(MIME, os.path.join(env['XDG_DATA_DIRS'], 'mime', 'packages', MIME_BASE))
    # }}}


def option_parser():
    from calibre.utils.config import OptionParser
    parser = OptionParser()
    parser.add_option('--make-errors-fatal', action='store_true', default=False,
                      dest='fatal_errors', help='If set die on errors.')
    parser.add_option('--root', dest='staging_root', default='/usr',
            help='Prefix under which to install files')
    parser.add_option('--bindir', default=None, dest='staging_bindir',
        help='Location where calibre launcher scripts were installed. Typically /usr/bin')
    parser.add_option('--sharedir', default=None, dest='staging_sharedir',
        help='Location where calibre resources were installed, typically /usr/share/calibre')

    return parser


def options(option_parser):
    parser = option_parser()
    options = parser.option_list
    for group in parser.option_groups:
        options += group.option_list
    opts = []
    for opt in options:
        opts.extend(opt._short_opts)
        opts.extend(opt._long_opts)
    return opts


def opts_and_words(name, op, words, takes_files=False):
    opts  = '|'.join(options(op))
    words = '|'.join([w.replace("'", "\\'") for w in words])
    fname = name.replace('-', '_')
    return ('_'+fname+'()'+
f'''
{{
    local cur opts
    local IFS=$'|\\t'
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    opts="{opts}"
    words="{words}"

    case "${{cur}}" in
      -* )
         COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) )
         COMPREPLY=( $( echo ${{COMPREPLY[@]}} | sed 's/ /\\\\ /g' | tr '\\n' '\\t' ) )
         return 0
         ;;
      *  )
         COMPREPLY=( $(compgen -W "${{words}}" -- ${{cur}}) )
         COMPREPLY=( $( echo ${{COMPREPLY[@]}} | sed 's/ /\\\\ /g' | tr '\\n' '\\t' ) )
         return 0
         ;;
    esac

}}
complete -F _''' + fname + ' ' + name +'\n\n').encode('utf-8')


pics = ['bmp', 'gif', 'jpeg', 'jpg', 'png']  # keep sorted alphabetically


def opts_and_exts(name, op, exts, cover_opts=('--cover',), opf_opts=(),
                  file_map={}):
    opts = ' '.join(options(op))
    exts.extend([i.upper() for i in exts])
    exts='|'.join(sorted(exts))
    fname = name.replace('-', '_')
    spics = pics + [i.upper() for i in pics]
    spics = '|'.join(sorted(spics))
    special_exts_template = '''\
      %s )
           _filedir %s
           return 0
         ;;
    '''
    extras = []
    for eopts, eexts in ((cover_opts, '${pics}'), (opf_opts, "'@(opf)'")):
        for opt in eopts:
            extras.append(special_exts_template%(opt, eexts))
    extras = '\n'.join(extras)

    return ('_'+fname+'()'+
'''
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    opts="{opts}"
    pics="@({pics})"

    case "${{prev}}" in
{extras}
    esac

    case "${{cur}}" in
{extras}
      -* )
         COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) )
         return 0
         ;;
      *  )
        _filedir '@({exts})'
        return 0
        ;;
    esac

}}
complete -o filenames -F _'''.format(**dict(pics=spics,
    opts=opts, extras=extras, exts=exts)) + fname + ' ' + name +'\n\n').encode('utf-8')


VIEWER = '''\
[Desktop Entry]
Version=1.0
Type=Application
Name=LRF viewer
GenericName=Viewer for LRF files
Comment=Viewer for LRF files (SONY ebook format files)
TryExec=lrfviewer
Exec=lrfviewer %f
Icon=calibre-viewer
MimeType=application/x-sony-bbeb;
Categories=Office;Viewer;
Keywords=lrf;viewer;
'''

EVIEWER = '''\
[Desktop Entry]
Version=1.0
Type=Application
Name=E-book viewer
GenericName=Viewer for E-books
Comment=Viewer for E-books in all the major formats
TryExec=ebook-viewer
Exec=ebook-viewer --detach %f
Icon=calibre-viewer
Categories=Office;Viewer;
Keywords=epub;ebook;viewer;
'''

ETWEAK = '''\
[Desktop Entry]
Version=1.0
Type=Application
Name=E-book editor
GenericName=Editor for E-books
Comment=Edit E-books in various formats
TryExec=ebook-edit
Exec=ebook-edit --detach %f
Icon=calibre-ebook-edit
Categories=Office;WordProcessor
Keywords=epub;ebook;editor;
'''

GUI = '''\
[Desktop Entry]
Version=1.0
Type=Application
Name=calibre
GenericName=E-book library management
Comment=E-book library management: Convert, view, share, catalogue all your e-books
TryExec=calibre
Exec=calibre --detach %U
Icon=calibre-gui
Categories=Office;
X-GNOME-UsesNotifications=true
Keywords=epub;ebook;manager;
'''


def get_appdata():
    def _(x):
        return x  # Make sure the text below is not translated, but is marked for translation
    return {
        'calibre-gui': {
            'name':'calibre',
            'summary':_('The one stop solution to all your e-book needs'),
            'description':(
                _('calibre is the one stop solution to all your e-book needs.'),
                _('You can use calibre to catalog your books, fetch metadata for them automatically, convert them from and to all the various e-book formats, send them to your e-book reader devices, read the books on your computer, edit the books in a dedicated e-book editor and even make them available over the network with the built-in Content server. You can also download news and periodicals in e-book format from over a thousand different news and magazine websites.')  # noqa: E501
            ),
            'screenshots':(
                (1408, 792, 'https://lh4.googleusercontent.com/-bNE1hc_3pIc/UvHLwKPGBPI/AAAAAAAAASA/8oavs_c6xoU/w1408-h792-no/main-default.png',),
                (1408, 792, 'https://lh4.googleusercontent.com/-Zu2httSKABE/UvHMYK30JJI/AAAAAAAAATg/dQTQUjBvV5s/w1408-h792-no/main-grid.png'),
                (1408, 792, 'https://lh3.googleusercontent.com/-_trYUjU_BaY/UvHMYSdKhlI/AAAAAAAAATc/auPA3gyXc6o/w1408-h792-no/main-flow.png'),
            ),
            'desktop-id': 'calibre-gui.desktop',
            'include-releases': True,
        },

        'calibre-ebook-edit': {
            'name':'calibre - E-book Editor',
            'summary':_('Edit the text and styles inside e-books'),
            'description':(
                _('The calibre E-book editor allows you to edit the text and styles inside the book with a live preview of your changes.'),
                _('It can edit books in both the EPUB and AZW3 (Kindle) formats. It includes various useful tools for checking the book for errors, editing the Table of Contents, performing automated cleanups, etc.'),  # noqa: E501
            ),
            'screenshots':(
                (1408, 792, 'https://lh5.googleusercontent.com/-M2MAVc3A8e4/UvHMWqGRa8I/AAAAAAAAATA/cecQeWUYBVs/w1408-h792-no/edit-default.png',),
                (1408, 792, 'https://lh4.googleusercontent.com/-WhoMxuRb34c/UvHMWqN8aGI/AAAAAAAAATI/8SDBYWXb7-8/w1408-h792-no/edit-check.png'),
                (887, 575, 'https://lh6.googleusercontent.com/-KwaOwHabnBs/UvHMWidjyXI/AAAAAAAAAS8/H6xmCeLnSpk/w887-h575-no/edit-toc.png'),
            ),
            'desktop-id': 'calibre-ebook-edit.desktop',
        },

        'calibre-ebook-viewer': {
            'name':'calibre - E-book Viewer',
            'summary':_('Read e-books in over a dozen different formats'),
            'description': (
                _('The calibre E-book viewer allows you to read e-books in over a dozen different formats.'),
                _('It has a full screen mode for distraction free reading and can display the text with multiple columns per screen.'),
            ),
            'screenshots':(
                (1408, 792, 'https://lh5.googleusercontent.com/-dzSO82BPpaE/UvHMYY5SpNI/AAAAAAAAATk/I_kF9fYWrZM/w1408-h792-no/viewer-default.png',),
                (1920, 1080, 'https://lh6.googleusercontent.com/-n32Ae5RytAk/UvHMY0QD94I/AAAAAAAAATs/Zw8Yz08HIKk/w1920-h1080-no/viewer-fs.png'),
            ),
            'desktop-id': 'calibre-ebook-viewer.desktop',
        },
    }


def changelog_bullet_to_text(bullet):
    # It would be great if we could use any fancier formatting here, but the
    # only allowed inline formatting within the AppData description bullet
    # points are emphasis (italics) and code (monospaced font)
    text = [bullet['title']]
    if 'author' in bullet:
        text.append(' by ')
        text.append(bullet['author'])
    if 'description' in bullet or 'tickets' in bullet:
        text.append(' (')
        if 'description' in bullet:
            text.append(bullet['description'])
        if 'tickets' in bullet:
            if 'description' in bullet:
                text.append(' – ')
            text.append('Closes tickets: ')
            text.append(', '.join(map(str, bullet['tickets'])))
        text.append(')')
    return ''.join(text)


def make_appdata_releases():
    import json

    from lxml.builder import E
    changelog = json.loads(P('changelog.json', data=True))

    releases = E.releases()
    for revision in changelog:
        # Formatting of release description tries to resemble that of
        # https://calibre-ebook.com/whats-new while taking into account the limits imposed by
        # https://www.freedesktop.org/software/appstream/docs/chap-Metadata.html#tag-description
        description = E.description()
        if 'new features' in revision:
            description.append(E.p('New features:'))
            description.append(E.ol(
                *(E.li(changelog_bullet_to_text(bullet)) for bullet in revision['new features'])
            ))
        if 'bug fixes' in revision:
            description.append(E.p('Bug fixes:'))
            description.append(E.ol(
                *(E.li(changelog_bullet_to_text(bullet)) for bullet in revision['bug fixes'])
            ))
        if 'new recipes' in revision:
            description.append(E.p('New news sources:'))
            description.append(E.ol(
                *(E.li(changelog_bullet_to_text(bullet)) for bullet in revision['new recipes'])
            ))
        if 'improved recipes' in revision:
            description.append(E.p('Improved news sources:'))
            description.append(E.ol(
                *(E.li(name) for name in revision['improved recipes'])
            ))
        releases.append(E.release(
            description,
            version=revision['version'],
            date=revision['date']
        ))
    return releases


def write_appdata(key, entry, base, translators):
    from lxml.builder import E
    from lxml.etree import tostring
    fpath = os.path.join(base, f'{key}.metainfo.xml')
    screenshots = E.screenshots()
    for w, h, url in entry['screenshots']:
        s = E.screenshot(E.image(url, width=str(w), height=str(h)))
        screenshots.append(s)
    screenshots[0].set('type', 'default')
    description = E.description()
    for para in entry['description']:
        description.append(E.p(para))
        for lang, t in iteritems(translators):
            tp = t.gettext(para)
            if tp != para:
                description.append(E.p(tp, **{'{http://www.w3.org/XML/1998/namespace}lang': lang}))

    root = E.component(
        E.id(key + '.desktop'),
        E.name(entry['name']),
        E.metadata_license('CC0-1.0'),
        E.project_license('GPL-3.0'),
        E.developer(E.name('Kovid Goyal'), id='kovidgoyal.net'),
        E.summary(entry['summary']),
        E.content_rating(
            # Information Sharing: Using any online API, e.g. a user-counter
            # Details at https://calibre-ebook.com/dynamic/calibre-usage .
            E.content_attribute('mild', id='social-info'),
            # In-App Purchases: Users are encouraged to donate real money, e.g. using Patreon
            E.content_attribute('mild', id='money-purchasing'),
            type='oars-1.1'
        ),
        description,
        E.url('https://calibre-ebook.com/', type='homepage'),
        screenshots,
        E.launchable(entry['desktop-id'], type='desktop-id'),
        type='desktop-application'
    )
    for lang, t in iteritems(translators):
        tp = t.gettext(entry['summary'])
        if tp != entry['summary']:
            root.append(E.summary(tp, **{'{http://www.w3.org/XML/1998/namespace}lang': lang}))
    if entry.get('include-releases', False):
        try:
            root.append(make_appdata_releases())
        except Exception:
            import traceback
            traceback.print_exc()
    with open(fpath, 'wb') as f:
        f.write(tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=True))
    return fpath


def render_img(image, dest, width=128, height=128):
    from qt.core import QImage, Qt
    img = QImage(I(image)).scaled(int(width), int(height), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    img.save(dest)


def main():
    p = option_parser()
    opts, args = p.parse_args()
    PostInstall(opts)
    return 0


def cli_index_strings():
    return _('Command Line Interface'), _(
        'On macOS, the command line tools are inside the calibre bundle, for example,'
    ' if you installed calibre in :file:`/Applications` the command line tools'
        ' are in :file:`/Applications/calibre.app/Contents/MacOS/`. So, for example, to run :file:`ebook-convert`'
        ' you would use: :file:`/Applications/calibre.app/Contents/MacOS/ebook-convert`.'), _(
        'Documented commands'), _('Undocumented commands'), _(
        'You can see usage for undocumented commands by executing them without arguments in a terminal.'), _(
            'Change language'), _('Search')


if __name__ == '__main__':
    sys.exit(main())
