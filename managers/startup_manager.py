"""
Windows startup shortcut manager.
Uses Start Menu shortcut instead of registry to avoid AV false positives.
"""
import os
import sys


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

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
            import pythoncom
            pythoncom.CoInitialize()
            from win32com.client import Dispatch

            startup_path = self._get_startup_path()

            if getattr(sys, 'frozen', False):
                target = sys.executable
                icon_path = target
                work_dir = os.path.dirname(sys.executable)
                arguments = ""
            else:
                target = os.path.abspath(sys.argv[0])
                arguments = ""
                work_dir = os.path.dirname(target)
                icon_path = ""

            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(startup_path)
            shortcut.TargetPath = target
            shortcut.WorkingDirectory = work_dir
            if arguments:
                shortcut.Arguments = arguments
            if icon_path:
                shortcut.IconLocation = icon_path
            shortcut.Save()

            if os.path.exists(startup_path):
                logger.info(f"Startup shortcut created: {startup_path}")
                return True
            else:
                logger.info(f"Startup shortcut NOT found after save: {startup_path}")
                return False
        except Exception as e:
            logger.error(f"Startup enable error: {e}")
            return False

    def disable(self):
        """Remove the startup shortcut."""
        try:
            startup_path = self._get_startup_path()
            if os.path.exists(startup_path):
                os.remove(startup_path)
            return True
        except Exception as e:
            logger.error(f"Startup disable error: {e}")
            return False

    def sync(self, enabled):
        """Ensure shortcut state matches the setting."""
        if enabled:
            self.enable()
        else:
            self.disable()
