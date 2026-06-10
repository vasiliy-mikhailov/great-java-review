"""Rate-limited, single-worker GitHub REST client (stdlib only).

Design goals:
  * ZERO non-stdlib deps -> the crawler never hits dependency hell.
  * Token comes from the `gh` CLI keyring at runtime (`gh auth token`), so no
    secret is ever written to disk.
  * Strictly single-threaded with polite spacing + full respect for primary
    and secondary rate limits -> avoids the bans the user is worried about.
"""
from __future__ import annotations

import http.client
import json
import random
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


def get_token() -> str:
    """Fetch a GitHub token from the gh CLI keyring."""
    out = subprocess.run(
        ["/opt/homebrew/bin/gh", "auth", "token"],
        capture_output=True, text=True, check=True,
    )
    tok = out.stdout.strip()
    if not tok:
        raise RuntimeError("empty gh token")
    return tok


class GitHub:
    def __init__(self, token: str | None = None, min_interval: float = 0.8,
                 user_agent: str = "great-java-review-miner"):
        self.token = token or get_token()
        self.min_interval = min_interval
        self.ua = user_agent
        self._last = 0.0
        self.calls = 0

    # -- low level ---------------------------------------------------------
    def _throttle(self):
        dt = time.time() - self._last
        target = self.min_interval + random.uniform(0, 0.4)  # jitter
        if dt < target:
            time.sleep(target - dt)
        self._last = time.time()

    def _request(self, url: str, params: dict | None = None, retries: int = 8):
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            req.add_header("User-Agent", self.ua)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.calls += 1
                    body = r.read().decode("utf-8")
                    remaining = r.headers.get("X-RateLimit-Remaining")
                    reset = r.headers.get("X-RateLimit-Reset")
                    # Proactively sleep when the primary budget runs low.
                    if remaining is not None and int(remaining) < 30 and reset:
                        wait = max(0, int(reset) - int(time.time())) + 2
                        print(f"[gh] low budget ({remaining}); sleeping {wait}s")
                        time.sleep(wait)
                    nxt = self._next_link(r.headers.get("Link"))
                    return json.loads(body), nxt
            except urllib.error.HTTPError as e:
                # Secondary / abuse rate limit, or 5xx -> back off and retry.
                if e.code in (403, 429):
                    retry_after = e.headers.get("Retry-After")
                    reset = e.headers.get("X-RateLimit-Reset")
                    if retry_after:
                        wait = int(retry_after) + 1
                    elif reset:
                        wait = max(5, int(reset) - int(time.time()) + 2)
                    else:
                        # secondary/abuse limit with no hint: back off hard
                        wait = min(180, 15 * (attempt + 1))
                    print(f"[gh] {e.code} rate-limited; sleeping {wait}s "
                          f"(attempt {attempt+1})")
                    time.sleep(wait)
                    continue
                if 500 <= e.code < 600:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                if e.code == 404:
                    return None, None
                raise
            except (urllib.error.URLError, TimeoutError,
                    http.client.HTTPException, ConnectionError, OSError,
                    ValueError) as e:
                # IncompleteRead, connection reset, timeouts, malformed json...
                print(f"[gh] net/read error {type(e).__name__}: {e}; "
                      f"retry {attempt+1}")
                time.sleep(min(30, 2 ** attempt + 1))
        raise RuntimeError(f"giving up after {retries} retries: {url}")

    @staticmethod
    def _next_link(link_header: str | None) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            seg = part.split(";")
            if len(seg) < 2:
                continue
            if 'rel="next"' in seg[1]:
                return seg[0].strip().strip("<>")
        return None

    # -- helpers -----------------------------------------------------------
    def get(self, path: str, params: dict | None = None):
        url = path if path.startswith("http") else API + path
        data, _ = self._request(url, params)
        return data

    def paginate(self, path: str, params: dict | None = None, max_items: int | None = None):
        """Yield items across pages, stopping at max_items."""
        url = path if path.startswith("http") else API + path
        params = dict(params or {})
        params.setdefault("per_page", 100)
        first = True
        n = 0
        while url:
            try:
                data, nxt = self._request(url, params if first else None)
            except RuntimeError as e:
                # deep-page throttle or persistent error: stop this stream,
                # let the caller move on rather than crashing the whole crawl.
                print(f"[gh] pagination stopped early: {e}")
                return
            first = False
            if data is None:
                return
            items = data if isinstance(data, list) else data.get("items", [])
            for it in items:
                yield it
                n += 1
                if max_items and n >= max_items:
                    return
            url = nxt

    def rate(self):
        return self.get("/rate_limit")
