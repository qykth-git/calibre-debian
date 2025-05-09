#!/usr/bin/env python


__license__ = 'GPL v3'
__copyright__ = '2015, Kovid Goyal <kovid at kovidgoyal.net>'

import mimetypes
import os
import re
import subprocess
from collections import defaultdict
from plistlib import loads

from calibre.ptempfile import TemporaryDirectory
from calibre.utils.icu import numeric_sort_key
from polyglot.builtins import iteritems, string_or_bytes

application_locations = ('/Applications', '~/Applications', '~/Desktop')


# Public UTI MAP {{{

def generate_public_uti_map():
    from html5_parser import parse
    from lxml import etree

    from polyglot.urllib import urlopen
    raw = urlopen(
        'https://developer.apple.com/library/ios/documentation/Miscellaneous/Reference/UTIRef/Articles/System-DeclaredUniformTypeIdentifiers.html').read()
    root = parse(raw)
    tables = root.xpath('//table')[0::2]
    data = {}
    for table in tables:
        for tr in table.xpath('descendant::tr')[1:]:
            td = tr.xpath('descendant::td')
            identifier = etree.tostring(td[0], method='text', encoding='unicode').strip()
            tags = etree.tostring(td[2], method='text', encoding='unicode').strip()
            identifier = identifier.split()[0].replace('\u200b', '')
            exts = [x.strip()[1:].lower() for x in tags.split(',') if x.strip().startswith('.')]
            for ext in exts:
                data[ext] = identifier
    lines = ['PUBLIC_UTI_MAP = {']
    for ext in sorted(data):
        r = ("'" + ext + "':").ljust(16)
        lines.append((' ' * 4) + r + "'" + data[ext] + "',")
    lines.append('}')
    with open(__file__, 'r+b') as f:
        raw = f.read()
        f.seek(0)
        nraw = re.sub(r'^PUBLIC_UTI_MAP = .+?}', '\n'.join(lines), raw, flags=re.MULTILINE | re.DOTALL)
        f.truncate(), f.write(nraw)


