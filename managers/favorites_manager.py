# managers/favorites_manager.py

import json
import os
from utils.constants import FAVORITES_FILE

class FavoritesManager:
    def __init__(self):
        self.favorites = self.load_favorites_from_json()

    def load_favorites_from_json(self):
        if os.path.exists(FAVORITES_FILE):
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"Error loading favorites: {e}")
        return []

    def save_favorites_to_json(self):
        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving favorites: {e}")

    def add_favorite(self, folder_path):
        if folder_path not in self.favorites:
            self.favorites.append(folder_path)
            self.save_favorites_to_json()

    def remove_favorite(self, folder_path):
        if folder_path in self.favorites:
            self.favorites.remove(folder_path)
            self.save_favorites_to_json()
