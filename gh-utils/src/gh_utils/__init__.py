"""GitHub utilities for fetching PRs and repository information."""

from .cache import PRCache
from .client import (
    GitHubAPIError,
    RateLimitError,
    api_get,
    api_get_paginated,
    get_token,
)
from .pr import (
    DEFAULT_REPO,
    fetch_prs_between_tags,
    get_pr_details,
    get_pr_files,
    get_tag_date,
    list_prs_between_dates,
    list_prs_between_tags,
    search_prs,
)

__all__ = [
    # Client
    "GitHubAPIError",
    "RateLimitError",
    "api_get",
    "api_get_paginated",
    "get_token",
    # PR operations
    "get_tag_date",
    "list_prs_between_dates",
    "list_prs_between_tags",
    "fetch_prs_between_tags",
    "search_prs",
    "get_pr_details",
    "get_pr_files",
    "DEFAULT_REPO",
    # Cache
    "PRCache",
]
