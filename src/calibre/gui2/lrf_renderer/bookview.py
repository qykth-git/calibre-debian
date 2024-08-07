__license__   = 'GPL v3'
__copyright__ = '2008, Kovid Goyal <kovid at kovidgoyal.net>'

from qt.core import QGraphicsView, QSize


class BookView(QGraphicsView):

    MINIMUM_SIZE = QSize(400, 500)

    def __init__(self, parent=None):
        QGraphicsView.__init__(self, parent)
        self.preferred_size = self.MINIMUM_SIZE

    def minimumSizeHint(self):
        return self.MINIMUM_SIZE

    def sizeHint(self):
        return self.preferred_size

    def resize_for(self, width, height):
        self.preferred_size = QSize(width, height)
