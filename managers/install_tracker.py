"""
Silent first-launch install tracker using Supabase.
"""
import threading
import uuid
import requests
from config import SUPABASE_URL, SUPABASE_ANON_KEY


class InstallTracker:
    """Lightweight, silent background tracker for first-time unique installs."""

    def __init__(self, settings, app):
        self.settings = settings
        self.app = app

    def run_silently(self):
        """Run registration in background thread silently."""
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        try:
            if self.settings.device_registered:
                return

            if not self.settings.device_id:
                self.settings.device_id = str(uuid.uuid4())
                self.app.after(0, self.settings.save)

            if SUPABASE_URL == "YOUR_SUPABASE_URL":
                return

            headers = {
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "device_id": self.settings.device_id,
                "platform": "windows",
                "app_version": "1.0.0"
            }

            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/installs",
                json=payload, headers=headers, timeout=10
            )

            if response.status_code in (200, 201):
                self.settings.device_registered = True
                self.app.after(0, self.settings.save)
        except Exception:
            pass
