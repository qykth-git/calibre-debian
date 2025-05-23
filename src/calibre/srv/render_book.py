#!/usr/bin/env python
# License: GPLv3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>


import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from itertools import count

from lxml.etree import Comment

from calibre import detect_ncpus, prepare_string_for_xml
from calibre.customize.ui import plugin_for_input_format
from calibre.ebooks.oeb.base import EPUB, OEB_DOCS, OEB_STYLES, OPF, SMIL, XHTML, XHTML_NS, XLINK, rewrite_links, urlunquote
from calibre.ebooks.oeb.base import XPath as _XPath
from calibre.ebooks.oeb.iterator.book import extract_book
from calibre.ebooks.oeb.polish.container import Container as ContainerBase
from calibre.ebooks.oeb.polish.cover import find_cover_image, find_cover_image_in_page, find_cover_page
from calibre.ebooks.oeb.polish.toc import from_xpaths, get_landmarks, get_toc
from calibre.ebooks.oeb.polish.utils import guess_type
from calibre.srv.metadata import encode_datetime
from calibre.utils.date import EPOCH
from calibre.utils.forked_map import forked_map, forked_map_is_supported
from calibre.utils.logging import default_log
from calibre.utils.serialize import json_dumps, json_loads, msgpack_loads
from calibre.utils.short_uuid import uuid4
from calibre_extensions.fast_css_transform import transform_properties
from polyglot.binary import as_base64_unicode as encode_component
from polyglot.binary import from_base64_bytes
from polyglot.binary import from_base64_unicode as decode_component
from polyglot.builtins import as_bytes
from polyglot.urllib import urlparse

try:
    from calibre_extensions.speedup import get_num_of_significant_chars
except ImportError:  # running from source without updated binary
    def get_num_of_significant_chars(elem):
        return len(getattr(elem, 'text', '') or '') + len(getattr(elem, 'tail', '') or '')
RENDER_VERSION = 1

BLANK_JPEG = b'\xff\xd8\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc9\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xcc\x00\x06\x00\x10\x10\x05\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'  # noqa: E501


class Spineless(ValueError):
    pass


def XPath(expr):
    ans = XPath.cache.get(expr)
    if ans is None:
        ans = XPath.cache[expr] = _XPath(expr)
    return ans


XPath.cache = {}


def encode_url(name, frag=''):
    name = encode_component(name)
    if frag:
        name += '#' + frag
    return name


def decode_url(x):
    parts = x.split('#', 1)
    return decode_component(parts[0]), (parts[1] if len(parts) > 1 else '')


def create_link_replacer(container, link_uid, changed):
    resource_template = link_uid + '|{}|'

    def link_replacer(base, url):
        if url.startswith('#'):
            frag = urlunquote(url[1:])
            changed.add(base)
            if not frag:
                return link_uid
            return resource_template.format(encode_url(base, frag))
        try:
            purl = urlparse(url)
        except Exception:
            return url
        if purl.netloc or purl.query:
            return url
        if purl.scheme and purl.scheme != 'file':
            return url
        if not purl.path or purl.path.startswith('/'):
            return url
        url, frag = purl.path, purl.fragment
        name = container.href_to_name(url, base)
        if name:
            if container.has_name_and_is_not_empty(name):
                frag = urlunquote(frag)
                url = resource_template.format(encode_url(name, frag))
            else:
                url = 'missing:' + name
            changed.add(base)
        return url

    return link_replacer


def check_for_maths(root):
    for x in root.iterdescendants('{*}math'):
        return True
    for s in root.iterdescendants(XHTML('script')):
        if s.get('type') == 'text/x-mathjax-config':
            return True
    return False


def has_ancestor(elem, q):
    while elem is not None:
        elem = elem.getparent()
        if elem is q:
            return True
    return False


def anchor_map(root):
    ans = []
    seen = set()
    for elem in root.xpath('//*[@id or @name]'):
        eid = elem.get('id')
        if not eid and elem.tag.endswith('}a'):
            eid = elem.get('name')
            if eid:
                elem.set('id', eid)
        if eid and eid not in seen:
            ans.append(eid)
            seen.add(eid)
    return ans


def get_length(root):
    ans = 0
    for body in root.iterchildren(XHTML('body')):
        ans += get_num_of_significant_chars(body)
        for elem in body.iterdescendants():
            ans += get_num_of_significant_chars(elem)
    return ans


