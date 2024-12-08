# managers/directory_manager.py

import os
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMessageBox
from PyQt5.QtCore import Qt
from utils.helpers import get_windows_drives

class DirectoryManager:
    def __init__(self, tree_widget):
        self.tree_widget = tree_widget
        self.tree_widget.setHeaderLabel("Folders")
        self.tree_widget.setMinimumWidth(200)
        self.tree_widget.itemChanged.connect(self.handle_item_changed)
        self.tree_widget.itemExpanded.connect(self.on_item_expanded)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        # Context menu handling will be connected in the MainWindow

    def initialize_directory_tree(self):
        self.tree_widget.clear()
        if os.name == 'nt':
            drives = get_windows_drives()
            for drive in drives:
                self.populate_tree(drive, self.tree_widget)
        else:
            self.populate_tree("/", self.tree_widget)

    def populate_tree(self, root_path, parent_widget):
        root_name = os.path.basename(root_path.rstrip(os.sep))
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
                QMessageBox.warning(self.tree_widget, "Permission Denied", f"Cannot access {path}")

    def handle_item_changed(self, item, column):
        # This method should be connected to the MainWindow's handler
        pass
