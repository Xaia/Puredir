# main_window.py

import sys
import os
import json
import string
from math import ceil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QFileDialog,
    QGraphicsPixmapItem, QTreeWidget, QTreeWidgetItem, QMessageBox,
    QStyleFactory, QSplitter, QMenu, QTabWidget, QProgressBar, QVBoxLayout, QWidget,
    QGraphicsRectItem, QGraphicsTextItem, QDialog, QHBoxLayout, QLabel, QSpinBox, QPushButton
)
from PyQt5.QtCore import (
    Qt, QPointF, QPoint, QRectF, QEvent, QRect, QRunnable, QThreadPool,
    pyqtSignal, QObject, QTimer, QThread
)
from PyQt5.QtGui import (
    QWheelEvent, QMouseEvent, QPixmap, QPainter, QPalette, QColor, QPen, QFont
)

from ui.graphics_view import GraphicsView  # Ensure this import points to your fixed graphics_view.py
from ui.draggable_pixmap_item import DraggablePixmapItem
from ui.folder_backdrop_item import FolderBackdropItem  # Import the custom item
from utils.image_cache import LRUCache  # Import the LRUCache
from utils.constants import (
    UNIFORM_HEIGHT, COLUMNS, SPACING_X, SPACING_Y,
    INFINITE_CANVAS_SIZE, SUPPORTED_IMAGE_FORMATS, FAVORITES_FILE, CONFIG_FILE
)



class ImageLoadSignals(QObject):
    finished = pyqtSignal(str, str, QPixmap, float)  # folder_path, filepath, pix, scale_factor
    error = pyqtSignal(str, Exception)
    progress = pyqtSignal(int)


class ImageLoadWorker(QRunnable):
    def __init__(self, folder_path, filepaths, uniform_height, image_cache):
        super().__init__()
        self.folder_path = folder_path
        self.filepaths = filepaths
        self.uniform_height = uniform_height
        self.signals = ImageLoadSignals()
        self.image_cache = image_cache

    def run(self):
        for i, filepath in enumerate(self.filepaths):
            try:
                # Check if pixmap is in cache
                pix = self.image_cache.get(filepath)
                if pix is None:
                    # Load from disk
                    pix = QPixmap(filepath)
                    if pix.isNull():
                        raise ValueError(f"Could not load image: {filepath}")
                    # Store in cache
                    self.image_cache.put(filepath, pix)

                scale_factor = self.uniform_height / pix.height()

                # Emit finished for each image
                self.signals.finished.emit(self.folder_path, filepath, pix, scale_factor)

                # Emit progress
                progress = int((i + 1) / len(self.filepaths) * 100)
                self.signals.progress.emit(progress)
            except Exception as e:
                self.signals.error.emit(filepath, e)


