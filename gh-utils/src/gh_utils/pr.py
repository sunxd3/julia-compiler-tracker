"""PR operations for fetching pull requests from GitHub."""

from typing import TYPE_CHECKING, Any

from .client import api_get, api_get_paginated

if TYPE_CHECKING:
    from .cache import PRCache

DEFAULT_REPO = "JuliaLang/julia"


def get_tag_date(tag: str, repo: str = DEFAULT_REPO) -> str:
    """Get the commit date for a git tag.

    Args:
        tag: Tag name (e.g., 'v1.10.0').
        repo: Repository in 'owner/repo' format.

    Returns:
        ISO 8601 date string (e.g., '2024-01-15T10:30:00Z').
    """
    # First get the tag reference to find the commit SHA
    tag_info = api_get(f"/repos/{repo}/git/ref/tags/{tag}")
    tag_sha = tag_info["object"]["sha"]

    # If it's an annotated tag, we need to get the underlying commit
    if tag_info["object"]["type"] == "tag":
        tag_obj = api_get(f"/repos/{repo}/git/tags/{tag_sha}")
        commit_sha = tag_obj["object"]["sha"]
    else:
        commit_sha = tag_sha

    # Get the commit to find its date
    commit = api_get(f"/repos/{repo}/git/commits/{commit_sha}")
    return commit["committer"]["date"]


def search_prs(
    query: str,
    repo: str = DEFAULT_REPO,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Search for PRs using GitHub search API.

    Args:
        query: Search query (e.g., 'is:merged merged:2024-01-01..2024-12-31').
        repo: Repository in 'owner/repo' format.
        limit: Maximum number of PRs to fetch.

    Returns:
        List of PR dictionaries.
    """
    full_query = f"repo:{repo} is:pr {query}"
    max_pages = (limit + 99) // 100  # Ceiling division

    results = []
    for page in range(1, max_pages + 1):
        response = api_get(
            "/search/issues",
            params={"q": full_query, "per_page": 100, "page": page},
        )
        items = response.get("items", [])
        results.extend(items)

        if len(items) < 100 or len(results) >= limit:
            break

    return results[:limit]


def list_prs_between_dates(
    start_date: str,
    end_date: str,
    repo: str = DEFAULT_REPO,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch PRs merged within a date range.

    Args:
        start_date: Start date in ISO format (e.g., '2024-01-01').
        end_date: End date in ISO format (e.g., '2024-12-31').
        repo: Repository in 'owner/repo' format.
        limit: Maximum number of PRs to fetch.

    Returns:
        List of PR dictionaries with details.
    """
    query = f"is:merged merged:{start_date}..{end_date}"
    return search_prs(query, repo, limit)


def list_prs_between_tags(
    start_tag: str,
    end_tag: str,
    repo: str = DEFAULT_REPO,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch PRs merged between two git tags.

    Args:
        start_tag: Starting tag (older, e.g., 'v1.10.0').
        end_tag: Ending tag (newer, e.g., 'v1.10.1').
        repo: Repository in 'owner/repo' format.
        limit: Maximum number of PRs to fetch.

    Returns:
        List of PR dictionaries with details.
    """
    start_date = get_tag_date(start_tag, repo)
    end_date = get_tag_date(end_tag, repo)

    # Extract just the date part for the search query
    start_date_only = start_date.split("T")[0]
    end_date_only = end_date.split("T")[0]

    return list_prs_between_dates(start_date_only, end_date_only, repo, limit)


def get_pr_details(pr_number: int, repo: str = DEFAULT_REPO) -> dict[str, Any]:
    """Get detailed information about a specific PR.

    Args:
        pr_number: The PR number.
        repo: Repository in 'owner/repo' format.

    Returns:
        Dictionary with PR details.
    """
    return api_get(f"/repos/{repo}/pulls/{pr_number}")


def get_pr_files(pr_number: int, repo: str = DEFAULT_REPO) -> list[dict[str, Any]]:
    """Get the list of files changed in a PR.

    Args:
        pr_number: The PR number.
        repo: Repository in 'owner/repo' format.

    Returns:
        List of file dictionaries with path and change info.
    """
    return api_get_paginated(f"/repos/{repo}/pulls/{pr_number}/files")


def fetch_prs_between_tags(
    start_tag: str,
    end_tag: str,
    cache: "PRCache | None" = None,
    repo: str = DEFAULT_REPO,
    limit: int = 1000,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Fetch PRs between tags with automatic caching.

    This is the recommended way to fetch PRs. It will:
    1. Check if the tag range is already cached
    2. If cached, load PRs from cache
    3. If not cached, fetch from API and save to cache

    Args:
        start_tag: Starting tag (older, e.g., 'v1.10.0').
        end_tag: Ending tag (newer, e.g., 'v1.10.1').
        cache: PRCache instance. If None, creates one with default settings.
        repo: Repository in 'owner/repo' format.
        limit: Maximum number of PRs to fetch.
        force_refresh: If True, fetch from API even if cached.

    Returns:
        List of PR dictionaries with details.
    """
    # Import here to avoid circular imports
    from .cache import PRCache

    if cache is None:
        cache = PRCache()

    # Check cache first (unless force refresh)
    if not force_refresh:
        cached_numbers = cache.get_tag_range(repo, start_tag, end_tag)
        if cached_numbers is not None:
            prs = []
            for pr_num in cached_numbers:
                pr_data = cache.get_pr(repo, pr_num)
                if pr_data:
                    prs.append(pr_data)
            return prs

    # Fetch from API
    prs = list_prs_between_tags(start_tag, end_tag, repo, limit)

    # Save to cache
    cache.save_prs_batch(repo, prs)
    pr_numbers = [pr["number"] for pr in prs]
    cache.mark_tag_range_fetched(repo, start_tag, end_tag, pr_numbers)

    return prs
