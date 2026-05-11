"""
Mostaql platform scraper.
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

class MostaqlScraper(BaseScraper):
    SITE_NAME = "Mostaql"
    URL = "https://mostaql.com/projects"

    def _budget_selectors(self):
        return [
            ".project-meta--budget", ".budget", ".price",
            "td.budget", ".project__budget", ".projects-card__price",
            "li.budget", ".carda__budget", ".project__details .budget"
        ]

    def scrape(self, session):
        soup = self._fetch_page(session)
        projects = []
        for row in soup.select("tr.project-row")[:5]:
            try:
                title_el = row.select_one("h2 a")
                if not title_el:
                    continue
                desc_el = row.select_one("p.project__brief a")
                projects.append(Project(
                    site=self.SITE_NAME,
                    title=title_el.get_text(strip=True),
                    link=title_el.get("href", ""),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    budget=self._extract_budget(row)
                ))
            except Exception as e:
                logger.error(f"Mostaql Parse Error: {e}")
        return projects

    def fetch_full_description(self, project, session):
        desc, budget = project.description, project.budget
        try:
            if not project.link:
                return desc, budget
            response = session.get(project.link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            desc_el = soup.select_one("div.text-wrapper-div.carda__content")
            if desc_el:
                desc = desc_el.get_text(strip=True)
            if not budget:
                budget = self._extract_budget(soup)
        except Exception as e:
            logger.error(f"Fetch details error (Mostaql): {e}")
        return desc, budget
