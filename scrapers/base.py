"""
Abstract base class for all platform scrapers.
"""
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from config import HEADERS
from models import Project


class BaseScraper(ABC):
    """Base class providing shared scraping utilities."""

    SITE_NAME = ""
    URL = ""

    def _safe_text(self, element, default=""):
        """Safely extract and clean text from a BeautifulSoup element."""
        return element.get_text(" ", strip=True) if element else default

    def _safe_select(self, parent, selector):
        """Safely query a CSS selector and return the element."""
        return parent.select_one(selector) if parent else None

    def _budget_selectors(self):
        """Override to provide platform-specific budget CSS selectors."""
        return []

    def _extract_budget(self, element):
        """Clean reusable parsing function to extract pricing/budget info."""
        if not element:
            return ""

        # 1. Try platform-specific CSS selectors
        for sel in self._budget_selectors():
            try:
                els = element.select(sel)
                for el in els:
                    text = el.get_text(" ", strip=True)
                    if text and len(text) < 50:
                        return text
            except Exception:
                pass

        # 2. Fallback: money icons which usually precede budget text
        try:
            for icon_class in [".fa-money", ".fa-money-bill", ".fa-dollar-sign", ".fa-tags"]:
                icons = element.select(icon_class)
                for icon in icons:
                    parent = icon.parent
                    if parent:
                        text = parent.get_text(" ", strip=True)
                        if text and len(text) < 40 and (
                            any(c.isdigit() for c in text)
                            or "مفتوح" in text
                            or "fixed" in text.lower()
                        ):
                            return text
        except Exception:
            pass

        # 3. Fallback: text containing currency/budget keywords
        try:
            keywords = [
                "ميزانية", "سعر", "budget", "price", "salary",
                "$", "sar", "ر.س", "دولار", "fixed price"
            ]
            for tag in element.find_all(['span', 'div', 'li', 'td', 'p', 'b', 'strong']):
                text = tag.get_text(" ", strip=True)
                if 2 < len(text) < 45:
                    lower_text = text.lower()
                    if any(kw in lower_text for kw in keywords):
                        if (
                            any(c.isdigit() for c in text)
                            or "fixed" in lower_text
                            or "مفتوح" in lower_text
                            or "غير محدد" in lower_text
                        ):
                            return text
        except Exception:
            pass

        return ""

    def _fetch_page(self, session):
        """Fetch and parse the listing page."""
        response = session.get(self.URL, headers=HEADERS, timeout=10)
        return BeautifulSoup(response.text, "html.parser")

    @abstractmethod
    def scrape(self, session):
        """Scrape the platform listing page. Returns list[Project]."""
        pass

    @abstractmethod
    def fetch_full_description(self, project, session):
        """Fetch full description from project detail page. Returns (desc, budget)."""
        pass