def toc_anchor_map(toc):
    ans = defaultdict(list)
    seen_map = defaultdict(set)

    def process_node(node):
        name = node['dest']
        if name and node['id'] not in seen_map[name]:
            ans[name].append({'id':node['id'], 'frag':node['frag']})
            seen_map[name].add(node['id'])
        for i in node['children']:
            process_node(i)

    process_node(toc)
    return dict(ans)


def pagelist_anchor_map(page_list):
    ans = defaultdict(list)
    seen_map = defaultdict(set)
    for i, x in enumerate(page_list):
        x['id'] = i + 1
        name = x['dest']
        frag = x['frag']
        if name and frag not in seen_map[name]:
            ans[name].append({'id': x['id'], 'pagenum': x['pagenum'], 'frag':frag})
            seen_map[name].add(frag)
    return dict(ans)


class SimpleContainer(ContainerBase):

    tweak_mode = True


def find_epub_cover(container):
    cover_image = find_cover_image(container)
    marked_title_page = find_cover_page(container)
    cover_image_in_first_page = None
    try:
        first_page_name = next(container.spine_names)[0]
    except StopIteration:
        return None, None
    if not marked_title_page:
        cover_image_in_first_page = find_cover_image_in_page(container, first_page_name)

    has_epub_cover = cover_image or marked_title_page or cover_image_in_first_page
    if not has_epub_cover:
        return None, None
    if marked_title_page and cover_image:
        return marked_title_page, cover_image

    if marked_title_page:
        if cover_image:
            return marked_title_page, cover_image
        cover_image = find_cover_image_in_page(container, marked_title_page)
        if cover_image:
            return marked_title_page, cover_image
        return None, None

    if cover_image_in_first_page:
        return first_page_name, cover_image_in_first_page

    return None, None


def create_cover_page(container, input_fmt, is_comic, book_metadata=None):
    templ = '''
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
    <head><style>
    html, body, img { height: 100vh; display: block; margin: 0; padding: 0; border-width: 0; }
    img {
        width: 100%%; height: 100%%;
        object-fit: contain;
        margin-left: auto; margin-right: auto;
        max-width: 100vw; max-height: 100vh;
        top: 50vh; transform: translateY(-50%%);
        position: relative;
    }
    body.cover-fill img { object-fit: fill; }
    </style></head><body><img src="%s"/></body></html>
    '''

    def generic_cover():
        if book_metadata is not None:
            from calibre.ebooks.covers import create_cover
            mi = book_metadata
            return create_cover(mi.title, mi.authors, mi.series, mi.series_index)
        return BLANK_JPEG

    if input_fmt == 'epub':
        titlepage_name, raster_cover_name = find_epub_cover(container)
        if raster_cover_name and titlepage_name:
            raw = templ % prepare_string_for_xml(container.name_to_href(raster_cover_name, titlepage_name), True)
            with container.open(titlepage_name, 'wb') as f:
                f.write(raw.encode('utf-8'))
    else:
        raster_cover_name = find_cover_image(container, strict=True)
        if raster_cover_name is None:
            return None, None
        if is_comic:
            return raster_cover_name, None
        item = container.generate_item(name='titlepage.html', id_prefix='titlepage')
        titlepage_name = container.href_to_name(item.get('href'), container.opf_name)
        raw = templ % prepare_string_for_xml(container.name_to_href(raster_cover_name, titlepage_name), True)
        with container.open(titlepage_name, 'wb') as f:
            f.write(raw.encode('utf-8'))
        spine = container.opf_xpath('//opf:spine')[0]
        ref = spine.makeelement(OPF('itemref'), idref=item.get('id'))
        container.insert_into_xml(spine, ref, index=0)
    return raster_cover_name, titlepage_name


def transform_style_sheet(container, name, link_uid, virtualize_resources, virtualized_names):
    changed = False
    link_replacer = None
    if virtualize_resources:
        changed_names = set()
        link_replacer = partial(create_link_replacer(container, link_uid, changed_names), name)
    raw = container.raw_data(name, decode=True)
    nraw = transform_properties(raw, is_declaration=False, url_callback=link_replacer)
    if virtualize_resources:
        if name in changed_names:
            changed = True
            virtualized_names.add(name)
    if nraw != raw:
        changed = True
        raw = nraw
    raw = raw.lstrip()
    if not raw.startswith('@charset'):
        raw = '@charset "UTF-8";\n' + raw
        changed = True
    if changed:
        with container.open(name, 'wb') as f:
            f.write(raw.encode('utf-8'))


