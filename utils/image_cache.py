# utils/image_cache.py

from collections import OrderedDict
from PyQt5.QtGui import QPixmap
import threading


class LRUCache:
    """
    A simple thread-safe LRU (Least Recently Used) cache.
    """

    def __init__(self, capacity=100):
        """
        Initializes the LRU Cache.

        Args:
            capacity (int, optional): Maximum number of items to store. Defaults to 100.
        """
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        """
        Retrieves an item from the cache.

        Args:
            key (str): The key to retrieve.

        Returns:
            QPixmap or None: The cached QPixmap or None if not found.
        """
        with self.lock:
            if key not in self.cache:
                return None
            # Move the key to the end to indicate recent use
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key, value):
        """
        Adds an item to the cache.

        Args:
            key (str): The key for the item.
            value (QPixmap): The QPixmap to store.
        """
        with self.lock:
            if key in self.cache:
                # Update existing item and move to end
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                self.cache[key] = value
                if len(self.cache) > self.capacity:
                    # Remove least recently used item
                    self.cache.popitem(last=False)

    def clear(self):
        """
        Clears the cache.
        """
        with self.lock:
            self.cache.clear()
