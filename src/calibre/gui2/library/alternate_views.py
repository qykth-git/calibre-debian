#!/usr/bin/env python


__license__ = 'GPL v3'
__copyright__ = '2013, Kovid Goyal <kovid at kovidgoyal.net>'

import itertools
import math
import operator
import os
import weakref
from collections import namedtuple
from functools import wraps
from io import BytesIO
from textwrap import wrap
from threading import Event, Thread

from qt.core import (
    QAbstractItemView,
    QApplication,
    QBuffer,
    QByteArray,
    QColor,
    QDrag,
    QEasingCurve,
    QEvent,
    QFont,
    QHelpEvent,
    QIcon,
    QImage,
    QIODevice,
    QItemSelection,
    QItemSelectionModel,
    QListView,
    QMimeData,
    QModelIndex,
    QPainter,
    QPalette,
    QPixmap,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    Qt,
    QTableView,
    QTimer,
    QToolTip,
    QTreeView,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
    qBlue,
    qGreen,
    qRed,
)

from calibre import fit_image, human_readable, prepare_string_for_xml
from calibre.constants import DEBUG, config_dir, islinux
from calibre.ebooks.metadata import fmt_sidx, rating_to_stars
from calibre.gui2 import clip_border_radius, config, empty_index, gprefs, rating_font, resolve_grid_color
from calibre.gui2.dnd import path_from_qurl
from calibre.gui2.gestures import GestureManager
from calibre.gui2.library.caches import CoverCache, ThumbnailCache
from calibre.gui2.library.models import themed_icon_name
from calibre.gui2.pin_columns import PinContainer
from calibre.utils import join_with_timeout
from calibre.utils.config import prefs, tweaks
from calibre.utils.img import convert_PIL_image_to_pixmap
from polyglot.builtins import itervalues
from polyglot.queue import LifoQueue

CM_TO_INCH = 0.393701
CACHE_FORMAT = 'PPM'


def auto_height(widget):
    # On some broken systems, availableGeometry() returns tiny values, we need
    # a value of at least 1000 for 200 DPI systems.
    return max(1000, widget.screen().availableSize().height()) / 5.0


class EncodeError(ValueError):
    pass


def handle_enter_press(self, ev, special_action=None, has_edit_cell=True):
    if ev.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
        mods = ev.modifiers()
        if (
            mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.AltModifier or
            mods & Qt.KeyboardModifier.ShiftModifier or mods & Qt.KeyboardModifier.MetaModifier
        ):
            return
        if self.state() != QAbstractItemView.State.EditingState and self.hasFocus() and self.currentIndex().isValid():
            from calibre.gui2.ui import get_gui
            ev.ignore()
            tweak = tweaks['enter_key_behavior']
            gui = get_gui()
            if tweak == 'edit_cell':
                if has_edit_cell:
                    self.edit(self.currentIndex(), QAbstractItemView.EditTrigger.EditKeyPressed, ev)
                else:
                    gui.iactions['Edit Metadata'].edit_metadata(False)
            elif tweak == 'edit_metadata':
                gui.iactions['Edit Metadata'].edit_metadata(False)
            elif tweak == 'do_nothing':
                pass
            elif tweak == 'show_locked_book_details':
                self.gui.iactions['Show Book Details'].show_book_info(locked=True)
            elif tweak == 'show_book_details':
                self.gui.iactions['Show Book Details'].show_book_info()
            else:
                if special_action is not None:
                    special_action(self.currentIndex())
                gui.iactions['View'].view_triggered(self.currentIndex())
            gui.enter_key_pressed_in_book_list.emit(self)
            return True


def image_to_data(image):  # {{{
    # Although this function is no longer used in this file, it is used in
    # other places in calibre. Don't delete it.
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buf, CACHE_FORMAT):
        raise EncodeError('Failed to encode thumbnail')
    ret = ba.data()
    buf.close()
    return ret
# }}}


# Drag 'n Drop {{{

def qt_item_view_base_class(self):
    for q in (QTableView, QListView, QTreeView):
        if isinstance(self, q):
            return q
    return QAbstractItemView


def dragMoveEvent(self, event):
    event.acceptProposedAction()


def event_has_mods(self, event=None):
    mods = event.modifiers() if event is not None else \
            QApplication.keyboardModifiers()
    return mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.ShiftModifier


def mousePressEvent(self, event):
    ep = event.pos()
    # for performance, check the selection only once we know we need it
    if event.button() == Qt.MouseButton.LeftButton and not self.event_has_mods() \
                and self.indexAt(ep) in self.selectionModel().selectedIndexes():
        self.drag_start_pos = ep
    if hasattr(self, 'handle_mouse_press_event'):
        return self.handle_mouse_press_event(event)
    return qt_item_view_base_class(self).mousePressEvent(self, event)


def mouseReleaseEvent(self, event):
    if hasattr(self, 'handle_mouse_release_event'):
        return self.handle_mouse_release_event(event)
    return qt_item_view_base_class(self).mouseReleaseEvent(self, event)


def drag_icon(self, cover, multiple):
    cover = cover.scaledToHeight(120, Qt.TransformationMode.SmoothTransformation)
    if multiple:
        base_width = cover.width()
        base_height = cover.height()
        base = QImage(base_width+21, base_height+21,
                QImage.Format.Format_ARGB32_Premultiplied)
        base.fill(QColor(255, 255, 255, 0).rgba())
        p = QPainter(base)
        rect = QRect(20, 0, base_width, base_height)
        p.fillRect(rect, QColor('white'))
        p.drawRect(rect)
        rect.moveLeft(10)
        rect.moveTop(10)
        p.fillRect(rect, QColor('white'))
        p.drawRect(rect)
        rect.moveLeft(0)
        rect.moveTop(20)
        p.fillRect(rect, QColor('white'))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        p.drawImage(rect.topLeft(), cover)
        p.restore()
        p.drawRect(rect)
        p.end()
        cover = base
    return QPixmap.fromImage(cover)


