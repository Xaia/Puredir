# ui/folder_backdrop_item.py

from PyQt5.QtWidgets import QGraphicsItem
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt5.QtCore import QRectF, Qt


class FolderBackdropItem(QGraphicsItem):
    """
    Custom QGraphicsItem that combines a backdrop rectangle and a folder name text.
    """

    def __init__(self, folder_name, rect, parent=None):
        """
        Initializes the FolderBackdropItem.

        Args:
            folder_name (str): The name of the folder.
            rect (QRectF): The rectangle defining the backdrop's position and size.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.folder_name = folder_name
        self.backdrop_rect = rect
        self.setZValue(-1)  # Ensure backdrop is behind images
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        # Text properties
        self.font = QFont("Arial", 14)
        self.text_color = QColor(Qt.white)
        self.text_margin = 5  # Space between text and backdrop

        # Calculate text bounding box using QFontMetrics
        self.font_metrics = QFontMetrics(self.font)
        self.text_bbox = self.font_metrics.boundingRect(self.folder_name)

        # Define text_rect positioned above the backdrop_rect
        self.text_rect = QRectF(
            self.backdrop_rect.left(),
            self.backdrop_rect.top() - self.text_bbox.height() - self.text_margin,
            self.backdrop_rect.width(),
            self.text_bbox.height()
        )

        # Define the overall bounding rectangle
        self.total_rect = QRectF(
            self.backdrop_rect.left(),
            self.text_rect.top(),
            self.backdrop_rect.width(),
            self.backdrop_rect.height() + self.text_bbox.height() + self.text_margin
        )
        
    def paint(self, painter: QPainter, option, widget=None):
        # Draw backdrop
        painter.setBrush(QColor(40, 40, 40, 100))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.backdrop_rect)

        # Draw folder name with elision
        painter.setFont(self.font)
        painter.setPen(self.text_color)
        fm = QFontMetrics(self.font)
        elided_text = fm.elidedText(self.folder_name, Qt.ElideRight, self.text_rect.width())
        painter.drawText(self.text_rect, Qt.AlignCenter, elided_text)

    def boundingRect(self):
        """
        Defines the outer bounds of the item as the total rectangle.

        Returns:
            QRectF: The bounding rectangle.
        """
        return self.total_rect

    def paint(self, painter: QPainter, option, widget=None):
        """
        Paints the backdrop and the folder name.

        Args:
            painter (QPainter): The painter used for drawing.
            option: Style options.
            widget: The widget being painted on.
        """
        # Draw backdrop
        painter.setBrush(QColor(40, 40, 40, 100))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.backdrop_rect)

        # Draw folder name
        painter.setFont(self.font)
        painter.setPen(self.text_color)
        painter.drawText(self.text_rect, Qt.AlignCenter, self.folder_name)
