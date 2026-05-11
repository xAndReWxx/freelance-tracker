"""
FreelanceYard platform scraper.
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

class FreelanceYardScraper(BaseScraper):
    SITE_NAME = "FreelanceYard"
    URL = "https://freelanceyard.com/en/jobs"

    def _budget_selectors(self):
        return [
            "span.text-green-700", ".budget", ".price",
            ".salary", "span:contains('EGP')"
        ]

    def scrape(self, session):
        soup = self._fetch_page(session)
        projects = []
        for card in soup.select("div.h-full.p-4.mb-4.bg-white.border.rounded-lg")[:5]:
            try:
                title_el = self._safe_select(card, "h3.text-lg.font-bold a")
                if not title_el:
                    continue

                title = self._safe_text(title_el)
                link = title_el.get("href", "")
                if link and link.startswith("/"):
                    link = "https://freelanceyard.com" + link

                client_el = self._safe_select(card, "i.uil-user")
                client_name = self._safe_text(client_el.parent) if client_el and client_el.parent else ""

                category_el = self._safe_select(card, "div.text-stone-500")
                category = self._safe_text(category_el)

                budget_el = self._safe_select(card, "span.text-green-700")
                budget = self._safe_text(budget_el)
                if not budget:
                    budget = self._extract_budget(card)

                description = (
                    f"Client: {client_name} | Category: {category}"
                    if client_name or category
                    else "No short description."
                )

                projects.append(Project(
                    site=self.SITE_NAME,
                    title=title,
                    link=link,
                    description=description,
                    budget=budget
                ))
            except Exception as e:
                logger.error(f"FreelanceYard Parse Error: {e}")
        return projects

    def fetch_full_description(self, project, session):
        desc, budget = project.description, project.budget
        try:
            if not project.link:
                return desc, budget
            response = session.get(project.link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            # Specific selector requested for FreelanceYard project description
            desc_el = soup.select_one("div#job-details div.mb-4.break-words.text-muted")
            if desc_el:
                desc = self.clean_description(desc_el.get_text(" ", strip=True))
            else:
                # Safe fallback if layout changes slightly
                desc_fallback = soup.select_one("div.job-description, div.content, article")
                if desc_fallback:
                    desc = self.clean_description(desc_fallback.get_text(" ", strip=True))
            if not budget:
                budget = self._extract_budget(soup)
        except Exception as e:
            logger.error(f"Fetch details error (FreelanceYard): {e}")
        return desc, budget