# Generated by generate_public_uti_map()
PUBLIC_UTI_MAP = {
    '3g2':          'public.3gpp2',
    '3gp':          'public.3gpp',
    '3gp2':         'public.3gpp2',
    '3gpp':         'public.3gpp',
    'ai':           'com.adobe.illustrator.ai-image',
    'aif':          'public.aiff-audio',
    'aifc':         'public.aifc-audio',
    'aiff':         'public.aiff-audio',
    'app':          'com.apple.application-bundle',
    'applescript':  'com.apple.applescript.text',
    'asf':          'com.microsoft.advanced-systems-format',
    'asx':          'com.microsoft.advanced-stream-redirector',
    'au':           'public.ulaw-audio',
    'avi':          'public.avi',
    'bin':          'com.apple.macbinary-archive',
    'bmp':          'com.microsoft.bmp',
    'bundle':       'com.apple.bundle',
    'c':            'public.c-source',
    'c++':          'public.c-plus-plus-source',
    'caf':          'com.apple.coreaudio-format',
    'cc':           'public.c-plus-plus-source',
    'class':        'com.sun.java-class',
    'command':      'public.shell-script',
    'cp':           'public.c-plus-plus-source',
    'cpio':         'public.cpio-archive',
    'cpp':          'public.c-plus-plus-source',
    'csh':          'public.csh-script',
    'cxx':          'public.c-plus-plus-source',
    'defs':         'public.mig-source',
    'dfont':        'com.apple.truetype-datafork-suitcase-font',
    'dll':          'com.microsoft.windows-dynamic-link-library',
    'doc':          'com.microsoft.word.doc',
    'efx':          'com.js.efx-fax',
    'eps':          'com.adobe.encapsulated-postscript',
    'exe':          'com.microsoft.windows-executable',
    'exp':          'com.apple.symbol-export',
    'exr':          'com.ilm.openexr-image',
    'fpx':          'com.kodak.flashpix.image',
    'framework':    'com.apple.framework',
    'gif':          'com.compuserve.gif',
    'gtar':         'org.gnu.gnu-tar-archive',
    'gz':           'org.gnu.gnu-zip-archive',
    'gzip':         'org.gnu.gnu-zip-archive',
    'h':            'public.c-header',
    'h++':          'public.c-plus-plus-header',
    'hpp':          'public.c-plus-plus-header',
    'hqx':          'com.apple.binhex-archive',
    'htm':          'public.html',
    'html':         'public.html',
    'hxx':          'public.c-plus-plus-header',
    'icc':          'com.apple.colorsync-profile',
    'icm':          'com.apple.colorsync-profile',
    'icns':         'com.apple.icns',
    'ico':          'com.microsoft.ico',
    'jar':          'com.sun.java-archive',
    'jav':          'com.sun.java-source',
    'java':         'com.sun.java-source',
    'javascript':   'com.netscape.javascript-source',
    'jfx':          'com.j2.jfx-fax',
    'jnlp':         'com.sun.java-web-start',
    'jp2':          'public.jpeg-2000',
    'jpeg':         'public.jpeg',
    'jpg':          'public.jpeg',
    'js':           'com.netscape.javascript-source',
    'jscript':      'com.netscape.javascript-source',
    'key':          'com.apple.keynote.key',
    'kth':          'com.apple.keynote.kth',
    'm':            'public.objective-c-source',
    'm15':          'public.mpeg',
    'm4a':          'public.mpeg-4-audio',
    'm4b':          'com.apple.protected-mpeg-4-audio',
    'm4p':          'com.apple.protected-mpeg-4-audio',
    'm75':          'public.mpeg',
    'mdimporter':   'com.apple.metadata-importer',
    'mig':          'public.mig-source',
    'mm':           'public.objective-c-plus-plus-source',
    'mov':          'com.apple.quicktime-movie',
    'mp3':          'public.mp3',
    'mp4':          'public.mpeg-4',
    'mpeg':         'public.mpeg',
    'mpg':          'public.mpeg',
    'o':            'public.object-code',
    'otf':          'public.opentype-font',
    'pct':          'com.apple.pict',
    'pdf':          'com.adobe.pdf',
    'pf':           'com.apple.colorsync-profile',
    'pfa':          'com.adobe.postscript.pfa-font',
    'pfb':          'com.adobe.postscript-pfb-font',
    'ph3':          'public.php-script',
    'ph4':          'public.php-script',
    'php':          'public.php-script',
    'php3':         'public.php-script',
    'php4':         'public.php-script',
    'phtml':        'public.php-script',
    'pic':          'com.apple.pict',
    'pict':         'com.apple.pict',
    'pl':           'public.perl-script',
    'plugin':       'com.apple.plugin',
    'pm':           'public.perl-script',
    'png':          'public.png',
    'pntg':         'com.apple.macpaint-image',
    'ppt':          'com.microsoft.powerpoint.ppt',
    'ps':           'com.adobe.postscript',
    'psd':          'com.adobe.photoshop-image',
    'py':           'public.python-script',
    'qif':          'com.apple.quicktime-image',
    'qt':           'com.apple.quicktime-movie',
    'qtif':         'com.apple.quicktime-image',
    'qtz':          'com.apple.quartz-composer-composition',
    'r':            'com.apple.rez-source',
    'ra':           'com.real.realaudio',
    'ram':          'com.real.realaudio',
    'rb':           'public.ruby-script',
    'rbw':          'public.ruby-script',
    'rm':           'com.real.realmedia',
    'rtf':          'public.rtf',
    'rtfd':         'com.apple.rtfd',
    's':            'public.assembly-source',
    'scpt':         'com.apple.applescript.script',
    'sd2':          'com.digidesign.sd2-audio',
    'sgi':          'com.sgi.sgi-image',
    'sh':           'public.shell-script',
    'sit':          'com.allume.stuffit-archive',
    'sitx':         'com.allume.stuffit-archive',
    'smil':         'com.real.smil',
    'snd':          'public.ulaw-audio',
    'suit':         'com.apple.font-suitcase',
    'tar':          'public.tar-archive',
    'tga':          'com.truevision.tga-image',
    'tgz':          'org.gnu.gnu-zip-tar-archive',
    'tif':          'public.tiff',
    'tiff':         'public.tiff',
    'ttc':          'public.truetype-collection-font',
    'ttf':          'public.truetype-ttf-font',
    'txt':          'public.plain-text',
    'ulw':          'public.ulaw-audio',
    'vcard':        'public.vcard',
    'vcf':          'public.vcard',
    'vfw':          'public.avi',
    'wav':          'com.microsoft.waveform-audio',
    'wave':         'com.microsoft.waveform-audio',
    'wax':          'com.microsoft.windows-media-wax',
    'wdgt':         'com.apple.dashboard-widget',
    'wm':           'com.microsoft.windows-media-wm',
    'wma':          'com.microsoft.windows-media-wma',
    'wmp':          'com.microsoft.windows-media-wmp',
    'wmv':          'com.microsoft.windows-media-wmv',
    'wmx':          'com.microsoft.windows-media-wmx',
    'wvx':          'com.microsoft.windows-media-wvx',
    'xbm':          'public.xbitmap-image',
    'xls':          'com.microsoft.excel.xls',
    'xml':          'public.xml',
    'zip':          'com.pkware.zip-archive',
}
PUBLIC_UTI_RMAP = defaultdict(set)
for ext, uti in iteritems(PUBLIC_UTI_MAP):
    PUBLIC_UTI_RMAP[uti].add(ext)
