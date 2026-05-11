"""
Khamsat community requests scraper.

Ultra-fast, authenticated, browserless implementation using httpx.
No Playwright. No Selenium. No browser automation.
"""
import re
import time
import asyncio
import random
import logging
from typing import Optional
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from scrapers.session_manager import khamsat_session
from models import Project

_LISTING_URL = "https://khamsat.com/community/requests"
_BASE_URL = "https://khamsat.com"

# ── Tuning constants ─────────────────────────────────────────────
_SCAN_RANGE_DEFAULT = 30       # Normal range
_SCAN_RANGE_MIN = 15           # Idle range
_SCAN_RANGE_MAX = 50           # Active period range
_MAX_CONSECUTIVE_INVALID = 15  # Fix 3: Stop after 15 consecutive misses
_CONCURRENCY_LIMIT = 2         # Fix 4: Strictly limited concurrency
_HEAD_TIMEOUT = 10             # Seconds per probe
_GET_TIMEOUT  = 15             # Seconds for full fetch

# Fix 5: Jitter Profiles
_JITTER_SUCCESS  = (0.8, 2.0)  # After successful extraction
_JITTER_MISS     = (0.2, 0.8)  # After an invalid ID
_JITTER_THROTTLE = (2.0, 4.0)  # When throttling is active
_THROTTLE_MISS_THRESHOLD = 8   # Lower threshold for faster throttle response


