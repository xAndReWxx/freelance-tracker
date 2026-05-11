"""
Nafezly platform scraper.
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

class NafezlyScraper(BaseScraper):
    SITE_NAME = "Nafezly"
    URL = "https://nafezly.com/projects"

    def _budget_selectors(self):
        return [
            ".project-budget", ".budget", ".price",
            ".project-price", ".salary", ".cost",
            "span.badge", ".project-box__budget"
        ]

    def scrape(self, session):
        soup = self._fetch_page(session)
        projects = []
        for card in soup.select("div.project-card, div.project-box")[:5]:
            try:
                title_el = card.select_one("a.text-truncate")
                if not title_el:
                    continue
                desc_el = card.select_one("h3")
                projects.append(Project(
                    site=self.SITE_NAME,
                    title=title_el.get_text(strip=True),
                    link=title_el.get("href", ""),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    budget=self._extract_budget(card)
                ))
            except Exception as e:
                logger.error(f"Nafezly Parse Error: {e}")
        return projects

    def fetch_full_description(self, project, session):
        desc, budget = project.description, project.budget
        try:
            if not project.link:
                return desc, budget
            response = session.get(project.link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            desc_el = soup.select_one("h2.naskh")
            if desc_el:
                desc = desc_el.get_text(strip=True)
            if not budget:
                budget = self._extract_budget(soup)
        except Exception as e:
            logger.error(f"Fetch details error (Nafezly): {e}")
        return desc, budget
