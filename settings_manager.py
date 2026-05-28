import json
import os
import logging

class SettingsManager:
    def __init__(self, filename="config.json"):
        self.filename = filename
        self.settings = self._load_settings()

    def _load_settings(self):
        if not os.path.exists(self.filename):
            return self._default_settings()
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")
            return self._default_settings()

    def _default_settings(self):
        return {
            "language": "en",
            "window_width": 980,
            "window_height": 680,
            "window_x": 100,
            "window_y": 100,
            "save_dir": os.path.join(os.path.expanduser("~"), "Downloads"),
            "auto_accept": False,
            "theme": "dark" # Preparation for theme feature
        }

    def save_settings(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()