def transform_svg_image(container, name, link_uid, virtualize_resources, virtualized_names):
    if not virtualize_resources:
        return
    link_replacer = create_link_replacer(container, link_uid, set())
    xlink = XLINK('href')
    altered = False
    xlink_xpath = XPath('//*[@xl:href]')
    for elem in xlink_xpath(container.parsed(name)):
        href = elem.get(xlink)
        if not href.startswith('#'):
            elem.set(xlink, link_replacer(name, href))
            altered = True
    if altered:
        virtualized_names.add(name)
        container.dirty(name)
        container.commit_item(name)


def parse_smil_time(x):
    # https://www.w3.org/TR/SMIL3/smil-timing.html#q22
    parts = x.split(':')
    seconds = 0
    if len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
        seconds = abs(hours) * 3600 + max(0, min(abs(minutes), 59)) * 60 + max(0, min(abs(seconds), 59))
    elif len(parts) == 2:
        minutes, seconds = int(parts[0]), float(parts[1])
        seconds = max(0, min(abs(minutes), 59)) * 60 + max(0, min(abs(seconds), 59))
    elif len(parts) == 1:
        if x.endswith('s'):
            seconds = float(x[:-1])
        elif x.endswith('ms'):
            seconds = float(x[:-2]) * 0.001
        elif x.endswith('min'):
            seconds = float(x[:-3]) * 60
        elif x.endswith('h'):
            seconds = float(x[:-1]) * 3600
        else:
            raise ValueError(f'Malformed SMIL time: {x}')
    else:
        raise ValueError(f'Malformed SMIL time: {x}')
    return seconds


def transform_smil(container, name, link_uid, virtualize_resources, virtualized_names, smil_map):
    root = container.parsed(name)
    text_tag, audio_tag = SMIL('text'), SMIL('audio')
    body_tag, seq_tag, par_tag = SMIL('body'), SMIL('seq'), SMIL('par')
    type_attr, textref_attr = EPUB('type'), EPUB('textref')
    parnum = 0

    def make_par(par, target):
        nonlocal parnum
        parnum += 1
        ans = {'num': parnum}
        t = par.get(type_attr)
        if t:
            ans['type'] = t
        for child in par.iterchildren('*'):
            if child.tag == text_tag:
                src = child.get('src')
                if src:
                    q = container.href_to_name(src, name)
                    if q != target:
                        return {}  # the par must match the textref of the parent seq
                    ans['anchor'] = src.partition('#')[2]
            elif child.tag == audio_tag:
                src = child.get('src')
                if src:
                    ans['audio'] = container.href_to_name(src, name)
                    b, e = child.get('clipBegin'), child.get('clipEnd')
                    if b:
                        ans['start'] = parse_smil_time(b)
                    if e:
                        ans['end'] = parse_smil_time(e)
        return ans

    def process_seq(seq_xml_element, tref, parent_seq=None):
        target = container.href_to_name(tref, name)
        seq = {'textref': [target, tref.partition('#')[2]], 'par': [], 'seq': []}
        t = seq_xml_element.get(type_attr)
        if t:
            seq['type'] = t
        if parent_seq is None:
            parent_seq = smil_map.get(target)
            if parent_seq is None:
                smil_map[target] = parent_seq = {'textref': [target, ''], 'par':[], 'seq':[], 'type': 'root'}
        else:
            if parent_seq['textref'][0] != target:
                return  # child seqs must be in the same HTML file as parent
        parent_seq['seq'].append(seq)
        for child in seq_xml_element.iterchildren('*'):
            if child.tag == par_tag:
                p = make_par(child, target)
                if p.get('audio'):
                    seq['par'].append(p)
            elif child.tag == seq_tag:
                tref = child.get(textref_attr)
                if tref:
                    process_seq(child, tref, seq)
        if not seq['par']:
            del seq['par']
        if not seq['seq']:
            del seq['seq']

    for child in root.iterchildren('*'):
        if child.tag == body_tag:
            tref = child.get(textref_attr)
            if tref:
                process_seq(child, tref)
            else:
                for gc in child.iterchildren('*'):
                    if gc.tag == seq_tag:
                        tref = gc.get(textref_attr)
                        if tref:
                            process_seq(gc, tref)


