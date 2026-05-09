"""
Settings persistence manager.
Thread-safe reads for worker threads; saves dispatched to main thread.
"""
import json
import os
import threading
from config import get_settings_path


class SettingsManager:
    """Manages application settings with thread-safe access."""

    def __init__(self):
        self.keywords = []
        self.filters_enabled = False
        self.notifications_enabled = True
        self.autostart_enabled = False
        self.device_registered = False
        self.device_id = ""
        self._lock = threading.Lock()

    def load(self):
        """Load settings from disk."""
        try:
            legacy_path = get_settings_path("filters.json")
            path = get_settings_path("settings.json")

            if not os.path.exists(path) and os.path.exists(legacy_path):
                try:
                    os.rename(legacy_path, path)
                except Exception as e:
                    print("Could not rename legacy filters.json:", e)

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.keywords = data.get("keywords", [])
                    self.filters_enabled = data.get("filters_enabled", False)
                    self.notifications_enabled = data.get("notifications_enabled", True)
                    self.autostart_enabled = data.get("autostart_enabled", False)
                    self.device_registered = data.get("device_registered", False)
                    self.device_id = data.get("device_id", "")
        except Exception as e:
            print("Load settings error:", e)

    def save(self):
        """Save settings to disk. Thread-safe via lock."""
        try:
            with self._lock:
                path = get_settings_path("settings.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({
                        "keywords": self.keywords,
                        "filters_enabled": self.filters_enabled,
                        "notifications_enabled": self.notifications_enabled,
                        "autostart_enabled": self.autostart_enabled,
                        "device_registered": self.device_registered,
                        "device_id": self.device_id
                    }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Save settings error:", e)

    def add_keyword(self, kw):
        """Add a keyword filter. Returns True if added."""
        kw = kw.strip().lower()
        if not kw or kw in self.keywords:
            return False
        self.keywords.append(kw)
        self.save()
        return True

    def remove_keyword(self, kw):
        """Remove a keyword filter."""
        if kw in self.keywords:
            self.keywords.remove(kw)
            self.save()

    def matches_filters(self, project):
        """Check if a project matches current filters. Safe to call from any thread."""
        if not self.filters_enabled or not self.keywords:
            return True
        text = (project.title + " " + project.description).lower()
        return any(kw in text for kw in list(self.keywords))
