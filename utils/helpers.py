# utils/helpers.py

import sys
import string

def get_windows_drives():
    drives = []
    if sys.platform.startswith('win'):
        try:
            from ctypes import windll
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
        except Exception as e:
            print(f"Error fetching drives: {e}")
    return drives
