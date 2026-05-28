import json
import os
import logging
from datetime import datetime

class HistoryManager:
    def __init__(self, filename="transfer_history.json"):
        self.filename = filename
        self.history = self._load_history()

    def _load_history(self):
        if not os.path.exists(self.filename):
            return []
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load history: {e}")
            return []

    def add_entry(self, direction, filename, size_mb, peer, status):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "direction": direction, # "Send" or "Receive"
            "filename": filename,
            "size_mb": size_mb,
            "peer": peer,
            "status": status
        }
        self.history.insert(0, entry) # Add to top
        self._save_history()

    def _save_history(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save history: {e}")

    def get_history(self):
        return self.history

    def clear_history(self):
        self.history = []
        self._save_history()