def transform_inline_styles(container, name, transform_sheet, transform_style):
    root = container.parsed(name)
    changed = False
    for style in root.xpath('//*[local-name()="style"]'):
        if style.text and (style.get('type') or 'text/css').lower() == 'text/css':
            nraw = transform_sheet(style.text)
            if nraw != style.text:
                changed = True
                style.text = nraw
    for elem in root.xpath('//*[@style]'):
        text = elem.get('style', None)
        if text:
            ntext = transform_style(text)
            if ntext != text:
                changed = True
                elem.set('style', ntext)
    return changed


def transform_html(container, name, virtualize_resources, link_uid, link_to_map, virtualized_names):
    link_xpath = XPath('//h:*[@href and (self::h:a or self::h:area)]')
    svg_link_xpath = XPath('//svg:a')
    img_xpath = XPath('//h:img[@src]')
    svg_img_xpath = XPath('//svg:image[@xl:href]')
    res_link_xpath = XPath('//h:link[@href]')
    root = container.parsed(name)
    changed_names = set()
    link_replacer = create_link_replacer(container, link_uid, changed_names)

    # Used for viewing images
    for img in img_xpath(root):
        img_name = container.href_to_name(img.get('src'), name)
        if img_name:
            img.set('data-calibre-src', img_name)
    for img in svg_img_xpath(root):
        img_name = container.href_to_name(img.get(XLINK('href')), name)
        if img_name:
            img.set('data-calibre-src', img_name)

    # Disable non-stylesheet link tags. This link will not be loaded by the
    # browser anyway and will causes the resource load check to hang
    for link in res_link_xpath(root):
        ltype = (link.get('type') or 'text/css').lower()
        rel = (link.get('rel') or 'stylesheet').lower()
        if ltype != 'text/css' or rel != 'stylesheet':
            link.attrib.clear()

    # URLs in the inline CSS will be replaced in virtualize_html
    def transform_sheet(sheet_text):
        ans = transform_properties(sheet_text, is_declaration=False)
        if name in changed_names:
            virtualized_names.add(name)
        return ans

    def transform_declaration(decl_text):
        ans = transform_properties(decl_text, is_declaration=True)
        if name in changed_names:
            virtualized_names.add(name)
        return ans

    # Transform <style> and style=""
    transform_inline_styles(container, name, transform_sheet=transform_sheet, transform_style=transform_declaration)

    if virtualize_resources:
        virtualize_html(container, name, link_uid, link_to_map, virtualized_names)
    else:

        def handle_link(a, attr='href'):
            href = a.get(attr)
            if href:
                href = link_replacer(name, href)
            elif attr in a.attrib:
                a.set(attr, 'javascript:void(0)')
            if href:
                if href.startswith(link_uid):
                    a.set(attr, 'javascript:void(0)')
                    parts = href.split('|')
                    if len(parts) > 1:
                        parts = decode_url(parts[1])
                        lname, lfrag = parts[0], parts[1]
                        link_to_map.setdefault(lname, {}).setdefault(lfrag or '', set()).add(name)
                        a.set('data-' + link_uid, json.dumps({'name':lname, 'frag':lfrag}, ensure_ascii=False))
                elif href.startswith('missing:'):
                    a.set(attr, 'javascript:void(0)')
                    a.set('data-' + link_uid, json.dumps({'name':href[len('missing:'):], 'frag':'', 'missing': True}, ensure_ascii=False))

        for a in link_xpath(root):
            handle_link(a)
        xhref = XLINK('href')
        for a in svg_link_xpath(root):
            handle_link(a, xhref)

    shtml = html_as_json(root)
    with container.open(name, 'wb') as f:
        f.write(shtml)


def virtualize_html(container, name, link_uid, link_to_map, virtualized_names):

    changed = set()
    link_xpath = XPath('//h:*[@href and (self::h:a or self::h:area)]')
    svg_link_xpath = XPath('//svg:a')
    link_replacer = create_link_replacer(container, link_uid, changed)

    virtualized_names.add(name)
    root = container.parsed(name)
    rewrite_links(root, partial(link_replacer, name))

    def handle_link(a, attr='href'):
        href = a.get(attr) or ''
        if href.startswith(link_uid):
            a.set(attr, 'javascript:void(0)')
            try:
                parts = decode_url(href.split('|')[1])
            except IndexError:
                pass
            else:
                lname, lfrag = parts[0], parts[1]
                link_to_map.setdefault(lname, {}).setdefault(lfrag or '', set()).add(name)
                a.set('data-' + link_uid, json.dumps({'name':lname, 'frag':lfrag}, ensure_ascii=False))
        elif href:
            if href.startswith('missing:'):
                a.set(attr, 'javascript:void(0)')
                a.set('data-' + link_uid, json.dumps({'name':href[len('missing:'):], 'frag':'', 'missing': True}, ensure_ascii=False))
            else:
                a.set('target', '_blank')
                a.set('rel', 'noopener noreferrer')
        elif attr in a.attrib:
            a.set(attr, 'javascript:void(0)')

    for a in link_xpath(root):
        handle_link(a)
    xhref = XLINK('href')
    for a in svg_link_xpath(root):
        handle_link(a, xhref)

    return name in changed