def drag_data(self):
    m = self.model()
    db = m.db
    selected = self.get_selected_ids()
    ids = ' '.join(map(str, selected))
    md = QMimeData()
    md.setData('application/calibre+from_library', ids.encode('utf-8'))
    fmt = prefs['output_format']

    def path_for_id(i):
        try:
            ans = db.format_path(i, fmt, index_is_id=True)
        except Exception:
            ans = None
        if ans is None:
            fmts = db.formats(i, index_is_id=True)
            if fmts:
                fmts = fmts.split(',')
            else:
                fmts = []
            for f in fmts:
                try:
                    ans = db.format_path(i, f, index_is_id=True)
                except Exception:
                    ans = None
        if ans is None:
            ans = db.abspath(i, index_is_id=True)
        return ans

    from calibre.gui2.dnd import set_urls_from_local_file_paths
    set_urls_from_local_file_paths(md, *[path_for_id(i) for i in selected])
    drag = QDrag(self)
    col = self.selectionModel().currentIndex().column()
    try:
        md.column_name = self.column_map[col]
    except AttributeError:
        md.column_name = 'title'
    drag.setMimeData(md)
    cover = self.drag_icon(m.cover(self.currentIndex().row()),
            len(selected) > 1)
    drag.setHotSpot(QPoint(-15, -15))
    drag.setPixmap(cover)
    return drag


def mouseMoveEvent(self, event):
    if self.event_has_mods():
        self.drag_start_pos = None
    if not self.drag_allowed:
        if hasattr(self, 'handle_mouse_move_event'):
            self.handle_mouse_move_event(event)
        return
    if self.drag_start_pos is None:
        if hasattr(self, 'handle_mouse_move_event'):
            self.handle_mouse_move_event(event)
        else:
            qt_item_view_base_class(self).mouseMoveEvent(self, event)
        return
    if not (event.buttons() & Qt.MouseButton.LeftButton) or \
            (event.pos() - self.drag_start_pos).manhattanLength() \
                    < QApplication.startDragDistance():
        return

    index = self.indexAt(event.pos())
    if not index.isValid():
        return
    drag = self.drag_data()
    drag.exec(Qt.DropAction.CopyAction)
    self.drag_start_pos = None


def dnd_merge_ok(md):
    return md.hasFormat('application/calibre+from_library') and gprefs['dnd_merge']


def dragEnterEvent(self, event):
    if not event.possibleActions() & (Qt.DropAction.CopyAction | Qt.DropAction.MoveAction):
        return
    paths = self.paths_from_event(event)
    md = event.mimeData()

    if paths or dnd_merge_ok(md):
        event.acceptProposedAction()


def dropEvent(self, event):
    md = event.mimeData()
    if dnd_merge_ok(md):
        ids = set(map(int, filter(None, bytes(md.data('application/calibre+from_library')).decode('utf-8').split(' '))))
        row = self.indexAt(event.position().toPoint()).row()
        if row > -1 and ids:
            book_id = self.model().id(row)
            if book_id and book_id not in ids:
                self.books_dropped.emit({book_id: ids})
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
        return
    paths = self.paths_from_event(event)
    event.setDropAction(Qt.DropAction.CopyAction)
    event.accept()
    self.files_dropped.emit(paths)


def paths_from_event(self, event):
    '''
    Accept a drop event and return a list of paths that can be read from
    and represent files with extensions.
    '''
    md = event.mimeData()
    if md.hasFormat('text/uri-list') and not md.hasFormat('application/calibre+from_library'):
        urls = map(path_from_qurl, md.urls())
        return [u for u in urls if u and os.path.splitext(u)[1] and os.path.exists(u)]