class SettingsDialog(QDialog):
    """
    Dialog for adjusting layout settings such as columns and spacing.
    """
    def __init__(self, current_columns, current_spacing_x, current_spacing_y, current_uniform_height, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        # Number of Columns
        columns_layout = QHBoxLayout()
        columns_label = QLabel("Number of Columns:")
        self.columns_spinbox = QSpinBox()
        self.columns_spinbox.setMinimum(1)
        self.columns_spinbox.setMaximum(20)
        self.columns_spinbox.setValue(current_columns)
        columns_layout.addWidget(columns_label)
        columns_layout.addWidget(self.columns_spinbox)
        layout.addLayout(columns_layout)
        
        # Spacing X
        spacing_x_layout = QHBoxLayout()
        spacing_x_label = QLabel("Spacing X:")
        self.spacing_x_spinbox = QSpinBox()
        self.spacing_x_spinbox.setMinimum(0)
        self.spacing_x_spinbox.setMaximum(100)
        self.spacing_x_spinbox.setValue(current_spacing_x)
        spacing_x_layout.addWidget(spacing_x_label)
        spacing_x_layout.addWidget(self.spacing_x_spinbox)
        layout.addLayout(spacing_x_layout)
        
        # Spacing Y
        spacing_y_layout = QHBoxLayout()
        spacing_y_label = QLabel("Spacing Y:")
        self.spacing_y_spinbox = QSpinBox()
        self.spacing_y_spinbox.setMinimum(0)
        self.spacing_y_spinbox.setMaximum(100)
        self.spacing_y_spinbox.setValue(current_spacing_y)
        spacing_y_layout.addWidget(spacing_y_label)
        spacing_y_layout.addWidget(self.spacing_y_spinbox)
        layout.addLayout(spacing_y_layout)
        
        # Uniform Height
        uniform_height_layout = QHBoxLayout()
        uniform_height_label = QLabel("Uniform Height:")
        self.uniform_height_spinbox = QSpinBox()
        self.uniform_height_spinbox.setMinimum(50)
        self.uniform_height_spinbox.setMaximum(1000)
        self.uniform_height_spinbox.setValue(current_uniform_height)
        uniform_height_layout.addWidget(uniform_height_label)
        uniform_height_layout.addWidget(self.uniform_height_spinbox)
        layout.addLayout(uniform_height_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addStretch()
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
    
    def get_settings(self):
        """
        Retrieves the settings from the dialog.
        
        Returns:
            tuple: (columns, spacing_x, spacing_y, uniform_height)
        """
        return (
            self.columns_spinbox.value(),
            self.spacing_x_spinbox.value(),
            self.spacing_y_spinbox.value(),
            self.uniform_height_spinbox.value()
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("PureRef Prototype")
        self.resize(1600, 900)
        self.apply_dark_theme()

        # Initialize layout parameters as instance variables with default values
        self.UNIFORM_HEIGHT = UNIFORM_HEIGHT
        self.COLUMNS = COLUMNS
        self.SPACING_X = SPACING_X
        self.SPACING_Y = SPACING_Y

        # Load settings from configuration file
        self.load_settings()

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max(QThreadPool.globalInstance().maxThreadCount(), 4))

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()

        self.image_cache = LRUCache(capacity=200)  # Adjust capacity as needed

        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-INFINITE_CANVAS_SIZE//2, -INFINITE_CANVAS_SIZE//2, INFINITE_CANVAS_SIZE, INFINITE_CANVAS_SIZE)

        # Initialize GraphicsView and connect custom signals
        self.view = GraphicsView(self.scene, self)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)  # Prevent the view from overriding the main window's context menu

        # Connect signals from GraphicsView
        self.view.clear_canvas_signal.connect(self.clear_canvas)
        self.view.open_settings_signal.connect(self.open_settings_dialog)
        self.view.reset_view_signal.connect(self.reset_view)  # Connect the new reset_view_signal

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0,0,0,0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.view)
        right_layout.addWidget(self.progress_bar)

        self.favorites = self.load_favorites_from_json()
        # Updated data structure: folder_path -> {'images': [...], 'backdrop': ...}
        self.loaded_images = {}
        self.current_folder_offset_x = 0  # where the next folder should start horizontally

        self.loaded_folders_order = []  # To maintain the order of loaded folders

        self.folder_load_counts = {}
        self.folder_loaded_counts = {}
        # Per-folder placement data
        # {folder_path: {"current_x", "current_y", "images_in_row", "row_max_height", "folder_max_width", "folder_total_height", "image_relative_positions"}}
        self.folder_placement_data = {}

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
        self.favorites_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.favorites_tree.customContextMenuRequested.connect(self.on_favorites_context_menu)
        self.favorites_tree.itemChanged.connect(self.handle_favorites_item_changed)
        for folder_path in self.favorites:
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

        # Set context menu policy for the main window to accept context menu events
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEventHandler)

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
        """
        Loads images from the specified folder, utilizing the image cache.

        Args:
            folder_path (str): The path of the folder to load images from.
        """
        if folder_path in self.loaded_images:
            # Already loaded
            return False

        file_paths = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if self.is_supported_image(file):
                    file_paths.append(os.path.join(root, file))

        if not file_paths:
            QMessageBox.information(self, "No Images", f"No supported images found in {folder_path}")
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
            "folder_total_height": 0,
            "image_relative_positions": []  # To store relative positions of images
        }

        # Append folder to the ordered list
        self.loaded_folders_order.append(folder_path)

        self.progress_bar.show()
        self.progress_bar.setValue(0)

        worker = ImageLoadWorker(folder_path, file_paths, self.UNIFORM_HEIGHT, self.image_cache)
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
        if images_in_row == self.COLUMNS:
            # Finish previous row
            folder_total_height += row_max_height + self.SPACING_Y
            # Move down to next row
            current_y = folder_total_height
            current_x = self.current_folder_offset_x
            images_in_row = 0
            row_max_height = 0

        # Place image
        item = DraggablePixmapItem(pix)
        item.setAcceptedMouseButtons(Qt.LeftButton)
        self.scene.addItem(item)
        item.setPos(QPointF(current_x, current_y))
        item.setScale(scale_factor)

        if folder_path not in self.loaded_images:
            self.loaded_images[folder_path] = {
                "images": [],
                "backdrop": None
            }
        self.loaded_images[folder_path]["images"].append(item)

        # Calculate and store relative position
        relative_x = current_x - (self.current_folder_offset_x - self.SPACING_X)
        relative_y = current_y + self.SPACING_Y  # Assuming backdrop is above by SPACING_Y
        data["image_relative_positions"].append((relative_x, relative_y))

        # Update row and folder metrics
        current_x += image_width + self.SPACING_X
        if image_height > row_max_height:
            row_max_height = image_height

        # Update max width
        width_used_this_row = current_x - self.current_folder_offset_x - self.SPACING_X
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
        """
        Called when all images for a folder have been loaded.
        Creates and adds the backdrop with the folder name.

        Args:
            folder_path (str): The path of the loaded folder.
        """
        data = self.folder_placement_data[folder_path]
        images_in_row = data["images_in_row"]
        row_max_height = data["row_max_height"]
        folder_total_height = data["folder_total_height"]
        folder_max_width = data["folder_max_width"]

        # Add the last row's height (if any images in last row)
        if images_in_row > 0:
            folder_total_height += row_max_height

        # Define the backdrop rectangle
        rect_left = self.current_folder_offset_x - self.SPACING_X
        rect_top = -self.SPACING_Y
        rect_width = folder_max_width + 2 * self.SPACING_X
        rect_height = folder_total_height + 2 * self.SPACING_Y

        backdrop_rect = QRectF(rect_left, rect_top, rect_width, rect_height)

        # Create and add the custom FolderBackdropItem
        folder_name = os.path.basename(folder_path)
        backdrop_item = FolderBackdropItem(folder_name, backdrop_rect)
        self.scene.addItem(backdrop_item)

        # Store the backdrop item
        self.loaded_images[folder_path]["backdrop"] = backdrop_item

        # Update offset for next folder
        self.current_folder_offset_x += folder_max_width + 2 * self.SPACING_X

    def on_image_load_error(self, filepath, error):
        QMessageBox.warning(self, "Image Load Error", f"Failed to load {filepath}.\nError: {error}")

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if value == 100:
            QTimer.singleShot(1000, self.progress_bar.hide)

    def unload_images_from_folder(self, folder_path):
        """
        Unloads images and associated backdrop items from the scene for a given folder.
        Repositions remaining folders to fill the freed space.

        Args:
            folder_path (str): The path of the folder to unload.
        """
        if folder_path not in self.loaded_images:
            return  # Nothing to unload

        # Remove image items
        for item in self.loaded_images[folder_path]["images"]:
            self.scene.removeItem(item)

        # Remove backdrop
        backdrop_item = self.loaded_images[folder_path].get("backdrop")
        if backdrop_item:
            self.scene.removeItem(backdrop_item)

        # Remove from loaded_images
        del self.loaded_images[folder_path]

        # Remove from the ordered list
        if folder_path in self.loaded_folders_order:
            self.loaded_folders_order.remove(folder_path)

        # Remove placement data
        if folder_path in self.folder_placement_data:
            del self.folder_placement_data[folder_path]

        # Rearrange remaining folders to fill the space
        self.rearrange_folders()

        # If no images remain, reset
        if not self.any_images_loaded():
            self.reset_canvas()

    def rearrange_folders(self):
        """
        Rearranges the positions of all loaded folders and their images based on the current order.
        """
        self.current_folder_offset_x = 0  # Reset offset

        for folder_path in self.loaded_folders_order:
            data = self.folder_placement_data[folder_path]
            folder_max_width = data["folder_max_width"]
            folder_total_height = data["folder_total_height"]

            # Define the new backdrop rectangle
            rect_left = self.current_folder_offset_x - self.SPACING_X
            rect_top = -self.SPACING_Y
            rect_width = folder_max_width + 2 * self.SPACING_X
            rect_height = folder_total_height + 2 * self.SPACING_Y

            backdrop_rect = QRectF(rect_left, rect_top, rect_width, rect_height)

            # Update backdrop item
            backdrop_item = self.loaded_images[folder_path]["backdrop"]
            backdrop_item.backdrop_rect = backdrop_rect
            backdrop_item.text_rect = QRectF(
                backdrop_rect.left(),
                backdrop_rect.top() - backdrop_item.text_bbox.height() - backdrop_item.text_margin,
                backdrop_rect.width(),
                backdrop_item.text_bbox.height()
            )
            backdrop_item.total_rect = QRectF(
                backdrop_rect.left(),
                backdrop_item.text_rect.top(),
                backdrop_rect.width(),
                backdrop_rect.height() + backdrop_item.text_bbox.height() + backdrop_item.text_margin
            )
            backdrop_item.prepareGeometryChange()
            backdrop_item.setPos(backdrop_rect.left(), backdrop_rect.top())

            # Reposition images based on relative positions
            for idx, image_item in enumerate(self.loaded_images[folder_path]["images"]):
                if idx >= len(data["image_relative_positions"]):
                    # Prevent index error if positions are mismatched
                    continue
                relative_x, relative_y = data["image_relative_positions"][idx]
                new_x = backdrop_rect.left() + relative_x
                new_y = backdrop_rect.top() + relative_y
                image_item.setPos(QPointF(new_x, new_y))

            # Update offset for the next folder
            self.current_folder_offset_x += folder_max_width + 2 * self.SPACING_X

    def any_images_loaded(self):
        return bool(self.loaded_images)

    def reset_canvas(self):
        """
        Resets the canvas by clearing all items and resetting transformations.
        """
        # Reset all folder offset
        self.current_folder_offset_x = 0
        self.view.resetTransform()
        self.view.centerOn(0,0)
        self.view.scale_factor_total = 1.0
        self.scene.clear()
        self.loaded_images.clear()
        self.folder_placement_data.clear()
        self.loaded_folders_order.clear()
        self.progress_bar.hide()

    def reset_view(self):
        """
        Resets the view to its initial state without clearing the canvas.
        """
        self.view.resetTransform()
        self.view.centerOn(0, 0)
        self.view.scale_factor_total = 1.0

    def contextMenuEventHandler(self, position):
        """
        Handles the custom context menu event for the main window.
        Prevents showing the main context menu if right-click is on the GraphicsView.

        Args:
            position (QPoint): The position where the menu was requested.
        """
        # Determine the widget at the clicked position
        clicked_widget = self.childAt(self.mapToGlobal(position))
        if isinstance(clicked_widget, GraphicsView):
            # Do not show the main window's context menu if right-click is on the GraphicsView
            return


    def clear_canvas(self):
        """
        Clears the canvas by unchecking all folders in both the Directories and Favorites trees.
        """
        self.uncheck_all_items(self.directory_tree)
        self.uncheck_all_items(self.favorites_tree)

    def uncheck_all_items(self, tree):
        """
        Recursively unchecks all checked items in the given QTreeWidget.

        Args:
            tree (QTreeWidget): The tree to traverse and uncheck items.
        """
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            self.uncheck_item_recursive(item)

    def uncheck_item_recursive(self, item):
        """
        Recursively unchecks the given item and all its children.

        Args:
            item (QTreeWidgetItem): The item to uncheck.
        """
        if item.checkState(0) == Qt.Checked:
            item.setCheckState(0, Qt.Unchecked)
        for i in range(item.childCount()):
            child = item.child(i)
            self.uncheck_item_recursive(child)

    def open_settings_dialog(self):
        """
        Opens the settings dialog to allow users to configure layout parameters.
        """
        dialog = SettingsDialog(
            current_columns=self.COLUMNS,
            current_spacing_x=self.SPACING_X,
            current_spacing_y=self.SPACING_Y,
            current_uniform_height=self.UNIFORM_HEIGHT,
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            new_columns, new_spacing_x, new_spacing_y, new_uniform_height = dialog.get_settings()
            self.update_settings(new_columns, new_spacing_x, new_spacing_y, new_uniform_height)

    def update_settings(self, new_columns, new_spacing_x, new_spacing_y, new_uniform_height):
        """
        Updates layout settings and rearranges the canvas.
        
        Args:
            new_columns (int): New number of columns.
            new_spacing_x (int): New horizontal spacing.
            new_spacing_y (int): New vertical spacing.
            new_uniform_height (int): New uniform height for images.
        """
        self.COLUMNS = new_columns
        self.SPACING_X = new_spacing_x
        self.SPACING_Y = new_spacing_y
        self.UNIFORM_HEIGHT = new_uniform_height

        # Update existing placement data
        for folder_path in self.loaded_folders_order:
            data = self.folder_placement_data.get(folder_path, {})
            data["current_x"] = self.current_folder_offset_x
            data["current_y"] = 0
            data["images_in_row"] = 0
            data["row_max_height"] = 0
            data["folder_max_width"] = 0
            data["folder_total_height"] = 0
            data["image_relative_positions"] = []

        # Reset folder offset and rearrange
        self.current_folder_offset_x = 0
        self.rearrange_folders()

        # Save the new settings
        self.save_settings()

    def on_directories_context_menu(self, pos):
        """
        Displays a context menu for the directories tree.

        Args:
            pos (QPoint): The position where the menu was requested.
        """
        item = self.directory_tree.itemAt(pos)
        if item:
            folder_path = item.data(0, Qt.UserRole)
            menu = QMenu()
            add_fav_action = menu.addAction("Add to Favorites")
            action = menu.exec_(self.directory_tree.mapToGlobal(pos))
            if action == add_fav_action:
                self.add_favorite(folder_path)
                self.save_favorites_to_json()

    def on_favorites_context_menu(self, pos):
        """
        Displays a context menu for the favorites tree.

        Args:
            pos (QPoint): The position where the menu was requested.
        """
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
        if folder_path in self.favorites:
            self.favorites.remove(folder_path)
        root = self.favorites_tree.invisibleRootItem()
        root.removeChild(item)
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

    def is_supported_image(self, filename):
        _, ext = os.path.splitext(filename)
        return ext.lower() in SUPPORTED_IMAGE_FORMATS

    def load_favorites_from_json(self):
        if os.path.exists(FAVORITES_FILE):
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except json.JSONDecodeError:
                QMessageBox.warning(self, "JSON Error", f"Failed to parse {FAVORITES_FILE}.")
        return []

    def save_favorites_to_json(self):
        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save favorites.\nError: {e}")

    def load_settings(self):
        """
        Loads layout settings from the configuration file.
        """
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.COLUMNS = data.get("COLUMNS", self.COLUMNS)
                        self.SPACING_X = data.get("SPACING_X", self.SPACING_X)
                        self.SPACING_Y = data.get("SPACING_Y", self.SPACING_Y)
                        self.UNIFORM_HEIGHT = data.get("UNIFORM_HEIGHT", self.UNIFORM_HEIGHT)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Configuration Error", f"Failed to parse {CONFIG_FILE}. Using default settings.")
        else:
            # Configuration file does not exist; use default settings
            pass

    def save_settings(self):
        """
        Saves the current layout settings to the configuration file.
        """
        data = {
            "COLUMNS": self.COLUMNS,
            "SPACING_X": self.SPACING_X,
            "SPACING_Y": self.SPACING_Y,
            "UNIFORM_HEIGHT": self.UNIFORM_HEIGHT
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save settings.\nError: {e}")

    def reset_view(self):
        """
        Resets the view to its initial state without clearing the canvas.
        """
        self.view.resetTransform()
        self.view.centerOn(0, 0)
        self.view.scale_factor_total = 1.0

def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
