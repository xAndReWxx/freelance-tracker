"""
Windows toast notification manager.
"""
import threading
from win11toast import toast
from config import PLATFORMS_CONFIG


class NotificationManager:
    """Sends Windows toast notifications in background threads."""

    def __init__(self, settings):
        self.settings = settings

    def send(self, project):
        """Send a notification for a new project (non-blocking)."""
        if not self.settings.notifications_enabled:
            return
        threading.Thread(target=self._send, args=(project,), daemon=True).start()

    def _send(self, project):
        """Internal: build and dispatch the toast notification."""
        from core.logger import get_logger, LatencyTracker
        logger = get_logger("Desktop", "desktop.log")
        
        try:
            req_id = getattr(project, 'id', None) or project.link
            with LatencyTracker(req_id, "Desktop_Toast", logger):
                site = project.site
                title = project.title
                desc = project.description
                link = project.link
                budget = project.budget.strip() if project.budget else ""

                icon = PLATFORMS_CONFIG.get(site, {}).get("icon")

                if not budget:
                    budget = "Budget not specified"
                elif not any(x in budget.lower() for x in ["budget", "ميزانية", "سعر", "price"]):
                    budget = f"Budget: {budget}"

                snippet = desc[:140].strip() if desc else "No description"

                toast(
                    f"[{site}] {title}",
                    f"{budget}\n{snippet}",
                    icon=icon,
                    on_click=link,
                    audio="ms-winsoundevent:Notification.Default",
                    app_id="Freelance Tracker"
                )
                logger.info(f"[TOAST] Sent for ProjectID={req_id}")
        except Exception as e:
            logger.error(f"[TOAST] Failed for ProjectID={req_id}: {e}")
