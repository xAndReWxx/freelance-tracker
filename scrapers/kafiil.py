"""
Kafiil platform scraper.
"""
import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS


from core.logger import get_logger, perf_monitor
logger = get_logger(__name__, "system.log")

class KafiilScraper(BaseScraper):
    SITE_NAME = "Kafiil"
    URL = "https://kafiil.com/projects"

    def _budget_selectors(self):
        return ["p.price", ".price", ".budget"]

    def scrape(self, session):
        soup = self._fetch_page(session)
        projects = []
        for card in soup.select("div.project-head")[:5]:
            try:
                title_elem = self._safe_select(card, "a.name")
                if not title_elem:
                    continue

                link = title_elem.get("href", "")
                if link and link.startswith("/"):
                    link = "https://kafiil.com" + link

                # Remove the span.tag text (e.g. "مفتوح") from the main title
                span = self._safe_select(title_elem, "span.tag")
                if span:
                    span.extract()
                title = self._safe_text(title_elem)

                client_elem = self._safe_select(card, "a.user")
                client = self._safe_text(client_elem)

                budget_elem = self._safe_select(card, "p.price")
                budget = self._safe_text(budget_elem)
                if not budget:
                    budget = self._extract_budget(card)

                spans = card.select("div.down span.text")
                offers = self._safe_text(spans[1]) if len(spans) > 1 else ""

                desc = f"Client: {client} | Offers: {offers}"

                projects.append(Project(
                    site=self.SITE_NAME,
                    title=title,
                    link=link,
                    description=desc,
                    budget=budget
                ))
            except Exception as e:
                logger.error(f"Kafiil Parse Error: {e}")
        return projects

    def fetch_full_description(self, project, session):
        desc, budget = project.description, project.budget
        try:
            if not project.link:
                return desc, budget
            response = session.get(project.link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            blocks = soup.select("div.block")
            for block in blocks:
                head = (
                    block.select_one("div.block-head p.title")
                    or block.select_one("div.block-head")
                )
                if head and "تفاصيل المشروع" in head.get_text(strip=True):
                    content = block.select_one("div.has-padding")
                    if content:
                        desc = re.sub(
                            r'\s+', ' ',
                            content.get_text(" ", strip=True)
                        ).strip()
                    break

            if not budget:
                budget = self._extract_budget(soup)
        except Exception as e:
            logger.error(f"Fetch details error (Kafiil): {e}")
        return desc, budget