def setup_dnd_interface(cls_or_self):
    if isinstance(cls_or_self, type):
        cls = cls_or_self
        fmap = globals()
        for x in (
            'dragMoveEvent', 'event_has_mods', 'mousePressEvent', 'mouseMoveEvent', 'mouseReleaseEvent',
            'drag_data', 'drag_icon', 'dragEnterEvent', 'dropEvent', 'paths_from_event'):
            func = fmap[x]
            setattr(cls, x, func)
        return cls
    else:
        self = cls_or_self
        self.drag_allowed = True
        self.drag_start_pos = None
        self.setDragEnabled(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
# }}}


# Manage slave views {{{

def sync(func):
    @wraps(func)
    def ans(self, *args, **kwargs):
        if self.break_link or self.current_view is self.main_view:
            return
        with self:
            return func(self, *args, **kwargs)
    return ans


class AlternateViews:

    def __init__(self, main_view):
        self.views = {None:main_view}
        self.stack_positions = {None:0}
        self.current_view = self.main_view = main_view
        self.stack = None
        self.break_link = False
        self.main_connected = False
        self.current_book_state = None

    def set_stack(self, stack):
        self.stack = stack
        pin_container = PinContainer(self.main_view, stack)
        self.stack.addWidget(pin_container)
        return pin_container

    def add_view(self, key, view):
        self.views[key] = view
        self.stack_positions[key] = self.stack.count()
        self.stack.addWidget(view)
        self.stack.setCurrentIndex(0)
        view.setModel(self.main_view._model)
        view.selectionModel().currentChanged.connect(self.slave_current_changed)
        view.selectionModel().selectionChanged.connect(self.slave_selection_changed)
        view.files_dropped.connect(self.main_view.files_dropped)
        view.books_dropped.connect(self.main_view.books_dropped)

    def show_view(self, key=None):
        view = self.views[key]
        if view is self.current_view:
            return
        self.stack.setCurrentIndex(self.stack_positions[key])
        self.current_view = view
        if view is not self.main_view:
            self.main_current_changed(self.main_view.currentIndex())
            self.main_selection_changed()
            view.shown()
            if not self.main_connected:
                self.main_connected = True
                self.main_view.selectionModel().currentChanged.connect(self.main_current_changed)
                self.main_view.selectionModel().selectionChanged.connect(self.main_selection_changed)
            view.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_database(self, db, stage=0):
        for view in itervalues(self.views):
            if view is not self.main_view:
                view.set_database(db, stage=stage)

    def __enter__(self):
        self.break_link = True

    def __exit__(self, *args):
        self.break_link = False

    @sync
    def slave_current_changed(self, current, *args):
        self.main_view.set_current_row(current.row(), for_sync=True)

    @sync
    def slave_selection_changed(self, *args):
        rows = {r.row() for r in self.current_view.selectionModel().selectedIndexes()}
        self.main_view.select_rows(rows, using_ids=False, change_current=False, scroll=False)

    @sync
    def main_current_changed(self, current, *args):
        self.current_view.set_current_row(current.row())

    @sync
    def main_selection_changed(self, *args):
        rows = {r.row() for r in self.main_view.selectionModel().selectedIndexes()}
        self.current_view.select_rows(rows)

    def set_context_menu(self, menu):
        for view in itervalues(self.views):
            if view is not self.main_view:
                view.set_context_menu(menu)

    def save_current_book_state(self):
        self.current_book_state = self.current_view, self.current_view.current_book_state()

    def restore_current_book_state(self):
        if self.current_book_state is not None:
            if self.current_book_state[0] is self.current_view:
                self.current_view.restore_current_book_state(self.current_book_state[1])
            self.current_book_state = None

    def marked_changed(self, old_marked, current_marked):
        if self.current_view is not self.main_view:
            self.current_view.marked_changed(old_marked, current_marked)
# }}}


# Rendering of covers {{{

class CoverDelegate(QStyledItemDelegate):

    MARGIN = 4
    TOP, LEFT, RIGHT, BOTTOM = object(), object(), object(), object()

    @pyqtProperty(float)
    def animated_size(self):
        return self._animated_size

    @animated_size.setter
    def animated_size(self, val):
        self._animated_size = val

    def __init__(self, parent):
        super().__init__(parent)
        self._animated_size = 1.0
        self.animation = QPropertyAnimation(self, b'animated_size', self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutInCirc)
        self.animation.setDuration(500)
        self.set_dimensions()
        self.cover_cache = CoverCache()
        self.render_queue = LifoQueue()
        self.animating = None
        self.highlight_color = QColor(Qt.GlobalColor.white)
        self.rating_font = QFont(rating_font())

    def set_dimensions(self):
        width = self.original_width = gprefs['cover_grid_width']
        height = self.original_height = gprefs['cover_grid_height']
        self.original_show_title = show_title = gprefs['cover_grid_show_title']
        self.original_show_emblems = gprefs['show_emblems']
        self.orginal_emblem_size = gprefs['emblem_size']
        self.orginal_emblem_position = gprefs['emblem_position']
        self.emblem_size = gprefs['emblem_size'] if self.original_show_emblems else 0
        try:
            self.gutter_position = getattr(self, self.orginal_emblem_position.upper())
        except Exception:
            self.gutter_position = self.TOP

        if height < 0.1:
            height = auto_height(self.parent())
        else:
            height *= self.parent().logicalDpiY() * CM_TO_INCH

        if width < 0.1:
            width = 0.75 * height
        else:
            width *= self.parent().logicalDpiX() * CM_TO_INCH
        self.cover_size = QSize(int(width), int(height))
        self.title_height = 0
        if show_title:
            f = self.parent().font()
            sz = f.pixelSize()
            if sz < 5:
                sz = f.pointSize() * self.parent().logicalDpiY() / 72.0
            self.title_height = int(max(25, sz + 10))
        self.item_size = self.cover_size + QSize(2 * self.MARGIN, (2 * self.MARGIN) + self.title_height)
        if self.emblem_size > 0:
            extra = self.emblem_size + self.MARGIN
            self.item_size += QSize(extra, 0) if self.gutter_position in (self.LEFT, self.RIGHT) else QSize(0, extra)
        self.calculate_spacing()
        self.animation.setStartValue(1.0)
        self.animation.setKeyValueAt(0.5, 0.5)
        self.animation.setEndValue(1.0)

    def calculate_spacing(self):
        spc = self.original_spacing = gprefs['cover_grid_spacing']
        if spc < 0.01:
            self.spacing = max(10, min(50, int(0.1 * self.original_width)))
        else:
            self.spacing = int(self.parent().logicalDpiX() * CM_TO_INCH * spc)

    def sizeHint(self, option, index):
        return self.item_size

    def render_field(self, db, book_id):
        is_stars = False
        try:
            field = db.pref('field_under_covers_in_grid', 'title')
            if field == 'size':
                ans = human_readable(db.field_for(field, book_id, default_value=0))
            else:
                mi = db.get_proxy_metadata(book_id)
                display_name, ans, val, fm = mi.format_field_extended(field)
                if fm and fm['datatype'] == 'rating':
                    ans = rating_to_stars(val, fm['display'].get('allow_half_stars', False))
                    is_stars = True
            return ('' if ans is None else str(ans)), is_stars
        except Exception:
            if DEBUG:
                import traceback
                traceback.print_exc()
        return '', is_stars

    def render_emblem(self, book_id, rule, rule_index, cache, mi, db, formatter, template_cache):
        ans = cache[book_id].get(rule, False)
        if ans is not False:
            return ans, mi
        ans = None
        if mi is None:
            mi = db.get_proxy_metadata(book_id)
        ans = formatter.safe_format(rule, mi, '', mi, column_name=f'cover_grid{rule_index}', template_cache=template_cache) or None
        cache[book_id][rule] = ans
        return ans, mi

    def cached_emblem(self, cache, name, raw_icon=None):
        ans = cache.get(name, False)
        if ans is not False:
            return ans
        sz = self.emblem_size
        ans = None
        if raw_icon is not None:
            ans = raw_icon.pixmap(sz, sz)
        elif name == ':ondevice':
            ans = QIcon.ic('ok.png').pixmap(sz, sz)
        elif name:
            pmap = None
            d = themed_icon_name(os.path.join(config_dir, 'cc_icons'), name)
            if d is not None:
                pmap = QIcon(d).pixmap(sz, sz)
            if pmap is None:
                pmap = QIcon(os.path.join(config_dir, 'cc_icons', name)).pixmap(sz, sz)
            if not pmap.isNull():
                ans = pmap
        cache[name] = ans
        return ans

    def paint(self, painter, option, index):
        with clip_border_radius(painter, option.rect):
            QStyledItemDelegate.paint(self, painter, option, empty_index)  # draw the hover and selection highlights
        m = index.model()
        db = m.db
        try:
            book_id = db.id(index.row())
        except (ValueError, IndexError, KeyError):
            return
        if book_id in m.ids_to_highlight_set:
            painter.save()
            try:
                painter.setPen(self.highlight_color)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.drawRoundedRect(option.rect, 10, 10, Qt.SizeMode.RelativeSize)
            finally:
                painter.restore()
        marked = db.data.get_marked(book_id)
        db = db.new_api
        cdata = self.cover_cache[book_id]
        if cdata is False:
            # Don't render anything if we haven't cached the rendered cover.
            # This reduces subtle flashing as covers are repainted. Note that
            # cdata is None if there isn't a cover vs an unrendered cover.
            self.render_queue.put(book_id)
            return
        device_connected = self.parent().gui.device_connected is not None
        on_device = device_connected and db.field_for('ondevice', book_id)

        emblem_rules = db.pref('cover_grid_icon_rules', default=())
        emblems = []
        if self.emblem_size > 0:
            mi = None
            for i, (kind, column, rule) in enumerate(emblem_rules):
                icon_name, mi = self.render_emblem(book_id, rule, i, m.cover_grid_emblem_cache, mi, db, m.formatter, m.cover_grid_template_cache)
                if icon_name is not None:
                    for one_icon in filter(None, (i.strip() for i in icon_name.split(':'))):
                        pixmap = self.cached_emblem(m.cover_grid_bitmap_cache, one_icon)
                        if pixmap is not None:
                            emblems.append(pixmap)
            if marked:
                emblems.insert(0, self.cached_emblem(m.cover_grid_bitmap_cache, ':marked', m.marked_icon))
            if on_device:
                emblems.insert(0, self.cached_emblem(m.cover_grid_bitmap_cache, ':ondevice'))

        painter.save()
        right_adjust = 0
        try:
            rect = option.rect
            rect.adjust(self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)
            if self.emblem_size > 0:
                self.paint_emblems(painter, rect, emblems)
            orect = QRect(rect)
            trect = QRect(rect)
            if self.title_height != 0:
                rect.setBottom(rect.bottom() - self.title_height)
                trect.setTop(trect.bottom() - self.title_height + 5)
            if cdata is None or cdata is False:
                title = db.field_for('title', book_id, default_value='')
                authors = ' & '.join(db.field_for('authors', book_id, default_value=()))
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap, f'{title}\n\n{authors}')
                if cdata is False:
                    self.render_queue.put(book_id)
                # else if None: don't queue the request
                if self.title_height != 0:
                    self.paint_title(painter, trect, db, book_id)
            else:
                if self.animating is not None and self.animating.row() == index.row():
                    cdata = cdata.scaled(cdata.size() * self._animated_size)
                dpr = cdata.devicePixelRatio()
                cw, ch = int(cdata.width() / dpr), int(cdata.height() / dpr)
                dx = max(0, int((rect.width() - cw)/2.0))
                dy = max(0, int((rect.height() - ch)/2.0))
                right_adjust = dx
                rect.adjust(dx, dy, -dx, -dy)
                self.paint_cover(painter, rect, cdata)
                if self.title_height != 0:
                    self.paint_title(painter, trect, db, book_id)
            if self.emblem_size > 0:
                # We don't draw embossed emblems as the ondevice/marked emblems are drawn in the gutter
                return
            if marked:
                try:
                    p = self.marked_emblem
                except AttributeError:
                    p = self.marked_emblem = m.marked_icon.pixmap(48, 48)
                self.paint_embossed_emblem(p, painter, orect, right_adjust)

            if on_device:
                try:
                    p = self.on_device_emblem
                except AttributeError:
                    p = self.on_device_emblem = QIcon.ic('ok.png').pixmap(48, 48)
                self.paint_embossed_emblem(p, painter, orect, right_adjust, left=False)
        finally:
            painter.restore()

    def paint_cover(self, painter: QPainter, rect: QRect, pixmap: QPixmap):
        with clip_border_radius(painter, rect):
            painter.drawPixmap(rect, pixmap)

    def paint_title(self, painter, rect, db, book_id):
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        title, is_stars = self.render_field(db, book_id)
        if is_stars:
            painter.setFont(self.rating_font)
        metrics = painter.fontMetrics()
        painter.setPen(self.highlight_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextSingleLine,
                            metrics.elidedText(title, Qt.TextElideMode.ElideRight, rect.width()))

    def paint_emblems(self, painter, rect, emblems):
        gutter = self.emblem_size + self.MARGIN
        grect = QRect(rect)
        gpos = self.gutter_position
        if gpos is self.TOP:
            grect.setBottom(grect.top() + gutter)
            rect.setTop(rect.top() + gutter)
        elif gpos is self.BOTTOM:
            grect.setTop(grect.bottom() - gutter + self.MARGIN)
            rect.setBottom(rect.bottom() - gutter)
        elif gpos is self.LEFT:
            grect.setRight(grect.left() + gutter)
            rect.setLeft(rect.left() + gutter)
        else:
            grect.setLeft(grect.right() - gutter + self.MARGIN)
            rect.setRight(rect.right() - gutter)
        horizontal = gpos in (self.TOP, self.BOTTOM)
        painter.save()
        painter.setClipRect(grect)
        try:
            for i, emblem in enumerate(emblems):
                delta = 0 if i == 0 else self.emblem_size + self.MARGIN
                grect.moveLeft(grect.left() + delta) if horizontal else grect.moveTop(grect.top() + delta)
                rect = QRect(grect)
                rect.setWidth(int(emblem.width() / emblem.devicePixelRatio())), rect.setHeight(int(emblem.height() / emblem.devicePixelRatio()))
                painter.drawPixmap(rect, emblem)
        finally:
            painter.restore()

    def paint_embossed_emblem(self, pixmap, painter, orect, right_adjust, left=True):
        drect = QRect(orect)
        pw = int(pixmap.width() / pixmap.devicePixelRatio())
        ph = int(pixmap.height() / pixmap.devicePixelRatio())
        if left:
            drect.setLeft(drect.left() + right_adjust)
            drect.setRight(drect.left() + pw)
        else:
            drect.setRight(drect.right() - right_adjust)
            drect.setLeft(drect.right() - pw + 1)
        drect.setBottom(drect.bottom() - self.title_height)
        drect.setTop(drect.bottom() - ph)
        painter.drawPixmap(drect, pixmap)

    @pyqtSlot(QHelpEvent, QAbstractItemView, QStyleOptionViewItem, QModelIndex, result=bool)
    def helpEvent(self, event, view, option, index):
        if event is not None and view is not None and event.type() == QEvent.Type.ToolTip:
            try:
                db = index.model().db
            except AttributeError:
                return False
            try:
                book_id = db.id(index.row())
            except (ValueError, IndexError, KeyError):
                return False
            db = db.new_api
            device_connected = self.parent().gui.device_connected
            on_device = device_connected is not None and db.field_for('ondevice', book_id)
            p = prepare_string_for_xml
            title = db.field_for('title', book_id)
            authors = db.field_for('authors', book_id)
            if title and authors:
                title = '<b>{}</b>'.format('<br>'.join(wrap(p(title), 120)))
                authors = '<br>'.join(wrap(p(' & '.join(authors)), 120))
                tt = f'{title}<br><br>{authors}'
                series = db.field_for('series', book_id)
                if series:
                    use_roman_numbers=config['use_roman_numerals_for_series_number']
                    val = _('Book %(sidx)s of <span class="series_name">%(series)s</span>')%dict(
                        sidx=fmt_sidx(db.field_for('series_index', book_id), use_roman=use_roman_numbers),
                        series=p(series))
                    tt += '<br><br>' + val
                if on_device:
                    val = _('This book is on the device in %s') % on_device
                    tt += '<br><br>' + val
                QToolTip.showText(event.globalPos(), tt, view)
                return True
        return False

