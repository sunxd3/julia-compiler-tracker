"""GitHub API client using requests."""

import os
import time
from typing import Any

import requests

GITHUB_API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """Exception raised when GitHub API request fails."""

    def __init__(self, message: str, status_code: int, response_body: str):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RateLimitError(GitHubAPIError):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str, reset_time: int):
        super().__init__(message, 403, "Rate limit exceeded")
        self.reset_time = reset_time


def get_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get_headers() -> dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def check_rate_limit(response: requests.Response) -> None:
    """Check rate limit headers and raise if exceeded."""
    if response.status_code == 403:
        remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
        if remaining == "0":
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            raise RateLimitError(
                f"Rate limit exceeded. Resets at {time.ctime(reset_time)}",
                reset_time,
            )


def api_get(
    endpoint: str,
    params: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> Any:
    """Make a GET request to the GitHub API.

    Args:
        endpoint: API endpoint (e.g., '/repos/owner/repo/pulls').
        params: Optional query parameters.
        max_retries: Maximum retries on rate limit (with exponential backoff).

    Returns:
        Parsed JSON response.

    Raises:
        GitHubAPIError: If the request fails.
        RateLimitError: If rate limit exceeded after retries.
    """
    url = f"{GITHUB_API_BASE}{endpoint}"
    headers = get_headers()

    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                wait_time = max(reset_time - time.time(), 0) + 1

                if attempt < max_retries - 1 and wait_time < 60:
                    # Only wait if it's less than a minute
                    time.sleep(min(wait_time, 2 ** (attempt + 1)))
                    continue

                raise RateLimitError(
                    f"Rate limit exceeded. Resets at {time.ctime(reset_time)}. "
                    f"Set GITHUB_TOKEN env var for higher limits.",
                    reset_time,
                )

        raise GitHubAPIError(
            f"GitHub API error: {response.status_code} {response.reason}",
            response.status_code,
            response.text,
        )

    raise GitHubAPIError("Max retries exceeded", 0, "")


def api_get_paginated(
    endpoint: str,
    params: dict[str, Any] | None = None,
    max_pages: int = 10,
    per_page: int = 100,
) -> list[Any]:
    """Make paginated GET requests to the GitHub API.

    Args:
        endpoint: API endpoint.
        params: Optional query parameters.
        max_pages: Maximum number of pages to fetch.
        per_page: Items per page (max 100).

    Returns:
        Combined list of all results.
    """
    params = params or {}
    params["per_page"] = per_page

    results = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        page_results = api_get(endpoint, params)

        if not page_results:
            break

        results.extend(page_results)

        if len(page_results) < per_page:
            break

    return results
