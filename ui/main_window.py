# ui/main_window.py

import os
from PyQt5.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QStyleFactory, QSplitter,
    QTabWidget, QProgressBar, QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem,
    QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QApplication, QMenu
)
from PyQt5.QtCore import Qt, QRect, QPoint, QPointF, QTimer, QThreadPool
from PyQt5.QtGui import QPalette, QColor, QFont, QPen  # Added QPen

from managers.favorites_manager import FavoritesManager
from managers.directory_manager import DirectoryManager
from workers.image_loader import ImageLoadWorker
from ui.graphics_view import GraphicsView
from ui.draggable_pixmap_item import DraggablePixmapItem
from utils.constants import (
    SUPPORTED_IMAGE_FORMATS,
    UNIFORM_HEIGHT, COLUMNS, SPACING_X, SPACING_Y,
    INFINITE_CANVAS_SIZE, RIGHT_CLICK_DRAG_THRESHOLD
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("PureRef Prototype")
        self.resize(1600, 900)
        self.apply_dark_theme()

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max(QThreadPool.globalInstance().maxThreadCount(), 4))

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()

        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-INFINITE_CANVAS_SIZE//2, -INFINITE_CANVAS_SIZE//2, INFINITE_CANVAS_SIZE, INFINITE_CANVAS_SIZE)

        self.view = GraphicsView(self.scene, self)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0,0,0,0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.view)
        right_layout.addWidget(self.progress_bar)

        self.favorites_manager = FavoritesManager()
        self.loaded_images = {}  # folder_path -> list of items
        self.current_folder_offset_x = 0  # where the next folder should start horizontally

        self.folder_load_counts = {}
        self.folder_loaded_counts = {}
        self.folder_placement_data = {}

        self.directory_tree = QTreeWidget()
        self.favorites_tree = QTreeWidget()

        self.directory_manager = DirectoryManager(self.directory_tree)
        self.directory_manager.initialize_directory_tree()

        self.favorites_tree.setHeaderLabel("Favorites")
        self.favorites_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        # Context menu connections will be handled below

        self.favorites_tree.customContextMenuRequested.connect(self.on_favorites_context_menu)
        self.favorites_tree.itemChanged.connect(self.handle_favorites_item_changed)

        for folder_path in self.favorites_manager.favorites:
            self.add_favorite_item(folder_path)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.directory_tree, "Directories")
        self.tabs.addTab(self.favorites_tree, "Favorites")

        splitter = QSplitter()
        splitter.addWidget(self.tabs)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1300])

        self.setCentralWidget(splitter)

        # Connect signals
        self.directory_tree.itemChanged.connect(self.handle_directory_item_changed)
        self.directory_tree.customContextMenuRequested.connect(self.on_directories_context_menu)

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
        QApplication.setPalette(dark_palette)  # Now works correctly

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
            QProgressBar {
                background-color: #2d2d2d;
                color: white;
                border: 1px solid #555;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3a3a3a;
            }
        """
        QApplication.instance().setStyleSheet(dark_stylesheet)

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

        self.folder_load_counts[folder_path] = len(file_paths)
        self.folder_loaded_counts[folder_path] = 0

        # Initialize placement data for this folder
        self.folder_placement_data[folder_path] = {
            "current_x": self.current_folder_offset_x,
            "current_y": 0,
            "images_in_row": 0,
            "row_max_height": 0,
            "folder_max_width": 0,
            "folder_total_height": 0
        }

        self.progress_bar.show()
        self.progress_bar.setValue(0)

        worker = ImageLoadWorker(folder_path, file_paths)
        worker.signals.finished.connect(self.on_image_loaded)
        worker.signals.error.connect(self.on_image_load_error)
        worker.signals.progress.connect(self.update_progress)

        self.thread_pool.start(worker)

    def on_image_loaded(self, folder_path, filepath, pix, scale_factor):
        data = self.folder_placement_data[folder_path]
        current_x = data["current_x"]
        current_y = data["current_y"]
        images_in_row = data["images_in_row"]
        row_max_height = data["row_max_height"]
        folder_max_width = data["folder_max_width"]
        folder_total_height = data["folder_total_height"]

        image_width = pix.width() * scale_factor
        image_height = pix.height() * scale_factor

        # Check if we need a new row
        if images_in_row == COLUMNS:
            # Finish previous row
            folder_total_height += row_max_height + SPACING_Y
            # Move down to next row
            current_y = folder_total_height
            current_x = self.current_folder_offset_x
            images_in_row = 0
            row_max_height = 0

        # Place image
        item = DraggablePixmapItem(pix)
        self.scene.addItem(item)
        item.setPos(QPointF(current_x, current_y))
        item.setScale(scale_factor)

        if folder_path not in self.loaded_images:
            self.loaded_images[folder_path] = []
        self.loaded_images[folder_path].append(item)

        # Update row and folder metrics
        current_x += image_width + SPACING_X
        if image_height > row_max_height:
            row_max_height = image_height

        # Update max width
        width_used_this_row = current_x - self.current_folder_offset_x - SPACING_X
        if width_used_this_row > folder_max_width:
            folder_max_width = width_used_this_row

        images_in_row += 1

        # Store updated data
        data["current_x"] = current_x
        data["current_y"] = current_y
        data["images_in_row"] = images_in_row
        data["row_max_height"] = row_max_height
        data["folder_max_width"] = folder_max_width
        data["folder_total_height"] = folder_total_height

        self.folder_loaded_counts[folder_path] += 1

        # Check if all images for folder are done
        if self.folder_loaded_counts[folder_path] == self.folder_load_counts[folder_path]:
            self.on_folder_load_complete(folder_path)

    def on_folder_load_complete(self, folder_path):
        data = self.folder_placement_data[folder_path]
        images_in_row = data["images_in_row"]
        row_max_height = data["row_max_height"]
        folder_total_height = data["folder_total_height"]
        folder_max_width = data["folder_max_width"]

        # Add the last row's height (if any images in last row)
        if images_in_row > 0:
            folder_total_height += row_max_height

        # Draw backdrop
        folder_start_x = self.current_folder_offset_x
        rect_left = folder_start_x - SPACING_X
        rect_top = -SPACING_Y
        rect_width = folder_max_width + 2 * SPACING_X
        rect_height = folder_total_height + 2 * SPACING_Y

        rect_item = QGraphicsRectItem(rect_left, rect_top, rect_width, rect_height)
        rect_item.setBrush(QColor(40, 40, 40, 100))
        rect_item.setPen(QPen(Qt.NoPen))  # Corrected line
        rect_item.setZValue(-1)
        self.scene.addItem(rect_item)

        # Add folder name
        folder_name = os.path.basename(folder_path.rstrip(os.sep))
        text_item = QGraphicsTextItem(folder_name)
        font = QFont("Arial", 14)
        text_item.setFont(font)
        text_item.setDefaultTextColor(Qt.white)
        text_bbox = text_item.boundingRect()
        text_x = folder_start_x + (folder_max_width - text_bbox.width()) / 2
        text_y = rect_top - text_bbox.height() - 5
        text_item.setPos(text_x, text_y)
        text_item.setZValue(0)
        self.scene.addItem(text_item)

        # Update offset for next folder
        self.current_folder_offset_x += folder_max_width + 2 * SPACING_X

    def on_image_load_error(self, filepath, error):
        print(f"Error loading {filepath}: {error}")

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if value == 100:
            QTimer.singleShot(1000, self.progress_bar.hide)

    def unload_images_from_folder(self, folder_path):
        items = self.loaded_images.get(folder_path, [])
        for item in items:
            self.scene.removeItem(item)
        if folder_path in self.loaded_images:
            del self.loaded_images[folder_path]

        # If no images remain, reset
        if not self.any_images_loaded():
            self.reset_canvas()

    def any_images_loaded(self):
        return any(self.loaded_images.values())

    def reset_canvas(self):
        # Reset all folder offset
        self.current_folder_offset_x = 0
        self.view.resetTransform()
        self.view.centerOn(0,0)
        self.view.scale_factor_total = 1.0

    def on_directories_context_menu(self, pos):
        item = self.directory_tree.itemAt(pos)
        if item:
            folder_path = item.data(0, Qt.UserRole)
            menu = QMenu()
            add_fav_action = menu.addAction("Add to Favorites")
            action = menu.exec_(self.directory_tree.mapToGlobal(pos))
            if action == add_fav_action:
                self.add_favorite(folder_path)
                self.favorites_manager.save_favorites_to_json()

    def on_favorites_context_menu(self, pos):
        item = self.favorites_tree.itemAt(pos)
        if item:
            folder_path = item.data(0, Qt.UserRole)
            menu = QMenu()
            remove_action = menu.addAction("Remove from Favorites")
            chosen = menu.exec_(self.favorites_tree.mapToGlobal(pos))
            if chosen == remove_action:
                self.remove_favorite(folder_path, item)

    def remove_favorite(self, folder_path, item):
        if folder_path in self.loaded_images:
            self.unload_images_from_folder(folder_path)
        self.favorites_manager.remove_favorite(folder_path)
        root = self.favorites_tree.invisibleRootItem()
        root.removeChild(item)

    def add_favorite(self, folder_path):
        self.favorites_manager.add_favorite(folder_path)
        self.add_favorite_item(folder_path)

    def add_favorite_item(self, folder_path):
        fav_item = QTreeWidgetItem([os.path.basename(folder_path.rstrip(os.sep))])
        fav_item.setData(0, Qt.UserRole, folder_path)
        fav_item.setFlags(fav_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        fav_item.setCheckState(0, Qt.Unchecked)
        self.favorites_tree.addTopLevelItem(fav_item)

    def is_supported_image(self, filename):
        _, ext = os.path.splitext(filename)
        return ext.lower() in SUPPORTED_IMAGE_FORMATS
