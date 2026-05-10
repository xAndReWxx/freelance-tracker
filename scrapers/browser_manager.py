"""
Synchronous Playwright browser manager for WAF-protected page rendering.

Maintains a persistent headless Chromium instance that is reused across
requests.  Thread-safe via a threading.Lock and Semaphore.

Usage (from worker threads):
    from scrapers.browser_manager import browser_mgr

    html = browser_mgr.fetch_page_html(url)
    browser_mgr.shutdown()
"""
import threading
import logging

logger = logging.getLogger(__name__)

# Block these resource types to save bandwidth, CPU, and RAM
_BLOCKED_TYPES = {"image", "font", "media", "stylesheet", "manifest", "other"}


class SyncBrowserManager:
    """Lazy-initialised, persistent sync Playwright browser (thread-safe)."""

    def __init__(self, max_concurrent: int = 1):
        self._playwright = None
        self._browser = None
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_browser(self):
        """Launch browser on first call; reconnect if it crashed."""
        if self._browser and self._browser.is_connected():
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning(
                "playwright is not installed — Playwright fallback disabled. "
                "Install with: pip install playwright && playwright install chromium"
            )
            raise

        with self._lock:
            # Double-check after acquiring lock
            if self._browser and self._browser.is_connected():
                return

            if self._playwright is None:
                self._playwright = sync_playwright().start()

            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                ],
            )
            logger.info("Playwright browser launched (headless)")

    def shutdown(self):
        """Gracefully close the browser and Playwright."""
        self._closed = True
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.debug(f"Browser shutdown note: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_page_html(
        self,
        url: str,
        wait_selector: str = "article.replace_urls",
        timeout_ms: int = 30000,
    ) -> str | None:
        """
        Navigate to *url* in a fresh page, wait for *wait_selector*,
        and return the full rendered HTML.

        Returns None on any failure (timeout, crash, missing selector).
        """
        if self._closed:
            return None

        self._semaphore.acquire()
        try:
            try:
                self._ensure_browser()
            except ImportError:
                return None

            page = None
            try:
                page = self._browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                    locale="ar-SA",
                )

                # Block heavy resources
                page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type in _BLOCKED_TYPES
                        else route.continue_()
                    ),
                )

                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                # Wait for the content selector to appear
                try:
                    page.wait_for_selector(
                        wait_selector, timeout=min(timeout_ms, 15000)
                    )
                except Exception:
                    # Selector not found — page might still have useful HTML
                    pass

                # Small extra delay for JS hydration
                import time
                time.sleep(1)

                return page.content()

            except Exception as e:
                logger.warning(f"Playwright fetch failed for {url}: {e}")
                return None
            finally:
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
        finally:
            self._semaphore.release()


# Singleton instance — import and use directly
browser_mgr = SyncBrowserManager(max_concurrent=1)
