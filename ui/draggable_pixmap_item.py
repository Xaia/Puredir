# ui/draggable_pixmap_item.py

from PyQt5.QtWidgets import QGraphicsPixmapItem
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QCursor

EDGE_SIZE = 10

class DraggablePixmapItem(QGraphicsPixmapItem):
    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setFlags(
            self.flags() |
            QGraphicsPixmapItem.ItemIsMovable |
            QGraphicsPixmapItem.ItemIsSelectable |
            QGraphicsPixmapItem.ItemSendsGeometryChanges
        )
        self.setTransformationMode(Qt.SmoothTransformation)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.is_rotating = False

    def hoverMoveEvent(self, event):
        if self.is_near_edge(event.pos()):
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_near_edge(event.pos()):
            self.is_rotating = True
            self.setCursor(Qt.SizeAllCursor)
            self.orig_pos = event.scenePos()
            self.orig_angle = self.rotation()
        else:
            self.is_rotating = False
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_rotating:
            pos = event.scenePos()
            delta = pos - self.orig_pos
            angle = self.orig_angle + delta.x()
            self.setRotation(angle)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_rotating = False
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def is_near_edge(self, pos):
        rect = self.boundingRect()
        edge_rect = QRectF(rect.width() - EDGE_SIZE, rect.height() - EDGE_SIZE, EDGE_SIZE, EDGE_SIZE)
        return edge_rect.contains(pos)
