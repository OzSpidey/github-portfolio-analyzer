"""GitHub REST API v3 client with caching, pagination, and rate-limit handling."""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from config import (
    CACHE_DIR, CACHE_TTL_S, GITHUB_API_BASE,
    MAX_COMMIT_PAGES, RATE_LIMIT_BUFFER, REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when the GitHub API rate limit is hit and cannot be recovered."""


class GitHubClient:
    """GitHub REST API v3 client with caching, pagination, and rate-limit backoff."""

    def __init__(self, token: str | None = None) -> None:
        """Initialise session; load token from env if not provided."""
        self._session = requests.Session()
        resolved_token = token or os.getenv("GITHUB_TOKEN")
        if resolved_token:
            self._session.headers["Authorization"] = f"token {resolved_token}"
            logger.info("GitHub client initialised with auth token (5000 req/hr limit)")
        else:
            logger.info("GitHub client initialised without token (60 req/hr limit)")
        self._session.headers.update({
            "Accept":     "application/vnd.github.v3+json",
            "User-Agent": "GitHubPortfolioAnalyzer/1.0",
        })
        CACHE_DIR.mkdir(exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_user(self, username: str) -> dict:
        """Fetch public profile for a GitHub user."""
        return self._cached_get(f"user_{username}", f"/users/{username}")

    def get_repos(self, username: str) -> list[dict]:
        """Fetch all public repositories for a user (handles pagination)."""
        return self._cached_paginated(
            f"repos_{username}",
            f"/users/{username}/repos",
            params={"type": "public", "per_page": 100, "sort": "updated"},
        )

    def get_languages(self, username: str, repo: str) -> dict[str, int]:
        """Fetch language byte breakdown for a single repository."""
        return self._cached_get(
            f"langs_{username}_{repo}",
            f"/repos/{username}/{repo}/languages",
        )

    def get_commits(self, username: str, repo: str) -> list[dict]:
        """Fetch recent commits for a repository (up to MAX_COMMIT_PAGES pages)."""
        key = f"commits_{username}_{repo}"
        cached = self._load_cache(key)
        if cached is not None:
            return cached
        results: list[dict] = []
        url = f"{GITHUB_API_BASE}/repos/{username}/{repo}/commits"
        params: dict[str, Any] = {"author": username, "per_page": 100}
        for _ in range(MAX_COMMIT_PAGES):
            try:
                resp = self._request(url, params=params)
                page = resp.json()
                if not isinstance(page, list) or not page:
                    break
                results.extend(page)
                next_url = self._next_link(resp)
                if not next_url:
                    break
                url = next_url
                params = {}
            except requests.HTTPError as exc:
                logger.warning("Could not fetch commits for %s/%s: %s", username, repo, exc)
                break
        self._save_cache(key, results)
        return results

    def check_rate_limit(self) -> dict:
        """Return current rate limit status from the API."""
        try:
            resp = self._session.get(
                f"{GITHUB_API_BASE}/rate_limit", timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return resp.json().get("rate", {})
        except Exception as exc:
            logger.warning("Could not check rate limit: %s", exc)
            return {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _cached_get(self, key: str, endpoint: str, params: dict | None = None) -> Any:
        """Return cached value or fetch from API and cache."""
        cached = self._load_cache(key)
        if cached is not None:
            return cached
        resp = self._request(f"{GITHUB_API_BASE}{endpoint}", params=params)
        data = resp.json()
        self._save_cache(key, data)
        return data

    def _cached_paginated(self, key: str, endpoint: str, params: dict | None = None) -> list:
        """Return cached paginated result or fetch all pages and cache."""
        cached = self._load_cache(key)
        if cached is not None:
            return cached
        results = self._paginated_get(f"{GITHUB_API_BASE}{endpoint}", params=params)
        self._save_cache(key, results)
        return results

    def _paginated_get(self, url: str, params: dict | None = None) -> list:
        """Follow Link rel=next headers and return concatenated results."""
        results: list = []
        current_url: str | None = url
        current_params = params
        while current_url:
            try:
                resp = self._request(current_url, params=current_params)
                page = resp.json()
                if not isinstance(page, list):
                    break
                results.extend(page)
                current_url = self._next_link(resp)
                current_params = None
            except requests.HTTPError as exc:
                logger.warning("Pagination stopped: %s", exc)
                break
        return results

    def _request(self, url: str, params: dict | None = None, retries: int = 3) -> requests.Response:
        """Make a single request with rate-limit awareness and exponential backoff."""
        for attempt in range(retries):
            try:
                resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                self._handle_rate_limit(resp)
                resp.raise_for_status()
                return resp
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status in (429, 503) and attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("HTTP %s — retrying in %ss", status, wait)
                    time.sleep(wait)
                    continue
                raise
            except requests.Timeout:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise requests.ConnectionError(f"All {retries} attempts failed for {url}")

    def _handle_rate_limit(self, resp: requests.Response) -> None:
        """Sleep until rate limit resets if remaining requests fall below buffer."""
        remaining = int(resp.headers.get("X-RateLimit-Remaining", 999))
        if remaining < RATE_LIMIT_BUFFER:
            reset_ts  = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait_secs = max(0, reset_ts - int(time.time())) + 2
            logger.warning("Rate limit low (%s remaining) — sleeping %ss", remaining, wait_secs)
            time.sleep(wait_secs)

    @staticmethod
    def _next_link(resp: requests.Response) -> str | None:
        """Parse Link header and return the `next` URL, or None."""
        link_header = resp.headers.get("Link", "")
        for part in link_header.split(","):
            url_part, *rel_parts = part.strip().split(";")
            if any('rel="next"' in r for r in rel_parts):
                return url_part.strip().strip("<>")
        return None

    def _cache_path(self, key: str) -> Path:
        """Return the cache file path for a given key."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return CACHE_DIR / f"{safe}.json"

    def _load_cache(self, key: str) -> Any | None:
        """Return cached data if fresh, else None."""
        path = self._cache_path(key)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > CACHE_TTL_S:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, key: str, data: Any) -> None:
        """Persist data to cache file."""
        try:
            self._cache_path(key).write_text(
                json.dumps(data, default=str), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not write cache for %s: %s", key, exc)
