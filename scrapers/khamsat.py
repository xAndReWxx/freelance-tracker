"""
Khamsat community requests scraper.

Detection strategy
------------------
1. Sequential HEAD requests on the next IDs from the high-water mark.
   Valid requests redirect (301) to a canonical slug URL:
       /community/requests/788217-مطلوب-مصمم
   Invalid requests stay at the bare URL and return 404.

2. A single GET to the listing page fetches data for ALL validated IDs
   in one request (individual pages are behind AWS WAF).

3. Adaptive stop: 25 consecutive invalid IDs → stop current scan cycle.
   Counter resets to 0 whenever a valid ID is found, bridging gaps safely.

4. Human-like pacing: randomized delays between each HEAD request.
   Automatically throttles to slower delays when many misses are detected,
   making the crawler appear natural and avoid anti-bot detection.
"""
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import Project
from config import HEADERS

_LISTING_URL = "https://khamsat.com/community/requests"
_BASE_URL = "https://khamsat.com"

# ── Tuning constants ──────────────────────────────────────────────────
_SCAN_RANGE = 40               # Max IDs to probe per cycle (adaptive stop applies)
_MAX_CONSECUTIVE_INVALID = 25  # Stop only after 25 consecutive misses
_HEAD_TIMEOUT = 8              # Seconds per HEAD probe
_GET_TIMEOUT  = 15             # Seconds for the listing page GET
# Human-like pacing — randomized to avoid fingerprinting
_DELAY_NORMAL   = (0.8, 2.0)   # Delay range between requests (normal)
_DELAY_THROTTLE = (2.0, 4.0)   # Delay range when many consecutive misses
_THROTTLE_MISS_THRESHOLD = 10  # After this many misses, switch to slow lane


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

    def load_seen_cache(self, seen_ids: list):
        """Restore persisted seen-ID cache to prevent re-detection across restarts."""
        self._seen_ids = set(seen_ids)

    def get_seen_cache(self) -> list:
        """Export recent seen IDs for persistence (capped at 200, newest kept)."""
        return sorted(self._seen_ids)[-200:]

    # ------------------------------------------------------------------
    # Startup baseline — discover frontier without returning projects
    # ------------------------------------------------------------------

    def establish_baseline(self, session) -> int:
        """
        Scan forward from the current high-water mark to find the true
        frontier (latest valid request ID) WITHOUT returning any projects.

        Strategy:
        1. Fetch listing page to bulk-discover current highest ID (1 GET).
        2. Probe forward from that point in batches until hitting
           _MAX_CONSECUTIVE_INVALID consecutive invalid IDs.
        3. Update _last_id and _seen_ids silently.

        Returns the frontier ID.  No projects, no UI, no notifications.
        """
        # ── Step 1: Listing page — jump to the current neighbourhood ──
        listing_data = self._fetch_listing(session)
        if listing_data:
            listing_max = max(listing_data.keys())
            if listing_max > self._last_id:
                self._last_id = listing_max
            self._seen_ids.update(listing_data.keys())
            print(f"[Khamsat] Listing baseline: #{listing_max} "
                  f"({len(listing_data)} existing requests)")

        if self._last_id == 0:
            print("[Khamsat] Baseline failed — no IDs discovered")
            return 0

        # ── Step 2: Forward probing — find the true frontier ──────────
        # Probe in batches until no valid IDs are found (frontier hit).
        # Safety cap: max 10 batches (200 IDs) to prevent runaway scanning.
        max_batches = 10
        for _ in range(max_batches):
            start_id = self._last_id + 1
            end_id = start_id + _SCAN_RANGE
            validated = self._probe_ids(session, start_id, end_id)

            if not validated:
                # No valid IDs in this batch — frontier reached
                break

            frontier = max(validated)
            self._last_id = frontier
            self._seen_ids.update(validated)

        print(f"[Khamsat] Baseline established at #{self._last_id}")
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
        if len(self._seen_ids) > 500:
            sorted_ids = sorted(self._seen_ids)
            self._seen_ids = set(sorted_ids[-300:])

        return projects

    def fetch_full_description(self, project, session):
        """Fetch the full request description from the individual page."""
        desc, budget = project.description, project.budget
        try:
            if not project.link:
                return desc, budget
            
            response = session.get(project.link, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")
                
                # The first forum_post is the original request. We want its content.
                # Common Khamsat content containers:
                desc_el = soup.select_one("div.card-body article.replace_urls")
                if not desc_el:
                    desc_el = soup.select_one("article .post-content, div.post-content, div.ajax_post .text_wrapper, .forum_post .content")
                
                if desc_el:
                    # Remove blockquotes or unwanted elements if necessary
                    for unwanted in desc_el.select("blockquote, .post-signature, script, style, .text-muted"):
                        unwanted.decompose()
                        
                    # Replace br tags with newlines to preserve line breaks
                    for br in desc_el.find_all("br"):
                        br.replace_with("\n")
                        
                    extracted_text = self.clean_description(desc_el.get_text("\n", strip=True))
                    if extracted_text and len(extracted_text) > 10:
                        desc = extracted_text
        except Exception as e:
            print(f"Fetch details error (Khamsat): {e}")
        
        return desc, budget

    # ------------------------------------------------------------------
    # First-run seeding (legacy fallback for scrape() when _last_id==0)
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
        Sequential adaptive HEAD crawler.

        Probes IDs one at a time with human-like randomized delays.
        Automatically throttles when many consecutive misses are detected,
        making the crawler look natural and avoid anti-bot / rate-limit triggers.

        Stops only after _MAX_CONSECUTIVE_INVALID (25) consecutive misses.
        Resets counter immediately when a valid ID is found (gap recovery).

        Returns sorted list of validated request IDs.
        """
        validated = []
        consecutive_invalid = 0

        for req_id in range(start_id, end_id):
            url = f"{_BASE_URL}/community/requests/{req_id}"
            is_valid = False
            canonical = url

            try:
                resp = session.head(
                    url, headers=HEADERS, timeout=_HEAD_TIMEOUT,
                    allow_redirects=True
                )
                final_url = resp.url
                path = self._urlparse(final_url).path
                is_valid = (
                    resp.status_code == 200
                    and f"/{req_id}-" in path
                    and path.startswith("/community/requests/")
                    and "/community/showcase/" not in final_url
                )
                if is_valid:
                    canonical = final_url
            except Exception:
                pass  # Timeout / network error — treated as miss

            if is_valid:
                validated.append(req_id)
                self._validated_urls[req_id] = canonical
                consecutive_invalid = 0  # gap bridged — reset counter
                delay = random.uniform(*_DELAY_NORMAL)
            else:
                consecutive_invalid += 1
                if consecutive_invalid >= _MAX_CONSECUTIVE_INVALID:
                    break  # True frontier reached — stop probing
                # Smart throttle: slow down after many misses to look natural
                if consecutive_invalid > _THROTTLE_MISS_THRESHOLD:
                    delay = random.uniform(*_DELAY_THROTTLE)
                else:
                    delay = random.uniform(*_DELAY_NORMAL)

            time.sleep(delay)

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