__smil_file_names__ = ''


def process_book_file(virtualize_resources, link_uid, container, name):
    link_to_map = {}
    html_data = {}
    smil_map = {__smil_file_names__: []}
    virtualized_names = set()
    if name is not None:
        mt = container.mime_map[name].lower()
        if mt in OEB_DOCS:
            root = container.parsed(name)
            html_data[name] = {
                'length': get_length(root),
                'has_maths': check_for_maths(root),
                'anchor_map': anchor_map(root)
            }
            transform_html(container, name, virtualize_resources, link_uid, link_to_map, virtualized_names)
        elif mt in OEB_STYLES:
            transform_style_sheet(container, name, link_uid, virtualize_resources, virtualized_names)
        elif mt == 'image/svg+xml':
            transform_svg_image(container, name, link_uid, virtualize_resources, virtualized_names)
        elif mt in ('application/smil', 'application/smil+xml'):
            smil_map[__smil_file_names__].append(name)
            transform_smil(container, name, link_uid, virtualize_resources, virtualized_names, smil_map)
    return link_to_map, html_data, virtualized_names, smil_map


def calculate_number_of_workers(names, in_process_container, max_workers):
    num_workers = min(detect_ncpus(), len(names))
    if max_workers:
        num_workers = min(num_workers, max_workers)
    if num_workers > 1:
        if len(names) < 3 or sum(os.path.getsize(in_process_container.name_path_map[n]) for n in names) < 128 * 1024:
            num_workers = 1
    return num_workers


