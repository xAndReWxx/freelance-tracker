import time
import asyncio
import logging
import random
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Realistic browser headers ────────────────────────────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Referer": "https://khamsat.com/",
    "Connection": "keep-alive",
    "Sec-Ch-Ua": '"Chromium";v="136", "Not.A/Brand";v="99", "Google Chrome";v="136"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# ── Metrics Tracking ───────────────────────────────────────────────
_METRICS = {
    "waf_503_count": 0,
    "total_requests": 0,
    "failed_requests": 0,
    "last_response_time": 0.0
}


class BrowserClientManager:
    """Manages an ultra-light, persistent httpx session for Khamsat.

    Optimized purely for:
      - Browser fingerprinting via realistic headers
      - Persistent connection pooling (http2)
      - Lightweight 503 WAF recovery
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._adaptive_slowdown = 0.0

    @property
    def client(self) -> Optional[httpx.AsyncClient]:
        return self._client

    @property
    def metrics(self) -> dict:
        return _METRICS.copy()

    async def initialize(self):
        """Create the AsyncClient, apply headers, and perform a warmup request."""
        async with self._lock:
            if self._client and not self._closed:
                return

            self._client = httpx.AsyncClient(
                http2=True,
                follow_redirects=True,
                timeout=httpx.Timeout(15.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=30,
                    max_keepalive_connections=15,
                    keepalive_expiry=120.0,
                ),
                headers=_BROWSER_HEADERS,
            )

            await self._warmup()
            logger.info("[KhamsatSession] ✓ Browser client initialized (Headers only)")

    async def _warmup(self):
        """Lightweight warmup request to establish connection."""
        if not self._client:
            return
        try:
            start = time.perf_counter()
            await self._client.get("https://khamsat.com/", timeout=10.0)
            _METRICS["last_response_time"] = time.perf_counter() - start
            _METRICS["total_requests"] += 1
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception:
            pass

    async def shutdown(self):
        """Gracefully close the httpx client."""
        self._closed = True
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            finally:
                self._client = None

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Header-driven GET with lightweight 503 retry logic."""
        if self._closed or not self._client:
            return None
        
        try:
            if self._adaptive_slowdown > 0:
                await asyncio.sleep(self._adaptive_slowdown + random.uniform(0.1, 0.5))

            start = time.perf_counter()
            response = await self._client.get(url, **kwargs)
            _METRICS["last_response_time"] = time.perf_counter() - start
            _METRICS["total_requests"] += 1

            # 503 is the primary WAF challenge
            if response.status_code == 503:
                _METRICS["waf_503_count"] += 1
                logger.warning(f"[KhamsatSession] 503 WAF triggered on {url}")
                
                if self._adaptive_slowdown == 0:
                    self._adaptive_slowdown = 1.0
                elif self._adaptive_slowdown < 8.0:
                    self._adaptive_slowdown = min(8.0, self._adaptive_slowdown * 2.0)
                
                # Randomized retry after cooldown
                await asyncio.sleep(random.uniform(2.0, 5.0))
                response = await self._client.get(url, **kwargs)
                _METRICS["total_requests"] += 1

            if response and response.status_code == 200:
                # Smoothly decay slowdown
                if self._adaptive_slowdown > 0:
                    self._adaptive_slowdown = max(0.0, self._adaptive_slowdown - 0.5)
            else:
                _METRICS["failed_requests"] += 1

            return response

        except Exception as e:
            _METRICS["failed_requests"] += 1
            return None

# ── Global Singleton ──────────────────────────────────────────────────
khamsat_session = BrowserClientManager()

