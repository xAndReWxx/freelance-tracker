"""
System tray icon manager using pystray.
"""
import os
import threading
import webbrowser
import pystray
from PIL import Image
from config import COLORS, APP_ICON


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

class TrayManager:
    """Manages the system tray icon and its menu."""

    def __init__(self, app):
        self.app = app
        self.tray_icon = None
        self.is_hidden = False

    def _create_image(self):
        """Create the tray icon image."""
        try:
            if os.path.exists(APP_ICON):
                return Image.open(APP_ICON)
        except Exception as e:
            logger.error(f"Tray icon error: {e}")
        return Image.new("RGB", (64, 64), COLORS["accent"])

    def hide(self):
        """Hide the main window and show the tray icon."""
        if self.is_hidden:
            return
        self.is_hidden = True
        self.app.withdraw()

        tooltip = "Monitoring Running" if self.app.is_monitoring else "Monitoring Stopped"

        def _toggle_notif(icon, item):
            self.app.settings.notifications_enabled = not self.app.settings.notifications_enabled
            self.app.after(0, self.app._sync_notification_ui)

        menu = pystray.Menu(
            pystray.MenuItem("Show Window", self.show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Enable Notifications",
                _toggle_notif,
                checked=lambda item: self.app.settings.notifications_enabled
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start Monitoring",
                lambda i, it: self.app.after(0, self.app._start_from_tray)
            ),
            pystray.MenuItem(
                "Stop Monitoring",
                lambda i, it: self.app.after(0, self.app._stop_from_tray)
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Open Mostaql",
                lambda i, it: webbrowser.open("https://mostaql.com/projects")
            ),
            pystray.MenuItem(
                "Open Nafezly",
                lambda i, it: webbrowser.open("https://nafezly.com/projects")
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.quit)
        )

        self.tray_icon = pystray.Icon(
            "FreelanceTracker", self._create_image(), tooltip, menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show(self, icon=None, item=None):
        """Restore the main window from the tray."""
        self.is_hidden = False
        self._stop_icon()
        self.app.after(0, self.app.deiconify)
        self.app.after(50, self.app.lift)
        self.app.after(100, self.app.focus_force)

    def quit(self, icon=None, item=None):
        """Quit the app from the tray menu."""
        self.is_hidden = False
        self._stop_icon()
        self.app.after(0, self.app._on_close)

    def stop(self):
        """Stop the tray icon (used during app shutdown)."""
        self._stop_icon()

    def _stop_icon(self):
        """Internal: safely stop and clear the tray icon."""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