def process_exploded_book(
    book_fmt, opfpath, input_fmt, tdir, log=None, book_hash=None, save_bookmark_data=False,
    book_metadata=None, virtualize_resources=True, max_workers=1
):
    log = log or default_log
    container = SimpleContainer(tdir, opfpath, log)
    input_plugin = plugin_for_input_format(input_fmt)
    is_comic = bool(getattr(input_plugin, 'is_image_collection', False))

    def needs_work(mt):
        return mt in OEB_STYLES or mt in OEB_DOCS or mt in ('image/svg+xml', 'application/smil', 'application/smil+xml')

    bookmark_data = None
    if save_bookmark_data:
        bm_file = 'META-INF/calibre_bookmarks.txt'
        if container.exists(bm_file):
            with container.open(bm_file, 'rb') as f:
                bookmark_data = f.read()

    # We do not add zero byte sized files as the IndexedDB API in the
    # browser has no good way to distinguish between zero byte files and
    # load failures.
    excluded_names = {
        name for name, mt in container.mime_map.items() if
        name == container.opf_name or mt == guess_type('a.ncx') or name.startswith('META-INF/') or
        name == 'mimetype' or not container.has_name_and_is_not_empty(name)}
    raster_cover_name, titlepage_name = create_cover_page(container, input_fmt.lower(), is_comic, book_metadata)

    tocobj = get_toc(container, verify_destinations=False)
    page_list = tocobj.page_list or []
    toc = tocobj.to_dict(count())
    if not toc or not toc.get('children'):
        toc = from_xpaths(container, ['//h:h1', '//h:h2', '//h:h3']).to_dict(count())
    spine = [name for name, is_linear in container.spine_names]
    spineq = frozenset(spine)
    landmarks = [l for l in get_landmarks(container) if l['dest'] in spineq]

    if not spineq:
        raise Spineless('Book is empty, no content in spine')

    page_progression_direction = None
    try:
        page_progression_direction = container.opf_xpath('//opf:spine/@page-progression-direction')[0]
    except IndexError:
        pass

    book_render_data = {
        'version': RENDER_VERSION,
        'toc':toc,
        'book_format': book_fmt,
        'spine':spine,
        'link_uid': uuid4(),
        'book_hash': book_hash,
        'is_comic': is_comic,
        'raster_cover_name': raster_cover_name,
        'title_page_name': titlepage_name,
        'has_maths': False,
        'total_length': 0,
        'spine_length': 0,
        'toc_anchor_map': toc_anchor_map(toc),
        'landmarks': landmarks,
        'link_to_map': {},
        'page_progression_direction': page_progression_direction,
        'page_list': page_list,
        'page_list_anchor_map': pagelist_anchor_map(page_list),
    }

    names_that_need_work = tuple(n for n, mt in container.mime_map.items() if needs_work(mt))
    num_workers = calculate_number_of_workers(names_that_need_work, container, max_workers)
    results = []
    f = partial(process_book_file, virtualize_resources, book_render_data['link_uid'], container)
    if num_workers < 2:
        results.extend(map(f, names_that_need_work))
    else:
        if forked_map_is_supported:
            results.extend(forked_map(f, names_that_need_work, num_workers=num_workers))
        else:
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                results.extend(executor.map(f, names_that_need_work))

    ltm = book_render_data['link_to_map']
    html_data = {}
    virtualized_names = set()

    def merge_ltm(dest, src):
        for k, v in src.items():
            if k in dest:
                dest[k] |= v
            else:
                dest[k] = v

    final_smil_map = {}

    def merge_smil_map(smil_map):
        for n in smil_map.pop(__smil_file_names__):
            excluded_names.add(n)
        for n, d in smil_map.items():
            if d:
                # This assumes all smil data for a spine item is in a single
                # smil file, which is required per the spec
                final_smil_map[n] = d

    for link_to_map, hdata, vnames, smil_map in results:
        html_data.update(hdata)
        virtualized_names |= vnames
        merge_smil_map(smil_map)
        for k, v in link_to_map.items():
            if k in ltm:
                merge_ltm(ltm[k], v)
            else:
                ltm[k] = v
    book_render_data['has_smil'] = bool(final_smil_map)

    def manifest_data(name):
        mt = (container.mime_map.get(name) or 'application/octet-stream').lower()
        ans = {
            'size':os.path.getsize(container.name_path_map[name]),
            'is_virtualized': name in virtualized_names,
            'mimetype':mt,
            'is_html': mt in OEB_DOCS,
        }
        if ans['is_html']:
            data = html_data[name]
            ans['length'] = l = data['length']
            book_render_data['total_length'] += l
            if name in book_render_data['spine']:
                book_render_data['spine_length'] += l
            ans['has_maths'] = hm = data['has_maths']
            if hm:
                book_render_data['has_maths'] = True
            ans['anchor_map'] = data['anchor_map']
            smil_map = final_smil_map.get(name)
            if smil_map:
                ans['smil_map'] = smil_map
        return ans

    book_render_data['files'] = {name:manifest_data(name) for name in set(container.name_path_map) - excluded_names}
    container.commit()

    for name in excluded_names:
        os.remove(container.name_path_map[name])

    ltm = book_render_data['link_to_map']
    for name, amap in ltm.items():
        for k, v in tuple(amap.items()):
            amap[k] = tuple(v)  # needed for JSON serialization

    data = as_bytes(json.dumps(book_render_data, ensure_ascii=False))
    with open(os.path.join(container.root, 'calibre-book-manifest.json'), 'wb') as f:
        f.write(data)

    return container, bookmark_data


def split_name(name):
    l, r = name.partition('}')[::2]
    if r:
        return l[1:], r
    return None, l


known_tags = ('img', 'script', 'link', 'image', 'style')
discarded_tags = ('meta', 'base')


def ensure_body(root):
    # Make sure we have only a single <body>
    bodies = list(root.iterchildren(XHTML('body')))
    if len(bodies) != 1:
        if not bodies:
            root.append(root.makeelement(XHTML('body')))
            return
        body = bodies[0]
        for b in bodies[1:]:
            div = root.makeelement(XHTML('div'))
            div.attrib.update(b.attrib)
            div.text = b.text
            for child in b:
                div.append(child)
            body.append(div)


def html_as_json(root):
    from calibre_extensions.html_as_json import serialize
    ns, name = split_name(root.tag)
    if ns not in (None, XHTML_NS):
        raise ValueError('HTML tag must be in empty or XHTML namespace')
    ensure_body(root)
    for child in tuple(root.iterchildren('*')):
        if child.tag.partition('}')[-1] not in ('head', 'body'):
            root.remove(child)
    root.text = root.tail = None
    return serialize(root, Comment)


