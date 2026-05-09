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
        try:
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
                app_id="Freelance Tracker"
            )
        except Exception as e:
            print("Notification Error:", e)