class KhamsatScraper(BaseScraper):
    SITE_NAME = "Khamsat"
    URL = _LISTING_URL

    def __init__(self):
        super().__init__()
        self._last_id = 0
        self._seen_ids = set()
        self._validated_urls = {}
        from urllib.parse import urlparse
        self._urlparse = urlparse
        self._semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
        self._scan_range = _SCAN_RANGE_DEFAULT
        self._activity_counter = 0

    def set_last_id(self, last_id: int):
        self._last_id = last_id

    def get_last_id(self) -> int:
        return self._last_id

    def load_seen_cache(self, seen_ids: list):
        self._seen_ids = set(seen_ids)

    def get_seen_cache(self) -> list:
        return sorted(self._seen_ids)[-200:]

    async def establish_baseline(self, session) -> int:
        """Establish the high-water mark for Khamsat request IDs.

        Args:
            session: Legacy parameter (ignored — uses internal httpx session).
        """
        listing_data = await self._fetch_listing()
        if listing_data:
            listing_max = max(listing_data.keys())
            if listing_max > self._last_id:
                self._last_id = listing_max
            self._seen_ids.update(listing_data.keys())
            print(f"[Khamsat] Listing baseline: #{listing_max}")

        if self._last_id == 0:
            return 0

        max_batches = 5
        for _ in range(max_batches):
            start_id = self._last_id + 1
            # For baseline, we use a fixed range
            end_id = start_id + _SCAN_RANGE_DEFAULT
            
            async for p in self._probe_projects_stream(start_id, end_id):
                req_id = getattr(p, 'id', 0)
                if req_id > self._last_id:
                    self._last_id = req_id
                self._seen_ids.add(req_id)

        print(f"[Khamsat] Baseline established at #{self._last_id}")
        return self._last_id

    async def scrape(self, session):
        """Scrape for new Khamsat community requests with streaming async generator.

        Args:
            session: Legacy parameter (ignored — uses internal httpx session).
        Yields:
            Project: Detected and extracted projects one by one.
        """
        if self._last_id == 0:
            # For seeding, we still return a list to maintain compatibility if needed, 
            # but we can also yield from it.
            listing_projects = await self._seed_from_listing()
            for p in listing_projects:
                yield p
            return

        # Adaptive Scan Range (Fix 7)
        if self._activity_counter > 2:
            self._scan_range = min(_SCAN_RANGE_MAX, self._scan_range + 5)
        elif self._activity_counter == 0:
            self._scan_range = max(_SCAN_RANGE_MIN, self._scan_range - 2)
        
        self._activity_counter = 0 # Reset for current cycle
        start_id = self._last_id + 1
        end_id = start_id + self._scan_range

        # Ultra-fast one-pass detection + extraction with streaming
        async for project in self._probe_projects_stream(start_id, end_id):
            req_id = getattr(project, 'id', None)
            if req_id and req_id not in self._seen_ids:
                self._activity_counter += 1
                self._seen_ids.add(req_id)
                if req_id > self._last_id:
                    self._last_id = req_id
                
                # Add detection timestamp for Fix 10
                project.detected_at = time.time()
                yield project

        if len(self._seen_ids) > 500:
            sorted_ids = sorted(self._seen_ids)
            self._seen_ids = set(sorted_ids[-300:])

    async def fetch_full_description(self, project, session):
        """Redundant in the new ultra-fast flow but kept for interface compatibility."""
        # If description is already extracted (not the placeholder), just return it
        if project.description and "جاري استخراج" not in project.description:
            return project.description, project.budget
        
        # Fallback for seeded projects from listing if needed
        try:
            response = await khamsat_session.get(project.link, timeout=_GET_TIMEOUT)
            if response and response.status_code == 200:
                extracted = self._extract_description_from_html(response.text)
                if extracted:
                    return extracted, project.budget
        except Exception:
            pass
        return project.description, project.budget

    def _extract_description_from_html(self, html: str) -> str | None:
        """Extract and clean the request description from rendered HTML.
        
        Fix 10: Improved robustness for malformed HTML and missing body.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Primary selector: the main request body
            desc_el = soup.select_one("div.card-body article.replace_urls")
            
            extracted_text = ""
            if desc_el:
                # Remove noise elements (usernames, metadata, sidebar)
                for unwanted in desc_el.select(
                    "blockquote, .post-signature, script, style, .text-muted, .user-name, .author, .details-sidebar"
                ):
                    unwanted.decompose()

                # Preserve line breaks
                for br in desc_el.find_all("br"):
                    br.replace_with("\n")
                
                extracted_text = desc_el.get_text("\n", strip=True)
            
            # Fallback to meta description if body is empty or too short
            if not extracted_text or len(extracted_text) < 15:
                meta = soup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content"):
                    extracted_text = meta["content"].strip()

            if not extracted_text:
                return None

            clean_text = self.clean_description(extracted_text)
            
            # ── Smart Description Validation ─────────────────────────────
            reject_keywords = ["منذ", "طلب جديد", "عضو", "متابعة", "آخر تفاعل", "التصنيف"]
            
            if any(kw in clean_text for kw in reject_keywords):
                return None
                
            if len(clean_text) < 20: 
                return None
                
            if clean_text.count(":") > 5: # Likely metadata block
                return None

            return clean_text
        except Exception as e:
            logger.debug(f"[KhamsatExtraction] Error: {e}")
            return None

    async def _probe_projects_stream(self, start_id: int, end_id: int):
        """One-pass project detection and description extraction with streaming tasks.
        
        Fix 1: Exception safety inside as_completed.
        Fix 2: Orphan task cleanup.
        """
        consecutive_invalid = 0
        step = _CONCURRENCY_LIMIT
        
        for i in range(start_id, end_id, step):
            batch_ids = range(i, min(i + step, end_id))
            tasks = [asyncio.create_task(self._probe_single_id(req_id)) for req_id in batch_ids]
            
            any_valid_in_batch = False
            try:
                # Process tasks as they complete
                for coro in asyncio.as_completed(tasks):
                    try:
                        project = await coro
                        if project:
                            yield project
                            any_valid_in_batch = True
                            consecutive_invalid = 0
                        else:
                            consecutive_invalid += 1
                    except Exception as e:
                        logger.error(f"[KhamsatStream] Task error: {e}")
                        consecutive_invalid += 1
                        continue
                
                if consecutive_invalid >= _MAX_CONSECUTIVE_INVALID:
                    break
                    
                # Batch-level Jitter
                if any_valid_in_batch:
                    await asyncio.sleep(random.uniform(*_JITTER_SUCCESS))
                else:
                    await asyncio.sleep(random.uniform(*_JITTER_MISS))
                    
                if consecutive_invalid > _THROTTLE_MISS_THRESHOLD:
                    await asyncio.sleep(random.uniform(*_JITTER_THROTTLE))
                    
            finally:
                # Fix 2: Orphan task cleanup
                for t in tasks:
                    if not t.done():
                        t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_single_id(self, req_id: int) -> Optional[Project]:
        """Probe a single ID with semaphore protection and per-task jitter."""
        # Fix 5: Tiny per-task jitter to avoid perfectly synchronized requests
        await asyncio.sleep(random.uniform(0.01, 0.1))

        async with self._semaphore:
            url = f"{_BASE_URL}/community/requests/{req_id}"
            
            # Authenticated GET (Fix 9: Timeout resilience handled by session manager)
            resp = await khamsat_session.get(url, timeout=_HEAD_TIMEOUT)

            if resp and resp.status_code == 200:
                final_url = str(resp.url)
                path = self._urlparse(final_url).path
                
                if (f"/{req_id}-" in path and path.startswith("/community/requests/") 
                    and "/community/showcase/" not in final_url):
                    
                    description = self._extract_description_from_html(resp.text)
                    title = self._title_from_slug(final_url, req_id)
                    
                    if description:
                        p = Project(
                            site=self.SITE_NAME,
                            title=title,
                            link=final_url,
                            description=description,
                            budget=""
                        )
                        p.id = req_id
                        return p
            return None

    async def _fetch_listing(self) -> dict:
        """Fetch the listing page using authenticated httpx session."""
        try:
            resp = await khamsat_session.get(
                _LISTING_URL, timeout=_GET_TIMEOUT
            )
            if resp is None or resp.status_code != 200:
                return {}
            html = resp.text
        except Exception:
            return {}

        soup = BeautifulSoup(html, "html.parser")
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
        canonical = self._validated_urls.get(req_id, "")
        url = canonical or f"{_BASE_URL}/community/requests/{req_id}"
        title = self._title_from_slug(canonical, req_id)
        return Project(
            site=self.SITE_NAME,
            title=title,
            link=url,
            description="⏱ جاري استخراج التفاصيل...",
            budget=""
        )

    def _parse_row(self, row):
        link_el = row.select_one("h3.details-head a")
        if not link_el:
            return None, None

        href = link_el.get("href", "")
        title = link_el.get_text(strip=True)

        if not href or not title:
            return None, None

        req_id = self._extract_id_from_href(href)
        if req_id is None:
            return None, None

        full_url = f"{_BASE_URL}{href}" if href.startswith("/") else href

        # Time extraction
        relative_time = ""
        spans = row.find_all("span")
        for span in spans:
            text = span.get_text(strip=True)
            if text.startswith("منذ") and "آخر تفاعل" not in text:
                relative_time = text
                break

        desc_parts = []
        if relative_time:
            desc_parts.append(f"⏱ {relative_time}")

        user_el = row.select_one("a.user-name, a.author, span.user-name")
        if user_el:
            username = user_el.get_text(strip=True)
            desc_parts.append(f"👤 {username}")

        description = "\n".join(desc_parts) if desc_parts else "⏱ طلب جديد"

        return Project(
            site=self.SITE_NAME,
            title=title,
            link=full_url,
            description=description,
            budget=""
        ), req_id

    @staticmethod
    def _extract_id_from_href(href: str):
        match = re.search(r"/community/requests/(\d+)", href)
        return int(match.group(1)) if match else None

    @staticmethod
    def _title_from_slug(canonical_url: str, req_id: int) -> str:
        if not canonical_url:
            return f"Khamsat Request #{req_id}"
        try:
            from urllib.parse import unquote
            match = re.search(rf"/{req_id}-(.+)$", canonical_url)
            if match:
                slug = unquote(match.group(1))
                title = slug.replace("-", " ").strip()
                if title:
                    return title
        except Exception:
            pass
        return f"Khamsat Request #{req_id}"
