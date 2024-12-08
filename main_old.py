import sys
import os
import json
import string
from math import ceil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QFileDialog,
    QGraphicsPixmapItem, QTreeWidget, QTreeWidgetItem, QMessageBox,
    QStyleFactory, QSplitter, QMenu, QTabWidget
)
from PyQt5.QtCore import (
    Qt, QPointF, QPoint, QRectF, QEvent, QRect
)
from PyQt5.QtGui import (
    QWheelEvent, QMouseEvent, QPixmap, QPainter, QPalette, QColor
)

SUPPORTED_IMAGE_FORMATS = ['.png', '.xpm', '.jpg', '.jpeg', '.bmp', '.gif']
FAVORITES_FILE = "favorites.json"

UNIFORM_HEIGHT = 150
COLUMNS = 5
SPACING_X = 10
SPACING_Y = 10
EDGE_RESIZE_MARGIN = 20
INFINITE_CANVAS_SIZE = 10_000_000


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
        # Items only accept left button
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
        edge_size = 10
        rect = self.boundingRect()
        return QRectF(rect.width() - edge_size, rect.height() - edge_size, edge_size, edge_size).contains(pos)


class GraphicsView(QGraphicsView):
    def __init__(self, scene, mainwindow):
        super().__init__(scene)
        self.mainwindow = mainwindow
        self.zoom_factor = 1.15

        # Disable scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # We handle zoom-to-cursor manually, so no anchor
        self.setTransformationAnchor(QGraphicsView.NoAnchor)

        # Track total scale factor to adjust panning speed
        self.scale_factor_total = 1.0

        # Middle-click panning variables
        self.panning = False
        self.pan_start_view = QPoint()

        # Right-click window moving
        self.moving_window = False
        self.win_drag_start_global = QPoint()
        self.win_start_pos = QPoint()

        # Resizing variables
        self.resizing_window = False
        self.resize_direction = None
        self.window_drag_start_pos = QPoint()
        self.window_start_geometry = None

    def wheelEvent(self, event: QWheelEvent):
        # Zoom-to-cursor:
        # 1. Get old scene pos under cursor
        old_pos = self.mapToScene(event.pos())

        # 2. Determine zoom factor
        if event.angleDelta().y() > 0:
            zoom = self.zoom_factor
        else:
            zoom = 1 / self.zoom_factor

        # 3. Scale the view
        self.scale(zoom, zoom)
        self.scale_factor_total *= zoom

        # 4. Get new scene pos under cursor after scaling
        new_pos = self.mapToScene(event.pos())
        # 5. Translate to keep old_pos under the cursor
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            # Start middle-click panning
            self.panning = True
            self.pan_start_view = event.pos()
            print(f"Middle pressed at: {self.pan_start_view}")
            event.accept()
        elif event.button() == Qt.RightButton:
            # Start right-click moving window
            self.moving_window = True
            self.win_drag_start_global = event.globalPos()
            self.win_start_pos = self.mainwindow.pos()
            print(f"Right click pressed: start pos={self.win_start_pos}, global start={self.win_drag_start_global}")
            event.accept()
        elif event.button() == Qt.LeftButton:
            # Check edges for resizing
            edge = self.get_resize_direction(event.pos())
            if edge:
                self.resizing_window = True
                self.resize_direction = edge
                self.window_drag_start_pos = event.globalPos()
                self.window_start_geometry = self.mainwindow.geometry()
                print(f"Left click on edge: {edge}, geometry={self.window_start_geometry}")
                event.accept()
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.panning and (event.buttons() & Qt.MiddleButton):
            # Middle-click panning: Adjust dx, dy by scale_factor_total to keep speed constant?
            # The user wants the same speed no matter zoom.
            # If we do not adjust by scale_factor_total, speed changes with zoom.
            # To keep speed the same in scene coordinates, divide by self.scale_factor_total.
            dx = (event.x() - self.pan_start_view.x()) / self.scale_factor_total
            dy = (event.y() - self.pan_start_view.y()) / self.scale_factor_total

            print(f"Middle drag: dx={dx}, dy={dy}, scale_factor_total={self.scale_factor_total}")

            # Move scene in scene-consistent speed
            self.translate(dx, dy)
            self.pan_start_view = event.pos()
            event.accept()
        elif self.moving_window and (event.buttons() & Qt.RightButton):
            delta = event.globalPos() - self.win_drag_start_global
            new_pos = self.win_start_pos + delta
            self.mainwindow.move(new_pos)
            event.accept()
        elif self.resizing_window and (event.buttons() & Qt.LeftButton):
            self.handle_window_resize(event.globalPos())
            event.accept()
        else:
            # Update cursor if near edges
            if not self.panning and not self.moving_window and not self.resizing_window:
                edge = self.get_resize_direction(event.pos())
                if edge:
                    if edge in ('left', 'right'):
                        self.setCursor(Qt.SizeHorCursor)
                    elif edge in ('top', 'bottom'):
                        self.setCursor(Qt.SizeVerCursor)
                    else:
                        if edge in ('top-left', 'bottom-right'):
                            self.setCursor(Qt.SizeFDiagCursor)
                        else:
                            self.setCursor(Qt.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self.panning = False
            print("Middle click released, stop panning.")
            event.accept()
        elif event.button() == Qt.RightButton:
            self.moving_window = False
            print("Right click released, stop moving window.")
            event.accept()
        elif event.button() == Qt.LeftButton and self.resizing_window:
            self.resizing_window = False
            self.resize_direction = None
            self.setCursor(Qt.ArrowCursor)
            print("Left button released, stop resizing.")
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def get_resize_direction(self, pos):
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
        dx = global_pos.x() - self.window_drag_start_pos.x()
        dy = global_pos.y() - self.window_drag_start_pos.y()
        g = self.window_start_geometry

        left = g.x()
        top = g.y()
        right = g.x() + g.width()
        bottom = g.y() + g.height()

        if 'left' in self.resize_direction:
            new_left = left + dx
            if new_left < right - 100:
                left = new_left
        if 'right' in self.resize_direction:
            new_right = right + dx
            if new_right > left + 100:
                right = new_right
        if 'top' in self.resize_direction:
            new_top = top + dy
            if new_top < bottom - 100:
                top = new_top
        if 'bottom' in self.resize_direction:
            new_bottom = bottom + dy
            if new_bottom > top + 100:
                bottom = new_bottom

        self.mainwindow.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Frameless window
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("PureRef Prototype")
        self.resize(1600, 900)
        self.apply_dark_theme()

        self.scene = QGraphicsScene()
        # Large scene rect for infinite canvas
        self.scene.setSceneRect(-INFINITE_CANVAS_SIZE//2, -INFINITE_CANVAS_SIZE//2, INFINITE_CANVAS_SIZE, INFINITE_CANVAS_SIZE)

        self.favorites = self.load_favorites_from_json()
        self.loaded_images = {}
        self.current_y = 0

        self.directory_tree = QTreeWidget()
        self.directory_tree.setHeaderLabel("Folders")
        self.directory_tree.setMinimumWidth(200)
        self.directory_tree.itemChanged.connect(self.handle_directory_item_changed)
        self.directory_tree.itemExpanded.connect(self.on_item_expanded)
        self.directory_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.directory_tree.customContextMenuRequested.connect(self.on_directories_context_menu)
        self.initialize_directory_tree()
        self.directory_tree.expandAll()

        self.favorites_tree = QTreeWidget()
        self.favorites_tree.setHeaderLabel("Favorites")
        self.favorites_tree.itemChanged.connect(self.handle_favorites_item_changed)
        for folder_path in self.favorites:
            self.add_favorite_item(folder_path)

        self.view = GraphicsView(self.scene, self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.directory_tree, "Directories")
        self.tabs.addTab(self.favorites_tree, "Favorites")

        splitter = QSplitter()
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1300])

        self.setCentralWidget(splitter)

    def apply_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(dark_palette)

        dark_stylesheet = """
            QTreeWidget {
                background-color: #2d2d2d;
                color: white;
            }
            QTreeWidget::item:selected {
                background-color: #3a3a3a;
            }
            QTabWidget::pane {
                border: 0px;
            }
            QTabBar::tab {
                background: #3a3a3a;
                padding: 5px;
                color: white;
            }
            QTabBar::tab:selected {
                background: #4a4a4a;
            }
            QMainWindow {
                background-color: #353535;
            }
        """
        QApplication.instance().setStyleSheet(dark_stylesheet)

    def initialize_directory_tree(self):
        self.directory_tree.clear()
        if sys.platform.startswith('win'):
            drives = self.get_windows_drives()
            for drive in drives:
                self.populate_tree(drive, self.directory_tree)
        else:
            self.populate_tree("/", self.directory_tree)

    def get_windows_drives(self):
        drives = []
        if sys.platform.startswith('win'):
            try:
                from ctypes import windll
                bitmask = windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drives.append(f"{letter}:\\")
                    bitmask >>= 1
            except:
                pass
        return drives

    def populate_tree(self, root_path, parent_widget):
        root_name = os.path.basename(root_path)
        if not root_name.strip():
            root_name = root_path
        root_item = QTreeWidgetItem(parent_widget, [root_name])
        root_item.setData(0, Qt.UserRole, root_path)
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        root_item.setCheckState(0, Qt.Unchecked)
        if self.has_subdirectories(root_path):
            dummy = QTreeWidgetItem()
            dummy.setText(0, "")
            root_item.addChild(dummy)

    def has_subdirectories(self, path):
        try:
            for entry in os.scandir(path):
                if entry.is_dir():
                    return True
        except PermissionError:
            pass
        return False

    def on_item_expanded(self, item):
        if item.childCount() == 1 and not item.child(0).text(0):
            item.removeChild(item.child(0))
            path = item.data(0, Qt.UserRole)
            try:
                for entry in os.scandir(path):
                    if entry.is_dir():
                        child_item = QTreeWidgetItem(item, [entry.name])
                        child_item.setData(0, Qt.UserRole, entry.path)
                        child_item.setFlags(child_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        child_item.setCheckState(0, Qt.Unchecked)
                        if self.has_subdirectories(entry.path):
                            dummy = QTreeWidgetItem()
                            dummy.setText(0, "")
                            child_item.addChild(dummy)
            except PermissionError:
                QMessageBox.warning(self, "Permission Denied", f"Cannot access {path}")

    def handle_directory_item_changed(self, item, column):
        self.directory_tree.blockSignals(True)
        folder_path = item.data(0, Qt.UserRole)
        if item.checkState(0) == Qt.Checked:
            self.load_images_from_folder(folder_path)
        else:
            self.unload_images_from_folder(folder_path)
        self.directory_tree.blockSignals(False)

    def handle_favorites_item_changed(self, item, column):
        self.favorites_tree.blockSignals(True)
        folder_path = item.data(0, Qt.UserRole)
        if item.checkState(0) == Qt.Checked:
            self.load_images_from_folder(folder_path)
        else:
            self.unload_images_from_folder(folder_path)
        self.favorites_tree.blockSignals(False)

    def load_images_from_folder(self, folder_path):
        file_paths = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if self.is_supported_image(file):
                    file_paths.append(os.path.join(root, file))

        if not file_paths:
            return

        folder_items = []
        i = 0
        while i < len(file_paths):
            row_files = file_paths[i:i+COLUMNS]
            max_height = UNIFORM_HEIGHT
            current_x = 0
            for fpath in row_files:
                pix = QPixmap(fpath)
                if pix.isNull():
                    continue
                scale_factor = UNIFORM_HEIGHT / pix.height()
                displayed_width = pix.width() * scale_factor

                item = DraggablePixmapItem(pix)
                item.setAcceptedMouseButtons(Qt.LeftButton)
                self.scene.addItem(item)
                item.setPos(QPointF(current_x, self.current_y))
                item.setScale(scale_factor)

                folder_items.append(item)
                current_x += displayed_width + SPACING_X

            self.current_y += UNIFORM_HEIGHT + SPACING_Y
            i += COLUMNS

        if folder_items:
            self.loaded_images[folder_path] = folder_items

    def unload_images_from_folder(self, folder_path):
        for item in self.loaded_images.get(folder_path, []):
            self.scene.removeItem(item)
        if folder_path in self.loaded_images:
            del self.loaded_images[folder_path]

    def is_supported_image(self, filename):
        _, ext = os.path.splitext(filename)
        return ext.lower() in SUPPORTED_IMAGE_FORMATS

    def on_directories_context_menu(self, pos):
        item = self.directory_tree.itemAt(pos)
        if item:
            folder_path = item.data(0, Qt.UserRole)
            menu = QMenu()
            add_fav_action = menu.addAction("Add to Favorites")
            action = menu.exec_(self.directory_tree.mapToGlobal(pos))
            if action == add_fav_action:
                self.add_favorite(folder_path)
                self.save_favorites_to_json()

    def add_favorite(self, folder_path):
        if folder_path not in self.favorites:
            self.favorites.append(folder_path)
        self.add_favorite_item(folder_path)
        self.save_favorites_to_json()

    def add_favorite_item(self, folder_path):
        fav_item = QTreeWidgetItem([os.path.basename(folder_path)])
        fav_item.setData(0, Qt.UserRole, folder_path)
        fav_item.setFlags(fav_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        fav_item.setCheckState(0, Qt.Unchecked)
        self.favorites_tree.addTopLevelItem(fav_item)

    def closeEvent(self, event):
        event.accept()

    def load_favorites_from_json(self):
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        return []

    def save_favorites_to_json(self):
        with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.favorites, f, ensure_ascii=False, indent=4)


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