def serialize_datetimes(d):
    for k in tuple(d):
        v = d[k]
        if isinstance(v, datetime):
            v = encode_datetime(v)
            d[k] = v


EPUB_FILE_TYPE_MAGIC = b'encoding=json+base64:\n'


def get_stored_annotations(container, bookmark_data):
    raw = bookmark_data or b''
    if not raw:
        return
    if raw.startswith(EPUB_FILE_TYPE_MAGIC):
        raw = raw[len(EPUB_FILE_TYPE_MAGIC):].replace(b'\n', b'')
        yield from json_loads(from_base64_bytes(raw))
        return

    from calibre.ebooks.oeb.iterator.bookmarks import parse_bookmarks
    for bm in parse_bookmarks(raw):
        if bm['type'] == 'cfi' and isinstance(bm['pos'], str):
            spine_index = (1 + bm['spine']) * 2
            epubcfi = 'epubcfi(/{}/{})'.format(spine_index, bm['pos'].lstrip('/'))
            title = bm.get('title')
            if title and title != 'calibre_current_page_bookmark':
                yield {'type': 'bookmark', 'title': title, 'pos': epubcfi, 'pos_type': 'epubcfi', 'timestamp': EPOCH}
            else:
                yield {'type': 'last-read', 'pos': epubcfi, 'pos_type': 'epubcfi', 'timestamp': EPOCH}


def render(pathtoebook, output_dir, book_hash=None, serialize_metadata=False, extract_annotations=False, virtualize_resources=True, max_workers=0):
    pathtoebook = os.path.abspath(pathtoebook)
    mi = None
    if serialize_metadata:
        from calibre.customize.ui import quick_metadata
        from calibre.ebooks.metadata.meta import get_metadata
        with open(pathtoebook, 'rb') as f, quick_metadata:
            mi = get_metadata(f, os.path.splitext(pathtoebook)[1][1:].lower())
    book_fmt, opfpath, input_fmt = extract_book(pathtoebook, output_dir, log=default_log)
    container, bookmark_data = process_exploded_book(
        book_fmt, opfpath, input_fmt, output_dir, max_workers=max_workers,
        book_hash=book_hash, save_bookmark_data=extract_annotations,
        book_metadata=mi, virtualize_resources=virtualize_resources
    )
    if serialize_metadata:
        from calibre.ebooks.metadata.book.serialize import metadata_as_dict
        d = metadata_as_dict(mi)
        d.pop('cover_data', None)
        serialize_datetimes(d), serialize_datetimes(d.get('user_metadata', {}))
        with open(os.path.join(output_dir, 'calibre-book-metadata.json'), 'wb') as f:
            f.write(json_dumps(d))
    if extract_annotations:
        annotations = None
        if bookmark_data:
            annotations = json_dumps(tuple(get_stored_annotations(container, bookmark_data)))
        if annotations:
            with open(os.path.join(output_dir, 'calibre-book-annotations.json'), 'wb') as f:
                f.write(annotations)


def render_for_viewer(path, out_dir, book_hash):
    return render(
        path, out_dir, book_hash=book_hash, serialize_metadata=True,
        extract_annotations=True, virtualize_resources=False
    )


def viewer_main():
    stdin = getattr(sys.stdin, 'buffer', sys.stdin)
    args = msgpack_loads(stdin.read())
    render_for_viewer(*args)


# QuickLook {{{

def quicklook(pathtoebook: str, output_dir: str) -> dict[str, object]:
    pathtoebook = os.path.abspath(pathtoebook)
    output_dir = os.path.abspath(output_dir)
    book_fmt, opfpath, input_fmt = extract_book(pathtoebook, output_dir, log=default_log)
    container = SimpleContainer(output_dir, opfpath, default_log)
    from calibre.customize.ui import quick_metadata
    from calibre.ebooks.metadata.meta import get_metadata
    with open(pathtoebook, 'rb') as f, quick_metadata:
        mi = get_metadata(f, os.path.splitext(pathtoebook)[1][1:].lower())
    from calibre.ebooks.metadata.book.serialize import metadata_as_dict
    d = metadata_as_dict(mi)
    d.pop('cover_data', None)
    serialize_datetimes(d), serialize_datetimes(d.get('user_metadata', {}))
    input_plugin = plugin_for_input_format(input_fmt)
    is_comic = bool(getattr(input_plugin, 'is_image_collection', False))
    raster_cover_name, titlepage_name = create_cover_page(container, input_fmt.lower(), is_comic, mi)
    spine = []
    for name, linear in container.spine_names:
        spine.append({'path': container.get_file_path_for_processing(name, allow_modification=False), 'is_linear': linear})
    ans = {'spine': spine, 'metadata': d, 'is_comic': is_comic}
    if raster_cover_name:
        ans['raster_cover'] = container.get_file_path_for_processing(raster_cover_name, allow_modification=False)
    if titlepage_name:
        ans['titlepage'] = container.get_file_path_for_processing(titlepage_name, allow_modification=False)
    return ans


