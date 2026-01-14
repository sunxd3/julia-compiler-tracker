"""Simple JSON file caching for GitHub API responses."""

import json
from pathlib import Path
from typing import Any


class PRCache:
    """Cache for storing fetched PR data."""

    def __init__(self, cache_dir: str | Path = "pr-archive"):
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files.
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_repo_dir(self, repo: str) -> Path:
        """Get cache directory for a repository."""
        # Replace / with _ for safe directory name
        safe_name = repo.replace("/", "_")
        repo_dir = self.cache_dir / safe_name
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir

    def _pr_file(self, repo: str, pr_number: int) -> Path:
        """Get cache file path for a PR."""
        return self._get_repo_dir(repo) / f"pr_{pr_number}.json"

    def _index_file(self, repo: str) -> Path:
        """Get index file path for a repository."""
        return self._get_repo_dir(repo) / "index.json"

    def get_pr(self, repo: str, pr_number: int) -> dict[str, Any] | None:
        """Get a cached PR.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number.

        Returns:
            Cached PR data or None if not cached.
        """
        cache_file = self._pr_file(repo, pr_number)
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        return None

    def save_pr(self, repo: str, pr_number: int, data: dict[str, Any]) -> None:
        """Save a PR to cache.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number.
            data: PR data to cache.
        """
        cache_file = self._pr_file(repo, pr_number)
        cache_file.write_text(json.dumps(data, indent=2))

    def get_index(self, repo: str) -> dict[str, Any]:
        """Get the index of cached PRs for a repository.

        Args:
            repo: Repository in 'owner/repo' format.

        Returns:
            Index dictionary with PR numbers and metadata.
        """
        index_file = self._index_file(repo)
        if index_file.exists():
            return json.loads(index_file.read_text())
        return {"prs": {}, "tag_ranges": {}}

    def save_index(self, repo: str, index: dict[str, Any]) -> None:
        """Save the index for a repository.

        Args:
            repo: Repository in 'owner/repo' format.
            index: Index dictionary.
        """
        index_file = self._index_file(repo)
        index_file.write_text(json.dumps(index, indent=2))

    def get_cached_pr_numbers(self, repo: str) -> set[int]:
        """Get set of all cached PR numbers for a repository.

        Args:
            repo: Repository in 'owner/repo' format.

        Returns:
            Set of PR numbers that are cached.
        """
        index = self.get_index(repo)
        return set(int(n) for n in index.get("prs", {}))

    def save_prs_batch(
        self, repo: str, prs: list[dict[str, Any]], key: str = "number"
    ) -> None:
        """Save a batch of PRs to cache and update index.

        Args:
            repo: Repository in 'owner/repo' format.
            prs: List of PR data dictionaries.
            key: Key to use for PR number (default 'number').
        """
        index = self.get_index(repo)

        for pr in prs:
            pr_number = pr.get(key)
            if pr_number:
                self.save_pr(repo, pr_number, pr)
                index["prs"][str(pr_number)] = {
                    "title": pr.get("title", ""),
                    "merged_at": pr.get("merged_at") or pr.get("mergedAt", ""),
                    "updated_at": pr.get("updated_at") or pr.get("updatedAt", ""),
                }

        self.save_index(repo, index)

    def mark_tag_range_fetched(
        self, repo: str, start_tag: str, end_tag: str, pr_numbers: list[int]
    ) -> None:
        """Mark a tag range as fully fetched.

        Args:
            repo: Repository in 'owner/repo' format.
            start_tag: Start tag.
            end_tag: End tag.
            pr_numbers: List of PR numbers in this range.
        """
        index = self.get_index(repo)
        range_key = f"{start_tag}..{end_tag}"
        index["tag_ranges"][range_key] = pr_numbers
        self.save_index(repo, index)

    def get_tag_range(
        self, repo: str, start_tag: str, end_tag: str
    ) -> list[int] | None:
        """Get cached PR numbers for a tag range.

        Args:
            repo: Repository in 'owner/repo' format.
            start_tag: Start tag.
            end_tag: End tag.

        Returns:
            List of PR numbers if range is cached, None otherwise.
        """
        index = self.get_index(repo)
        range_key = f"{start_tag}..{end_tag}"
        return index.get("tag_ranges", {}).get(range_key)

    def get_cached_updated_at(self, repo: str, pr_number: int) -> str | None:
        """Get the cached updated_at timestamp for a PR.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number.

        Returns:
            Cached updated_at timestamp or None if not cached.
        """
        index = self.get_index(repo)
        pr_info = index.get("prs", {}).get(str(pr_number))
        if pr_info:
            return pr_info.get("updated_at")
        return None

    def is_pr_stale(self, repo: str, pr_number: int, current_updated_at: str) -> bool:
        """Check if a cached PR is stale (needs refresh).

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number.
            current_updated_at: The current updated_at from GitHub API.

        Returns:
            True if the cached PR is older than current_updated_at.
        """
        cached_updated_at = self.get_cached_updated_at(repo, pr_number)
        if cached_updated_at is None:
            return True  # Not cached, consider stale
        return cached_updated_at < current_updated_at

    def find_stale_prs(self, repo: str, current_prs: list[dict[str, Any]]) -> list[int]:
        """Find PRs that have been updated since last cached.

        Args:
            repo: Repository in 'owner/repo' format.
            current_prs: List of PR dicts with 'number' and 'updated_at' fields.

        Returns:
            List of PR numbers that are stale and need refresh.
        """
        stale = []
        for pr in current_prs:
            pr_number = pr.get("number")
            updated_at = pr.get("updated_at") or pr.get("updatedAt", "")
            if pr_number and self.is_pr_stale(repo, pr_number, updated_at):
                stale.append(pr_number)
        return stale
