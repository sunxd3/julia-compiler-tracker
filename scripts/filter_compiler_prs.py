#!/usr/bin/env python3
"""Filter cached PRs to keep only compiler-related ones."""

import json
import sys
from pathlib import Path

# Add gh-utils to path
sys.path.insert(0, str(Path(__file__).parent.parent / "gh-utils" / "src"))

from gh_utils import PRCache, filter_compiler_prs, get_pr_files

REPO = "JuliaLang/julia"
CACHE_DIR = Path(__file__).parent.parent / "pr-archive"


def main():
    cache = PRCache(CACHE_DIR)
    index = cache.get_index(REPO)
    pr_numbers = [int(n) for n in index.get("prs", {}).keys()]

    print(f"Total cached PRs: {len(pr_numbers)}")
    print()

    # First, fetch files for PRs that don't have them cached
    print("Checking for PRs without cached files...")
    missing_files = []
    for pr_num in pr_numbers:
        pr_data = cache.get_pr(REPO, pr_num)
        if pr_data and "files" not in pr_data:
            missing_files.append(pr_num)

    if missing_files:
        print(f"Need to fetch files for {len(missing_files)} PRs")
        print("Fetching... (this may take a while)")
        for i, pr_num in enumerate(missing_files):
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(missing_files)}")
            try:
                files = get_pr_files(pr_num, REPO)
                pr_data = cache.get_pr(REPO, pr_num)
                if pr_data:
                    pr_data["files"] = files
                    cache.save_pr(REPO, pr_num, pr_data)
            except Exception as e:
                print(f"  Warning: Failed to fetch files for PR #{pr_num}: {e}")
        print(f"  Done fetching files")
    else:
        print("All PRs have cached files")

    print()

    # Now filter for compiler PRs
    print("Filtering for compiler-related PRs...")
    compiler_prs, pr_files_map = filter_compiler_prs(
        pr_numbers, REPO, cache, fetch_missing=False
    )

    print(f"Found {len(compiler_prs)} compiler-related PRs (out of {len(pr_numbers)})")
    print()

    # Save results
    output_file = CACHE_DIR / "JuliaLang_julia" / "compiler_prs.json"
    result = {
        "total_prs": len(pr_numbers),
        "compiler_prs": len(compiler_prs),
        "pr_numbers": sorted(compiler_prs),
        "pr_files": {str(k): v for k, v in pr_files_map.items()},
    }
    output_file.write_text(json.dumps(result, indent=2))
    print(f"Saved to {output_file}")

    # Show sample
    print()
    print("Sample compiler PRs:")
    for pr_num in sorted(compiler_prs)[:5]:
        pr_data = cache.get_pr(REPO, pr_num)
        title = pr_data.get("title", "")[:60] if pr_data else "?"
        files = pr_files_map.get(pr_num, [])
        print(f"  #{pr_num}: {title}")
        for f in files[:3]:
            print(f"    - {f}")
        if len(files) > 3:
            print(f"    ... and {len(files) - 3} more")


if __name__ == "__main__":
    main()