# }}}


CoverTuple = namedtuple('CoverTuple', ['book_id', 'has_cover', 'cache_valid',
                                     'cdata', 'timestamp'])


# The View {{{

@setup_dnd_interface
class GridView(QListView):

    update_item = pyqtSignal(object, object)
    files_dropped = pyqtSignal(object)
    books_dropped = pyqtSignal(object)

    def __init__(self, parent):
        QListView.__init__(self, parent)
        self.shift_click_start_data = None
        self.dbref = lambda: None
        self._ncols = None
        self.gesture_manager = GestureManager(self)
        setup_dnd_interface(self)
        self.setUniformItemSizes(True)
        self.setWrapping(True)
        self.setFlow(QListView.Flow.LeftToRight)
        # We cannot set layout mode to batched, because that breaks
        # restore_vpos()
        # self.setLayoutMode(QListView.ResizeMode.Batched)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.delegate = CoverDelegate(self)
        self.delegate.animation.valueChanged.connect(self.animation_value_changed)
        self.delegate.animation.finished.connect(self.animation_done)
        self.setItemDelegate(self.delegate)
        self.setSpacing(self.delegate.spacing)
        self.set_color()
        QApplication.instance().palette_changed.connect(self.set_color)
        self.ignore_render_requests = Event()
        dpr = self.device_pixel_ratio
        # Up the version number if anything changes in how images are stored in
        # the cache.
        self.thumbnail_cache = ThumbnailCache(max_size=gprefs['cover_grid_disk_cache_size'],
            thumbnail_size=(int(dpr * self.delegate.cover_size.width()),
                            int(dpr * self.delegate.cover_size.height())),
            version=1)
        self.render_thread = None
        self.update_item.connect(self.re_render, type=Qt.ConnectionType.QueuedConnection)
        self.doubleClicked.connect(self.double_clicked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gui = parent
        self.context_menu = None
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(200)
        self.update_timer.timeout.connect(self.update_viewport)
        self.update_timer.setSingleShot(True)
        self.resize_timer = t = QTimer(self)
        t.setInterval(200), t.setSingleShot(True)
        t.timeout.connect(self.update_memory_cover_cache_size)

    def viewportEvent(self, ev):
        if hasattr(self, 'gesture_manager'):
            ret = self.gesture_manager.handle_event(ev)
            if ret is not None:
                return ret
        return super().viewportEvent(ev)

    @property
    def device_pixel_ratio(self):
        return self.devicePixelRatioF()

    @property
    def first_visible_row(self):
        geom = self.viewport().geometry()
        for y in range(geom.top(), (self.spacing()*2) + geom.top(), 5):
            for x in range(geom.left(), (self.spacing()*2) + geom.left(), 5):
                ans = self.indexAt(QPoint(x, y)).row()
                if ans > -1:
                    return ans

    @property
    def last_visible_row(self):
        geom = self.viewport().geometry()
        for y in range(geom.bottom(), geom.bottom() - 2 * self.spacing(), -5):
            for x in range(geom.left(), (self.spacing()*2) + geom.left(), 5):
                ans = self.indexAt(QPoint(x, y)).row()
                if ans > -1:
                    item_width = self.delegate.item_size.width() + 2*self.spacing()
                    return ans + (geom.width() // item_width)

    def update_viewport(self):
        self.ignore_render_requests.clear()
        self.update_timer.stop()
        m = self.model()
        for r in range(self.first_visible_row or 0, self.last_visible_row or (m.count() - 1)):
            self.update(m.index(r, 0))

    def start_view_animation(self, index):
        d = self.delegate
        if d.animating is None and not config['disable_animations']:
            d.animating = index
            d.animation.start()

    def double_clicked(self, index):
        self.start_view_animation(index)
        tval = tweaks['doubleclick_on_library_view']
        if tval == 'open_viewer':
            self.gui.iactions['View'].view_triggered(index)
        elif tval in {'edit_metadata', 'edit_cell'}:
            self.gui.iactions['Edit Metadata'].edit_metadata(False, False)
        elif tval == 'show_book_details':
            self.gui.iactions['Show Book Details'].show_book_info()

    def animation_value_changed(self, value):
        if self.delegate.animating is not None:
            self.update(self.delegate.animating)

    def animation_done(self):
        if self.delegate.animating is not None:
            idx = self.delegate.animating
            self.delegate.animating = None
            self.update(idx)

    def set_color(self):
        r, g, b = resolve_grid_color()
        tex = resolve_grid_color(which='texture')
        pal = self.palette()
        bgcol = QColor(r, g, b)
        pal.setColor(QPalette.ColorRole.Base, bgcol)
        self.setPalette(pal)
        ss = f'background-color: {bgcol.name()}; border: 0px solid {bgcol.name()};'
        if tex:
            from calibre.gui2.preferences.texture_chooser import texture_path
            path = texture_path(tex)
            if path:
                path = os.path.abspath(path).replace(os.sep, '/')
                ss += f'background-image: url({path});'
                ss += 'background-attachment: fixed;'
                pm = QPixmap(path)
                if not pm.isNull():
                    val = pm.scaled(1, 1).toImage().pixel(0, 0)
                    r, g, b = qRed(val), qGreen(val), qBlue(val)
        dark = max(r, g, b) < 115
        col = '#eee' if dark else '#111'
        ss += f'color: {col};'
        self.delegate.highlight_color = QColor(col)
        self.setStyleSheet(f'QListView {{ {ss} }}')

    def refresh_settings(self):
        size_changed = (
            gprefs['cover_grid_width'] != self.delegate.original_width or gprefs['cover_grid_height'] != self.delegate.original_height
        )
        if (size_changed or gprefs[
            'cover_grid_show_title'] != self.delegate.original_show_title or gprefs[
                'show_emblems'] != self.delegate.original_show_emblems or gprefs[
                    'emblem_size'] != self.delegate.orginal_emblem_size or gprefs[
                        'emblem_position'] != self.delegate.orginal_emblem_position):
            self.delegate.set_dimensions()
            self.setSpacing(self.delegate.spacing)
            if size_changed:
                self.delegate.cover_cache.clear()
        if gprefs['cover_grid_spacing'] != self.delegate.original_spacing:
            self.delegate.calculate_spacing()
            self.setSpacing(self.delegate.spacing)
        self.set_color()
        self.set_thumbnail_cache_image_size()
        cs = gprefs['cover_grid_disk_cache_size']
        if (cs*(1024**2)) != self.thumbnail_cache.max_size:
            self.thumbnail_cache.set_size(cs)
        self.update_memory_cover_cache_size()

    def set_thumbnail_cache_image_size(self):
        dpr = self.device_pixel_ratio
        self.thumbnail_cache.set_thumbnail_size(
            int(dpr * self.delegate.cover_size.width()), int(dpr*self.delegate.cover_size.height()))

    def resizeEvent(self, ev):
        self._ncols = None
        self.resize_timer.start()
        return QListView.resizeEvent(self, ev)

    def update_memory_cover_cache_size(self):
        try:
            sz = self.delegate.item_size
        except AttributeError:
            return
        rows, cols = self.width() // sz.width(), self.height() // sz.height()
        num = (rows + 1) * (cols + 1)
        limit = max(100, num * max(2, gprefs['cover_grid_cache_size_multiple']))
        if limit != self.delegate.cover_cache.limit:
            self.delegate.cover_cache.set_limit(limit)

    def shown(self):
        self.update_memory_cover_cache_size()
        if self.render_thread is None:
            self.fetch_thread = Thread(target=self.fetch_covers)
            self.fetch_thread.daemon = True
            self.fetch_thread.start()

    def fetch_covers(self):
        q = self.delegate.render_queue
        while True:
            book_id = q.get()
            try:
                if book_id is None:
                    return
                if self.ignore_render_requests.is_set():
                    continue
                thumb = None
                try:
                    # Fetch the cover from the cache or file system
                    cover_tuple = self.fetch_cover_from_cache(book_id)
                    if cover_tuple is not None:
                        # Render/resize the cover.
                        thumb = self.make_thumbnail(cover_tuple)
                except Exception:
                    import traceback
                    traceback.print_exc()
                # Tell the GUI to redisplay the thumbnail with the new image
                self.update_item.emit(book_id, thumb)

            finally:
                q.task_done()

    def fetch_cover_from_cache(self, book_id):
        '''
        This method fetches the cover from the cache if it exists, otherwise the
        cover.jpg stored in the library.

        It is called on the cover thread.

        It returns a CoverTuple containing the following cover and cache data:

        book_id: The id of the book for which a cover is wanted.
        has_cover: True if the book has an associated cover image file.
        cdata: Cover data. Can be None (no cover data), or a rendered cover image.
        cache_valid: True if the cache has correct data, False if a cover exists
                     but isn't in the cache, None if the cache has data but the
                     cover has been deleted.
        timestamp: the cover file modtime if the cover came from the file system,
                   the timestamp in the cache if a valid cover is in the cache,
                   otherwise None.
        '''
        if self.ignore_render_requests.is_set():
            return None
        db = self.dbref()
        if db is None:
            return None
        tc = self.thumbnail_cache
        cdata, timestamp = tc[book_id]  # None, None if not cached.
        if timestamp is None:
            # Cover not in cache. Try to read the cover from the library.
            has_cover, cdata, timestamp = db.new_api.cover_or_cache(book_id, 0, as_what='pil_image')
            if has_cover:
                # There is a cover.jpg, already rendered as a pil_image
                cache_valid = False
            else:
                # No cover.jpg
                cache_valid = None
        else:
            # A cover is in the cache. Check whether it is up to date.
            # Note that if tcdata is not None then it is already a PIL image.
            has_cover, tcdata, timestamp = db.new_api.cover_or_cache(book_id, timestamp,
                                                                     as_what='pil_image')
            if has_cover:
                if tcdata is None:
                    from PIL import Image
                    # The cached cover is up-to-date. Convert the cached bytes
                    # to a PIL image
                    cache_valid = True
                    cdata = Image.open(BytesIO(cdata))
                else:
                    # The cached cover is stale
                    cache_valid = False
                    cdata = tcdata
            else:
                # We found a cached cover for a book without a cover. This can
                # happen in older version of calibre that can reuse book_ids
                # between libraries and books in one library have covers where
                # they don't in another library. This version doesn't have the
                # problem because the cache UUID is set when the database
                # changes instead of when the cache thread is created.
                tc.invalidate((book_id,))
                cache_valid = None
                cdata = None
        if has_cover and cdata is None:
            raise RuntimeError('No cover data when has_cover is True')
        return CoverTuple(book_id=book_id, has_cover=has_cover, cache_valid=cache_valid,
                          cdata=cdata, timestamp=timestamp)

    def make_thumbnail(self, cover_tuple):
        # Render the cover image data to the thumbnail size and correct format.
        # Rendering isn't needed if the cover came from the cache and the cache
        # is valid. Put newly rendered images into the cache. Returns the
        # thumbnail as a PIL Image. This method is called on the cover thread.

        cdata = cover_tuple.cdata
        book_id = cover_tuple.book_id
        tc = self.thumbnail_cache
        thumb = None
        if cover_tuple.has_cover:
            # cdata contains either the resized thumbnail, the full cover.jpg
            # rendered as a PIL image, or None if cover.jpg isn't valid
            if not cover_tuple.cache_valid:
                # The cover isn't in the cache, is stale, or isn't a valid
                # image. We might have the image from cover.jpg, in which case
                # make it into a thumbnail.
                if cdata is not None:
                    # We have an image from cover.jpg. Scale it by creating a thumbnail
                    dpr = self.device_pixel_ratio
                    page_width = int(dpr * self.delegate.cover_size.width())
                    page_height = int(dpr * self.delegate.cover_size.height())
                    scaled, nwidth, nheight = fit_image(cdata.width, cdata.height,
                                                        page_width, page_height)
                    if scaled:
                        # The image is the wrong size. Scale it.
                        if self.ignore_render_requests.is_set():
                            return None
                        # The PIL thumbnail operation works in-place, changing
                        # the source image.
                        cdata.thumbnail((int(nwidth), int(nheight)))
                        thumb = cdata
                    # Put the new thumbnail into the cache.
                    try:
                        with BytesIO() as buf:
                            cdata.save(buf, format=CACHE_FORMAT)
                            # use getbuffer() instead of getvalue() to avoid a copy
                            tc.insert(book_id, cover_tuple.timestamp, buf.getbuffer())
                        thumb = cdata
                    except Exception:
                        tc.invalidate((book_id,))
                        import traceback
                        traceback.print_exc()
                else:
                    # The cover data isn't valid. Remove it from the cache
                    tc.invalidate((book_id,))
            else:
                # Test to see if there is something wrong with the cover data in
                # the cache. If so, remove it from the cache and queue it to
                # render again. It isn't clear that this can ever happen. One
                # possibility is if different versions of calibre are used
                # interchangeably.
                def getbbox(img):
                    try:
                        return img.getbbox()
                    except Exception:
                        return None
                if getbbox(cdata) is None:
                    tc.invalidate((book_id,))
                    self.render_queue.put(book_id)
                    return None
                # The data from the cover cache is valid and is already a thumb.
                thumb = cdata
        else:
            # The book doesn't have a cover.
            if cover_tuple.cache_valid is not None:
                # Cover was removed, but it exists in cache. Remove it from the cache
                tc.invalidate((book_id,))
            thumb = None
        # Conversion to QPixmap needs RGBA data. Do it here rather than in the
        # GUI thread. This check doesn't need to be wrapped in
        #     if thumb is not None:
        # because None is a first-class object with no attributes.
        if getattr(thumb, 'mode', None) == 'RGB':
            thumb = thumb.convert('RGBA')
        # Return the thumbnail, which is either None or a PIL Image. If not None
        # the image will be converted to a QPixmap on the GUI thread. Putting
        # None into the CoverCache ensures re-rendering won't try again.
        return thumb

    def re_render(self, book_id, thumb):
        # This is called on the GUI thread when a cover thumbnail is not in the
        # CoverCache. The parameter "thumb" is either None if there is no cover
        # or a PIL Image of the thumbnail.
        self.delegate.cover_cache.clear_staging()
        if thumb is not None:
            # Convert the image to a QPixmap
            thumb = convert_PIL_image_to_pixmap(thumb, self.device_pixel_ratio)
        self.delegate.cover_cache.set(book_id, thumb)
        m = self.model()
        try:
            index = m.db.row(book_id)
        except (IndexError, ValueError, KeyError, AttributeError):
            return
        self.update(m.index(index, 0))

    def shutdown(self):
        self.ignore_render_requests.set()
        self.delegate.render_queue.put(None)
        self.thumbnail_cache.shutdown()

    def set_database(self, newdb, stage=0):
        self.dbref = weakref.ref(newdb)
        if stage == 0:
            self.ignore_render_requests.set()
            try:
                for x in (self.delegate.cover_cache, self.thumbnail_cache):
                    self.model().db.new_api.remove_cover_cache(x)
            except AttributeError:
                pass  # db is None
            for x in (self.delegate.cover_cache, self.thumbnail_cache):
                newdb.new_api.add_cover_cache(x)
            # This must be done here so the UUID in the cache is changed when
            # libraries are switched.
            self.thumbnail_cache.set_database(newdb)
            try:
                # Use a timeout so that if, for some reason, the render thread
                # gets stuck, we don't deadlock, future covers won't get
                # rendered, but this is better than a deadlock
                join_with_timeout(self.delegate.render_queue)
            except RuntimeError:
                print('Cover rendering thread is stuck!')
            finally:
                self.ignore_render_requests.clear()
        else:
            self.delegate.cover_cache.clear()

    def select_rows(self, rows):
        sel = QItemSelection()
        sm = self.selectionModel()
        m = self.model()
        # Create a range based selector for each set of contiguous rows
        # as supplying selectors for each individual row causes very poor
        # performance if a large number of rows has to be selected.
        for k, g in itertools.groupby(enumerate(rows), lambda i_x: i_x[0]-i_x[1]):
            group = list(map(operator.itemgetter(1), g))
            sel.merge(QItemSelection(m.index(min(group), 0), m.index(max(group), 0)), QItemSelectionModel.SelectionFlag.Select)
        sm.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def selectAll(self):
        # We re-implement this to ensure that only indexes from column 0 are
        # selected. The base class implementation selects all columns. This
        # causes problems with selection syncing, see
        # https://bugs.launchpad.net/bugs/1236348
        m = self.model()
        sm = self.selectionModel()
        sel = QItemSelection(m.index(0, 0), m.index(m.rowCount(QModelIndex())-1, 0))
        sm.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def set_current_row(self, row):
        sm = self.selectionModel()
        sm.setCurrentIndex(self.model().index(row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)

    def set_context_menu(self, menu):
        self.context_menu = menu

    def contextMenuEvent(self, event):
        if self.context_menu is None:
            return
        from calibre.gui2.main_window import clone_menu
        m = clone_menu(self.context_menu) if islinux else self.context_menu
        m.popup(event.globalPos())
        event.accept()

    def get_selected_ids(self):
        m = self.model()
        return [m.id(i) for i in self.selectionModel().selectedIndexes()]

    def restore_vpos(self, vpos):
        self.verticalScrollBar().setValue(vpos)

    def restore_hpos(self, hpos):
        pass

    def handle_mouse_move_event(self, ev):
        # handle shift drag to extend selections
        if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            return super().mouseMoveEvent(ev)
        index = self.indexAt(ev.pos())
        if not index.isValid() or not self.shift_click_start_data:
            return
        m = self.model()
        ci = m.index(self.shift_click_start_data[0], 0)
        if not ci.isValid():
            return
        sm = self.selectionModel()
        sm.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        if not sm.hasSelection():
            sm.select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            return True
        cr = ci.row()
        tgt = index.row()
        if cr == tgt:
            sm.select(index, QItemSelectionModel.SelectionFlag.Select)
            return
        if cr < tgt:
            # mouse is moved after the start pos
            top = min(self.shift_click_start_data[1], cr)
            bottom = tgt
        else:
            top = tgt
            bottom = max(self.shift_click_start_data[2], cr)
        sm.select(QItemSelection(m.index(top, 0), m.index(bottom, 0)), QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def handle_mouse_press_event(self, ev):
        # Shift-Click in QListView is broken. It selects extra items in
        # various circumstances, for example, click on some item in the
        # middle of a row then click on an item in the next row, all items
        # in the first row will be selected instead of only items after the
        # middle item.
        if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            return super().mousePressEvent(ev)
        self.shift_click_start_data = None
        index = self.indexAt(ev.pos())
        if not index.isValid():
            return
        sm = self.selectionModel()
        ci = self.currentIndex()
        try:
            if not ci.isValid():
                return
            sm.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
            if not sm.hasSelection():
                sm.select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                return
            cr = ci.row()
            tgt = index.row()
            top = self.model().index(min(cr, tgt), 0)
            bottom = self.model().index(max(cr, tgt), 0)
            sm.select(QItemSelection(top, bottom), QItemSelectionModel.SelectionFlag.Select)
        finally:
            min_row = self.model().rowCount(QModelIndex())
            max_row = -1
            for idx in sm.selectedIndexes():
                r = idx.row()
                if r < min_row:
                    min_row = r
                elif r > max_row:
                    max_row = r
            self.shift_click_start_data = index.row(), min_row, max_row

    def indices_for_merge(self, resolved=True):
        return self.selectionModel().selectedIndexes()

    def number_of_columns(self):
        # Number of columns currently visible in the grid
        if self._ncols is None:
            dpr = self.device_pixel_ratio
            width = int(dpr * self.delegate.cover_size.width())
            height = int(dpr * self.delegate.cover_size.height())
            step = max(10, self.spacing())
            for y in range(step, 2 * height, step):
                for x in range(step, 2 * width, step):
                    i = self.indexAt(QPoint(x, y))
                    if i.isValid():
                        for x in range(self.viewport().width() - step, self.viewport().width() - width, -step):
                            j = self.indexAt(QPoint(x, y))
                            if j.isValid():
                                self._ncols = j.row() - i.row() + 1
                                return self._ncols
        return self._ncols

    def keyPressEvent(self, ev):
        if handle_enter_press(self, ev, self.start_view_animation, False):
            return
        k = ev.key()
        if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier and k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            ci = self.currentIndex()
            if not ci.isValid():
                return
            c = ci.row()
            ncols = self.number_of_columns() or 1
            delta = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -ncols, Qt.Key.Key_Down: ncols}[k]
            n = max(0, min(c + delta, self.model().rowCount(None) - 1))
            if n == c:
                return
            sm = self.selectionModel()
            rows = {i.row() for i in sm.selectedIndexes()}
            if rows:
                mi, ma = min(rows), max(rows)
                end = mi if c == ma else ma if c == mi else c
            else:
                end = c
            top = self.model().index(min(n, end), 0)
            bottom = self.model().index(max(n, end), 0)
            sm.select(QItemSelection(top, bottom), QItemSelectionModel.SelectionFlag.ClearAndSelect)
            sm.setCurrentIndex(self.model().index(n, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        else:
            return QListView.keyPressEvent(self, ev)

    @property
    def current_book(self):
        ci = self.currentIndex()
        if ci.isValid():
            try:
                return self.model().db.data.index_to_id(ci.row())
            except (IndexError, ValueError, KeyError, TypeError, AttributeError):
                pass

    def current_book_state(self):
        return self.current_book

    def restore_current_book_state(self, state):
        book_id = state
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        try:
            row = self.model().db.data.id_to_index(book_id)
        except (IndexError, ValueError, KeyError, TypeError, AttributeError):
            return
        self.set_current_row(row)
        self.select_rows((row,))
        self.scrollTo(self.model().index(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    def marked_changed(self, old_marked, current_marked):
        changed = old_marked | current_marked
        m = self.model()
        for book_id in changed:
            try:
                self.update(m.index(m.db.data.id_to_index(book_id), 0))
            except ValueError:
                pass

    def moveCursor(self, action, modifiers):
        action = QAbstractItemView.CursorAction(action)
        index = QListView.moveCursor(self, action, modifiers)
        if action in (QAbstractItemView.CursorAction.MoveLeft, QAbstractItemView.CursorAction.MoveRight) and index.isValid():
            ci = self.currentIndex()
            if ci.isValid() and index.row() == ci.row():
                nr = index.row() + (1 if action == QAbstractItemView.CursorAction.MoveRight else -1)
                if 0 <= nr < self.model().rowCount(QModelIndex()):
                    index = self.model().index(nr, 0)
        return index

    def selectionCommand(self, index, event):
        if event and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Home, Qt.Key.Key_End
                                    ) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        return super().selectionCommand(index, event)

    def wheelEvent(self, ev):
        if ev.phase() not in (Qt.ScrollPhase.ScrollUpdate, Qt.ScrollPhase.NoScrollPhase, Qt.ScrollPhase.ScrollMomentum):
            return
        number_of_pixels = ev.pixelDelta()
        number_of_degrees = ev.angleDelta() / 8.0
        b = self.verticalScrollBar()
        if number_of_pixels.isNull() or islinux:
            # pixelDelta() is broken on linux with wheel mice
            dy = number_of_degrees.y() / 15.0
            # Scroll by approximately half a row
            dy = math.ceil((dy) * b.singleStep() / 2.0)
        else:
            dy = number_of_pixels.y()
        if abs(dy) > 0:
            b.setValue(b.value() - dy)

    def paintEvent(self, ev):
        dpr = self.device_pixel_ratio
        page_width = int(dpr * self.delegate.cover_size.width())
        page_height = int(dpr * self.delegate.cover_size.height())
        size_changed = self.thumbnail_cache.set_thumbnail_size(page_width, page_height)
        if size_changed:
            self.delegate.cover_cache.clear()

        return super().paintEvent(ev)

# }}}