def handle_quicklook_client(c) -> None:
    with c.makefile('r', encoding='utf-8') as inf:
        for line in inf:
            line = line.rstrip()
            if not line:
                return
            req = json.loads(line)
        try:
            output = {'ok': True, 'path': req['path'], 'result': quicklook(req['path'], req['output_dir'])}
        except Exception as e:
            import traceback
            output = {'ok': False, 'path': req['path'], 'error': str(e), 'traceback': traceback.format_exc()}
        with c.makefile('w', encoding='utf-8') as outf:
            json.dump(output, outf)
            print(file=outf, flush=True)


def quicklook_service(path_to_socket: str) -> None:
    '''
    A server to service requests to generate QuickLook previews.
    Connect to the socket and send JSON of the form:
        {"path": /path/to/ebook, "output_dir": /path/to/output_dir}
    In response, the service will extract the ebook as HTML into the output_dir
    and return a JSON dict containing the list of HTML files and metadata about the
    book on the socket.

    You can send requests for multiple books, with the JSON objects separated by newlines.
    The output JSON will also be separated by newlines.

    Send an empty line to instruct the server to shutdown.

    Example, having the server listen at /tmp/qs and prepare the book /t/demo.epub in /t/qs:
    calibre-debug -c "from calibre.srv.render_book import *; quicklook_service("/tmp/qs")"
    echo '{"path": "/t/demo.epub", "output_dir": "/t/qs"}' | socat - unix-connect:/tmp/qs
    '''
    import socket
    from contextlib import closing, suppress

    from calibre.constants import debug
    from calibre.ptempfile import reset_base_dir
    from calibre.utils.safe_atexit import remove_file_atexit, reset_after_fork
    debug(False)
    s = socket.socket(socket.AF_UNIX)
    s.setblocking(True)
    s.bind(path_to_socket)
    with suppress(KeyboardInterrupt), closing(s):
        if path_to_socket and not path_to_socket.startswith('\0'):
            remove_file_atexit(path_to_socket)
        s.listen(16)
        while True:
            c, addr = s.accept()
            c.setblocking(True)
            os.set_inheritable(c.fileno(), True)
            if child_pid := os.fork():  # parent
                c.close()
                os.waitpid(child_pid, 0)
            else:  # child
                os.set_inheritable(c.fileno(), False)
                reset_after_fork()
                reset_base_dir()
                try:
                    handle_quicklook_client(c)
                finally:
                    c.shutdown(socket.SHUT_RDWR)
                    c.close()

# }}}


class Profiler:

    def __init__(self):
        try:
            import cProfile as profile
        except ImportError:
            import profile
        self.profile = profile.Profile()

    def __enter__(self):
        self.profile.enable()

    def __exit__(self, *a):
        self.profile.disable()
        self.profile.create_stats()
        import pstats
        stats = pstats.Stats(self.profile)
        stats.sort_stats('cumulative')
        stats.print_stats(.05)


def profile():
    from calibre.ptempfile import TemporaryDirectory
    path = sys.argv[-1]
    with TemporaryDirectory() as tdir, Profiler():
        return render(
            path, tdir, serialize_metadata=True,
            extract_annotations=True, virtualize_resources=False, max_workers=1
        )


def develop(max_workers=1, wait_for_input=True):
    from calibre.ptempfile import TemporaryDirectory
    path = sys.argv[-1]
    if max_workers < 1:
        max_workers = os.cpu_count()
    with TemporaryDirectory() as tdir:
        render(
            path, tdir, serialize_metadata=True,
            extract_annotations=True, virtualize_resources=False, max_workers=max_workers
        )
        print('Extracted to:', tdir)
        if wait_for_input:
            input('Press Enter to quit')


if __name__ == '__main__':
    develop()
