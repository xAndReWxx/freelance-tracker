"""
Windows startup shortcut manager.
Uses Start Menu shortcut instead of registry to avoid AV false positives.
"""
import os
import sys


class StartupManager:
    """Manages Windows startup shortcut safely."""

    def __init__(self):
        self.app_name = "FreelanceTracker.lnk"

    def _get_startup_path(self):
        try:
            import winshell
            return os.path.join(winshell.startup(), self.app_name)
        except ImportError:
            startup_dir = os.path.join(
                os.environ.get("APPDATA", ""),
                "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
            )
            return os.path.join(startup_dir, self.app_name)

    def enable(self):
        """Create a startup shortcut."""
        try:
            import winshell
            from win32com.client import Dispatch

            startup_path = self._get_startup_path()

            if getattr(sys, 'frozen', False):
                target = sys.executable
                icon_path = target
                work_dir = os.path.dirname(sys.executable)
                arguments = ""
            else:
                target = sys.executable
                arguments = f'"{os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))}"'
                work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                icon_path = ""

            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(startup_path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = work_dir
            if arguments:
                shortcut.Arguments = arguments
            if icon_path:
                shortcut.IconLocation = icon_path
            shortcut.save()
            return True
        except Exception as e:
            print(f"Startup enable error: {e}")
            return False

    def disable(self):
        """Remove the startup shortcut."""
        try:
            startup_path = self._get_startup_path()
            if os.path.exists(startup_path):
                os.remove(startup_path)
            return True
        except Exception as e:
            print(f"Startup disable error: {e}")
            return False

    def sync(self, enabled):
        """Ensure shortcut state matches the setting."""
        if enabled:
            self.enable()
        else:
            self.disable()