PUBLIC_UTI_RMAP = dict(PUBLIC_UTI_RMAP)

# }}}


def find_applications_in(base):
    try:
        entries = os.listdir(base)
    except OSError:
        return
    for name in entries:
        path = os.path.join(base, name)
        if os.path.isdir(path):
            if name.lower().endswith('.app'):
                yield path
            else:
                yield from find_applications_in(path)


def find_applications():
    for base in application_locations:
        base = os.path.expanduser(base)
        yield from find_applications_in(base)


def get_extensions_from_utis(utis, plist):
    declared_utis = defaultdict(set)
    for key in ('UTExportedTypeDeclarations', 'UTImportedTypeDeclarations'):
        for decl in plist.get(key, ()):
            if isinstance(decl, dict):
                uti = decl.get('UTTypeIdentifier')
                if isinstance(uti, string_or_bytes):
                    spec = decl.get('UTTypeTagSpecification')
                    if isinstance(spec, dict):
                        ext = spec.get('public.filename-extension')
                        if ext:
                            declared_utis[uti] |= set(ext)
                        types = spec.get('public.mime-type')
                        if types:
                            for mt in types:
                                for ext in mimetypes.guess_all_extensions(mt, strict=False):
                                    declared_utis[uti].add(ext.lower()[1:])
    ans = set()
    for uti in utis:
        ans |= declared_utis[uti]
        ans |= PUBLIC_UTI_RMAP.get(uti, set())
    return ans


def get_bundle_data(path):
    path = os.path.abspath(path)
    info = os.path.join(path, 'Contents', 'Info.plist')
    ans = {
        'name': os.path.splitext(os.path.basename(path))[0],
        'path': path,
    }
    try:
        with open(info, 'rb') as f:
            plist = loads(f.read())
    except Exception:
        import traceback
        traceback.print_exc()
        return None
    ans['name'] = plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ans['name']
    icfile = plist.get('CFBundleIconFile')
    if icfile:
        icfile = os.path.join(path, 'Contents', 'Resources', icfile)
        if not os.path.exists(icfile):
            icfile += '.icns'
        if os.path.exists(icfile):
            ans['icon_file'] = icfile
    bid = plist.get('CFBundleIdentifier')
    if bid:
        ans['identifier'] = bid
    ans['extensions'] = extensions = set()
    for dtype in plist.get('CFBundleDocumentTypes', ()):
        utis = frozenset(dtype.get('LSItemContentTypes', ()))
        if utis:
            extensions |= get_extensions_from_utis(utis, plist)
        else:
            for ext in dtype.get('CFBundleTypeExtensions', ()):
                if isinstance(ext, string_or_bytes):
                    extensions.add(ext.lower())
            for mt in dtype.get('CFBundleTypeMIMETypes', ()):
                if isinstance(mt, string_or_bytes):
                    for ext in mimetypes.guess_all_extensions(mt, strict=False):
                        extensions.add(ext.lower())
    return ans


def find_programs(extensions):
    extensions = frozenset(extensions)
    ans = []
    for app in find_applications():
        try:
            app = get_bundle_data(app)
        except Exception:
            import traceback
            traceback.print_exc()
            continue
        if app and app['extensions'].intersection(extensions):
            ans.append(app)
    return ans


def get_icon(path, pixmap_to_data=None, as_data=False, size=64):
    if not path:
        return
    with TemporaryDirectory() as tdir:
        iconset = os.path.join(tdir, 'output.iconset')
        try:
            subprocess.check_call(['iconutil', '-c', 'iconset', '-o', 'output.iconset', path], cwd=tdir)
        except subprocess.CalledProcessError:
            return
        try:
            names = os.listdir(iconset)
        except OSError:
            return
        if not names:
            return
        from qt.core import QImage, Qt
        names.sort(key=numeric_sort_key)
        for name in names:
            m = re.search(r'(\d+)x\d+', name)
            if m is not None and int(m.group(1)) >= size:
                ans = QImage(os.path.join(iconset, name))
                if not ans.isNull():
                    break
        else:
            return
    ans = ans.scaled(size, size, transformMode=Qt.TransformationMode.SmoothTransformation)
    if as_data:
        ans = pixmap_to_data(ans)
    return ans


def entry_to_cmdline(entry, path):
    app = entry['path']
    if os.path.isdir(app):
        return ['open', '-a', app, path]
    if 'identifier' in entry:
        return ['open', '-b', entry['identifier'], path]
    return [app, path]
