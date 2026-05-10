"""
Khamsat community requests scraper.

Detection strategy
------------------
1. Concurrent HEAD requests on the next 20 IDs from the high-water mark.
   Valid requests redirect (301) to a canonical slug URL:
       /community/requests/788217-مطلوب-مصمم
   Invalid requests stay at the bare URL and return 404.

2. A single GET to the listing page fetches data for ALL validated IDs
   in one request (individual pages are behind AWS WAF).

3. Adaptive stop: 5 consecutive invalid IDs → stop current scan cycle.

This two-phase approach (HEAD probe → listing parse) minimises bandwidth,
CPU, and HTML parsing while maintaining accurate detection.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS

_LISTING_URL = "https://khamsat.com/community/requests"
_BASE_URL = "https://khamsat.com"

# ── Tuning constants ──────────────────────────────────────────────────
_SCAN_RANGE = 20          # Number of future IDs to probe each cycle
_MAX_WORKERS = 5          # Concurrent HEAD threads
_MAX_CONSECUTIVE_INVALID = 5  # Adaptive stop threshold
_HEAD_TIMEOUT = 8         # Seconds per HEAD probe
_GET_TIMEOUT = 15         # Seconds for the listing page GET


class KhamsatScraper(BaseScraper):
    """
    ID-tracked scraper for Khamsat community requests.

    Phase 1 — HEAD-based redirect validation on candidate IDs.
    Phase 2 — Listing-page GET & parse for validated IDs only.

    The high-water mark (last_id) is persisted in settings.json so scans
    resume across app restarts.
    """

    SITE_NAME = "Khamsat"
    URL = _LISTING_URL

    def __init__(self):
        super().__init__()
        # High-water mark: only IDs above this are considered new
        self._last_id = 0
        self._seen_ids = set()
        # Cache: maps request_id → canonical URL from HEAD redirect
        self._validated_urls = {}
        # Reusable import for URL path validation
        from urllib.parse import urlparse
        self._urlparse = urlparse

    # ------------------------------------------------------------------
    # Public helpers called by the main-window worker
    # ------------------------------------------------------------------

    def set_last_id(self, last_id: int):
        """Set the starting cursor for ID tracking."""
        self._last_id = last_id

    def get_last_id(self) -> int:
        """Return the current high-water mark ID."""
        return self._last_id

    # ------------------------------------------------------------------
    # Core scraping — two-phase pipeline
    # ------------------------------------------------------------------

    def scrape(self, session) -> list:
        """
        1. Probe next 20 IDs with concurrent HEAD requests (redirect check).
        2. Fetch listing page once and parse data for validated IDs.

        Returns list[Project] (newest-first).
        Updates self._last_id to the highest validated ID.
        """

        # ── First-run seed: establish baseline from listing page ─────
        if self._last_id == 0:
            return self._seed_from_listing(session)

        # ── Phase 1: HEAD-based validation ───────────────────────────
        start_id = self._last_id + 1
        end_id = start_id + _SCAN_RANGE

        validated_ids = self._probe_ids(session, start_id, end_id)

        # Filter out duplicates
        new_ids = [
            rid for rid in validated_ids
            if rid not in self._seen_ids
        ]

        if not new_ids:
            # Still advance past any contiguous invalid zone
            return []

        # ── Phase 2: Listing-page parse ──────────────────────────────
        listing_data = self._fetch_listing(session)

        projects = []
        for req_id in sorted(new_ids, reverse=True):  # newest first
            project = listing_data.get(req_id)

            if project is None:
                # ID was validated by HEAD but not yet on the listing page.
                # Build a minimal project from the canonical URL.
                project = self._build_minimal_project(req_id)

            if project:
                self._seen_ids.add(req_id)
                projects.append(project)
                if req_id > self._last_id:
                    self._last_id = req_id

        # Cap seen-IDs to prevent unbounded growth
        if len(self._seen_ids) > 2000:
            sorted_ids = sorted(self._seen_ids)
            self._seen_ids = set(sorted_ids[-1000:])

        return projects

    def fetch_full_description(self, project, session):
        """
        Descriptions are extracted during scrape() from the listing page.
        Individual request pages are behind AWS WAF, so no additional
        HTTP request is needed or attempted.
        """
        return project.description, project.budget

    # ------------------------------------------------------------------
    # First-run seeding
    # ------------------------------------------------------------------

    def _seed_from_listing(self, session) -> list:
        """
        First-run only: fetch the listing page to discover the current
        highest request ID and mark all existing requests as seen.

        Returns an empty list (no notifications on first run) and sets
        self._last_id so subsequent cycles only detect truly new requests.
        """
        listing_data = self._fetch_listing(session)

        if listing_data:
            max_id = max(listing_data.keys())
            self._last_id = max_id
            # Mark all current IDs as seen to prevent duplicate notifications
            self._seen_ids.update(listing_data.keys())
            print(f"[Khamsat] Seeded high-water mark at #{max_id} "
                  f"({len(listing_data)} existing requests skipped)")
        else:
            print("[Khamsat] Seed failed — listing page returned no data")

        return []

    # ------------------------------------------------------------------
    # Phase 1: Concurrent HEAD probing with redirect detection
    # ------------------------------------------------------------------

    def _probe_ids(self, session, start_id: int, end_id: int) -> list:
        """
        Send concurrent HEAD requests to detect which IDs are valid.

        A request is VALID if the server redirects (301) to a canonical
        slug URL containing '/{id}-'.  Invalid requests stay at the bare
        URL (typically 404, no redirect).

        Applies adaptive stop: if _MAX_CONSECUTIVE_INVALID IDs in a row
        are invalid, stop probing further.

        Returns sorted list of validated request IDs.
        """
        ids_to_check = list(range(start_id, end_id))
        results = {}  # {req_id: (is_valid, canonical_url)}

        def _head_check(req_id):
            """Probe a single ID via HEAD with redirect following."""
            url = f"{_BASE_URL}/community/requests/{req_id}"
            try:
                resp = session.head(
                    url, headers=HEADERS, timeout=_HEAD_TIMEOUT,
                    allow_redirects=True
                )
                # STRICT validation: parse the final URL path and ensure
                # it belongs to /community/requests/ specifically.
                # Khamsat shares a global ID counter across all community
                # sections (requests, showcase, discussions), so we MUST
                # reject any redirect that lands outside /community/requests/.
                path = self._urlparse(resp.url).path
                is_valid = (
                    resp.status_code == 200
                    and f"/{req_id}-" in path
                    and path.startswith("/community/requests/")
                )

                return req_id, is_valid, resp.url if is_valid else url

            except Exception:
                # Network error, timeout, SSL — treat as unknown, skip
                return req_id, False, url

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(_head_check, rid): rid for rid in ids_to_check}
            for future in as_completed(futures):
                try:
                    req_id, is_valid, canonical = future.result()
                    results[req_id] = (is_valid, canonical)
                    if is_valid:
                        self._validated_urls[req_id] = canonical
                except Exception:
                    pass

        # Walk IDs in order, applying adaptive stop
        consecutive_invalid = 0
        validated = []
        for rid in ids_to_check:
            valid, _ = results.get(rid, (False, ""))
            if valid:
                validated.append(rid)
                consecutive_invalid = 0
            else:
                consecutive_invalid += 1
                if consecutive_invalid >= _MAX_CONSECUTIVE_INVALID:
                    break

        return validated

    # ------------------------------------------------------------------
    # Phase 2: Listing-page fetch & parse
    # ------------------------------------------------------------------

    def _fetch_listing(self, session) -> dict:
        """
        Fetch the listing page once and build a dict of {request_id: Project}.

        This page is NOT WAF-protected and returns full HTML with all
        recent requests.  We parse only the request rows, extracting
        title, relative time, username, and link.
        """
        try:
            resp = session.get(_LISTING_URL, headers=HEADERS, timeout=_GET_TIMEOUT)
            if resp.status_code != 200:
                print(f"Khamsat listing returned {resp.status_code}")
                return {}
        except Exception as e:
            print(f"Khamsat listing error: {e}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("tr.forum_post")

        data = {}
        for row in rows:
            try:
                project, req_id = self._parse_row(row)
                if project and req_id is not None:
                    data[req_id] = project
            except Exception:
                pass

        return data

    def _build_minimal_project(self, req_id: int):
        """
        Build a minimal Project when the ID was validated by HEAD redirect
        but hasn't appeared on the listing page yet (very fresh request).

        Uses the canonical URL from the HEAD redirect to derive the title.
        """
        canonical = self._validated_urls.get(req_id, "")
        url = canonical or f"{_BASE_URL}/community/requests/{req_id}"

        # Try to extract a human-readable title from the slug
        title = self._title_from_slug(canonical, req_id)

        return Project(
            site=self.SITE_NAME,
            title=title,
            link=url,
            description=f"⏱ طلب جديد",
            budget=""
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_row(self, row):
        """
        Parse a single <tr class="forum_post"> row into a Project.
        Returns (Project, request_id) or (None, None) on failure.
        """
        # --- Link & Title ---
        link_el = row.select_one("h3.details-head a")
        if not link_el:
            return None, None

        href = link_el.get("href", "")
        title = link_el.get_text(strip=True)

        if not href or not title:
            return None, None

        # Extract numeric ID from href like /community/requests/788217-slug
        req_id = self._extract_id_from_href(href)
        if req_id is None:
            return None, None

        # Build full URL
        full_url = f"{_BASE_URL}{href}" if href.startswith("/") else href

        # --- Relative time ---
        # The first "منذ" span that is NOT prefixed with "آخر تفاعل" is the post time
        relative_time = ""
        spans = row.find_all("span")
        for span in spans:
            text = span.get_text(strip=True)
            if text.startswith("منذ") and "آخر تفاعل" not in text:
                relative_time = text
                break

        # --- Description ---
        # Build a clean description from the row context
        desc_parts = []
        if relative_time:
            desc_parts.append(f"⏱ {relative_time}")

        # Try to extract the username/poster info
        user_el = row.select_one("a.user-name, a.author, span.user-name")
        if not user_el:
            # Fallback: look in the card text for the username pattern
            card_text = row.get_text(" ", strip=True)
            # Username usually appears between title and "منذ"
            # e.g. "مطلوب مصمم ... .Sajjad M منذ ساعة"
            parts = card_text.split("منذ")
            if len(parts) > 1:
                # Text before first "منذ" minus the title
                before_time = parts[0].strip()
                if title in before_time:
                    username = before_time.replace(title, "").strip().rstrip(".")
                    if username:
                        desc_parts.append(f"👤 {username}")

        description = "\n".join(desc_parts) if desc_parts else title

        return Project(
            site=self.SITE_NAME,
            title=title,
            link=full_url,
            description=description,
            budget=""  # Khamsat requests don't have budgets
        ), req_id

    # ------------------------------------------------------------------
    # Static utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_id_from_href(href: str):
        """Extract numeric ID from /community/requests/788217-slug."""
        match = re.search(r"/community/requests/(\d+)", href)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_id_from_link(link: str):
        """Extract numeric ID from full URL for sorting."""
        match = re.search(r"/community/requests/(\d+)", link)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _title_from_slug(canonical_url: str, req_id: int) -> str:
        """
        Derive a human-readable title from the canonical slug URL.

        e.g. /788217-%D9%85%D8%B7%D9%84%D9%88%D8%A8-... → 'مطلوب مصمم و مبرمج تطبيقات'

        Falls back to 'Khamsat Request #<id>' if parsing fails.
        """
        if not canonical_url:
            return f"Khamsat Request #{req_id}"
        try:
            from urllib.parse import unquote
            # Extract slug part after the ID
            match = re.search(rf"/{req_id}-(.+)$", canonical_url)
            if match:
                slug = unquote(match.group(1))
                # Convert hyphens to spaces
                title = slug.replace("-", " ").strip()
                if title:
                    return title
        except Exception:
            pass
        return f"Khamsat Request #{req_id}"
