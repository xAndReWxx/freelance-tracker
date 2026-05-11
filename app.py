"""
Freelance Tracker — Entry Point
Launches the main application window from the modular UI package.
"""
from core.logger import get_logger
logger = get_logger("System")
logger.info("Application starting...")

from ui.main_window import FreelanceTrackerApp

if __name__ == "__main__":
    app = FreelanceTrackerApp()
    app.mainloop()
