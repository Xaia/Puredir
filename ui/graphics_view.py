# ui/graphics_view.py

from PyQt5.QtWidgets import QGraphicsView, QMenu, QMessageBox, QApplication
from PyQt5.QtCore import Qt, QRect, QPoint, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import QWheelEvent, QMouseEvent, QCursor, QPainter
from utils.constants import (
    EDGE_RESIZE_MARGIN, RIGHT_CLICK_DRAG_THRESHOLD, INFINITE_CANVAS_SIZE
)
from ui.draggable_pixmap_item import DraggablePixmapItem


class GraphicsView(QGraphicsView):
    # Define custom signals for Clear Canvas, Settings, and Reset View
    clear_canvas_signal = pyqtSignal()
    open_settings_signal = pyqtSignal()
    reset_view_signal = pyqtSignal()

    def __init__(self, scene, mainwindow):
        super().__init__(scene)
        self.mainwindow = mainwindow
        self.zoom_factor = 1.15

        # In GraphicsView __init__
        self.setCacheMode(QGraphicsView.CacheBackground)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Disable scroll bars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)

        self.scale_factor_total = 1.0

        # Panning attributes
        self.panning = False
        self.pan_start_view = QPoint()

        # Right-click dragging attributes
        self.right_click_pressed = False
        self.right_click_press_pos = QPoint()
        self.right_click_dragging = False  # Initialized to prevent AttributeError
        self.win_drag_start_global = QPoint()
        self.win_start_pos = QPoint()

        # Window resizing attributes
        self.resizing_window = False
        self.resize_direction = None
        self.window_drag_start_pos = QPoint()
        self.window_start_geometry = None

    def wheelEvent(self, event: QWheelEvent):
        """
        Handles mouse wheel events to perform zooming.

        Args:
            event (QWheelEvent): The wheel event.
        """
        old_pos = self.mapToScene(event.pos())
        if event.angleDelta().y() > 0:
            zoom = self.zoom_factor
        else:
            zoom = 1 / self.zoom_factor

        self.scale(zoom, zoom)
        self.scale_factor_total *= zoom

        new_pos = self.mapToScene(event.pos())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def mousePressEvent(self, event: QMouseEvent):
        """
        Handles mouse press events to initiate panning, right-click dragging, or window resizing.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        if event.button() == Qt.MiddleButton:
            # Initiate panning
            self.panning = True
            self.pan_start_view = event.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            # Initiate right-click dragging
            self.right_click_pressed = True
            self.right_click_dragging = False  # Reset dragging state
            self.right_click_press_pos = event.pos()
            self.win_drag_start_global = event.globalPos()
            self.win_start_pos = self.mainwindow.pos()
            event.accept()
        elif event.button() == Qt.LeftButton:
            # Check if the click is near the window edge for resizing
            edge = self.get_resize_direction(event.pos())
            if edge:
                self.resizing_window = True
                self.resize_direction = edge
                self.window_drag_start_pos = event.globalPos()
                self.window_start_geometry = self.mainwindow.geometry()
                event.accept()
            else:
                # Pass the event to the base class for default handling
                super().mousePressEvent(event)
        else:
            # Pass other buttons to the base class
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        Handles mouse move events to perform panning, right-click dragging, window resizing, or cursor changes.

        Args:
            event (QMouseEvent): The mouse move event.
        """
        if self.panning and (event.buttons() & Qt.MiddleButton):
            # Perform panning
            dx = (event.x() - self.pan_start_view.x()) / self.scale_factor_total
            dy = (event.y() - self.pan_start_view.y()) / self.scale_factor_total
            self.translate(dx, dy)
            self.pan_start_view = event.pos()
            event.accept()
        elif self.right_click_pressed and (event.buttons() & Qt.RightButton):
            # Calculate movement distance
            move_dist = (event.pos() - self.right_click_press_pos)
            if not self.right_click_dragging:
                # Determine if movement exceeds the threshold to start dragging
                if (abs(move_dist.x()) > RIGHT_CLICK_DRAG_THRESHOLD or
                        abs(move_dist.y()) > RIGHT_CLICK_DRAG_THRESHOLD):
                    self.right_click_dragging = True

            if self.right_click_dragging:
                # Perform window dragging
                delta = event.globalPos() - self.win_drag_start_global
                new_pos = self.win_start_pos + delta
                self.mainwindow.move(new_pos)
                event.accept()
            else:
                # Pass the event to the base class for default handling
                super().mouseMoveEvent(event)
        elif self.resizing_window and (event.buttons() & Qt.LeftButton):
            # Perform window resizing
            self.handle_window_resize(event.globalPos())
            event.accept()
        else:
            # Change cursor based on hover position
            if not self.panning and not self.resizing_window and not self.right_click_dragging:
                edge = self.get_resize_direction(event.pos())
                if edge:
                    if edge in ('left', 'right'):
                        self.setCursor(Qt.SizeHorCursor)
                    elif edge in ('top', 'bottom'):
                        self.setCursor(Qt.SizeVerCursor)
                    elif edge in ('top-left', 'bottom-right'):
                        self.setCursor(Qt.SizeFDiagCursor)
                    elif edge in ('top-right', 'bottom-left'):
                        self.setCursor(Qt.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        Handles mouse release events to terminate panning, right-click dragging, or window resizing.

        Args:
            event (QMouseEvent): The mouse release event.
        """
        if event.button() == Qt.MiddleButton:
            # Terminate panning
            self.panning = False
            event.accept()
        elif event.button() == Qt.RightButton:
            if self.right_click_pressed and not self.right_click_dragging:
                # Show context menu if it wasn't a drag
                self.show_context_menu(event.globalPos())
            # Reset right-click states
            self.right_click_pressed = False
            self.right_click_dragging = False
            event.accept()
        elif event.button() == Qt.LeftButton and self.resizing_window:
            # Terminate window resizing
            self.resizing_window = False
            self.resize_direction = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            # Pass the event to the base class for default handling
            super().mouseReleaseEvent(event)

    def show_context_menu(self, global_pos):
        """
        Displays a context menu with options to reset the view, clear the canvas, open settings, or exit the application.

        Args:
            global_pos (QPoint): The global position where the menu should appear.
        """
        menu = QMenu()

        # Existing actions
        reset_action = menu.addAction("Reset to Center")
        clear_canvas_action = menu.addAction("Clear Canvas")
        settings_action = menu.addAction("Settings")
        menu.addSeparator()
        exit_action = menu.addAction("Exit")

        chosen = menu.exec_(global_pos)
        if chosen == exit_action:
            QApplication.quit()
        elif chosen == reset_action:
            # Emit signal to reset view
            self.reset_view_signal.emit()
        elif chosen == clear_canvas_action:
            # Emit signal to clear canvas
            self.clear_canvas_signal.emit()
        elif chosen == settings_action:
            # Emit signal to open settings
            self.open_settings_signal.emit()

    def get_resize_direction(self, pos):
        """
        Determines the direction of window resizing based on the mouse position.

        Args:
            pos (QPoint): The position of the mouse within the view.

        Returns:
            str or None: The direction for resizing (e.g., 'top-left', 'right') or None if not near an edge.
        """
        rect = self.rect()
        x, y = pos.x(), pos.y()
        left = x < EDGE_RESIZE_MARGIN
        right = x > rect.width() - EDGE_RESIZE_MARGIN
        top = y < EDGE_RESIZE_MARGIN
        bottom = y > rect.height() - EDGE_RESIZE_MARGIN

        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        return None

    def handle_window_resize(self, global_pos):
        """
        Handles the resizing of the main window based on mouse movement.

        Args:
            global_pos (QPoint): The current global mouse position.
        """
        dx = global_pos.x() - self.window_drag_start_pos.x()
        dy = global_pos.y() - self.window_drag_start_pos.y()
        g = self.window_start_geometry

        left = g.x()
        top = g.y()
        right = g.x() + g.width()
        bottom = g.y() + g.height()

        if 'left' in self.resize_direction:
            new_left = left + dx
            if new_left < right - 100:  # Minimum width
                left = new_left
        if 'right' in self.resize_direction:
            new_right = right + dx
            if new_right > left + 100:  # Minimum width
                right = new_right
        if 'top' in self.resize_direction:
            new_top = top + dy
            if new_top < bottom - 100:  # Minimum height
                top = new_top
        if 'bottom' in self.resize_direction:
            new_bottom = bottom + dy
            if new_bottom > top + 100:  # Minimum height
                bottom = new_bottom

        # Apply the new geometry to the main window
        self.mainwindow.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))
