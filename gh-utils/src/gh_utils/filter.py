"""Filter PRs based on files changed."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .cache import PRCache

# Julia compiler-related paths (focused on Julia code)
COMPILER_PATHS = [
    # Julia compiler (written in Julia) - main focus
    "Compiler/",
    # Parser (written in Julia)
    "JuliaSyntax/",
    # Lowering passes (written in Julia)
    "JuliaLowering/",
    # Interpreter
    "src/interpreter.c",
]


def is_compiler_file(filename: str) -> bool:
    """Check if a file path is compiler-related."""
    return any(filename.startswith(path) for path in COMPILER_PATHS)


def get_compiler_files(files: list[dict[str, Any]]) -> list[str]:
    """Get list of compiler-related files from PR files."""
    return [f["filename"] for f in files if is_compiler_file(f.get("filename", ""))]


def is_compiler_pr(files: list[dict[str, Any]]) -> bool:
    """Check if a PR touches any compiler files."""
    return any(is_compiler_file(f.get("filename", "")) for f in files)


def filter_compiler_prs(
    pr_numbers: list[int],
    repo: str = "JuliaLang/julia",
    cache: "PRCache | None" = None,
    fetch_missing: bool = True,
) -> tuple[list[int], dict[int, list[str]]]:
    """Filter PRs to only those touching compiler files.

    Returns:
        Tuple of (compiler_pr_numbers, pr_compiler_files_map).
    """
    from .cache import PRCache
    from .pr import get_pr_files

    if cache is None:
        cache = PRCache()

    compiler_prs: list[int] = []
    pr_files_map: dict[int, list[str]] = {}

    for pr_num in pr_numbers:
        pr_data = cache.get_pr(repo, pr_num)
        files = None

        if pr_data and "files" in pr_data:
            files = pr_data["files"]
        elif fetch_missing:
            try:
                files = get_pr_files(pr_num, repo)
                if pr_data:
                    pr_data["files"] = files
                    cache.save_pr(repo, pr_num, pr_data)
            except Exception as e:
                print(f"  Warning: Failed to fetch files for PR #{pr_num}: {e}")
                continue

        if files:
            compiler_files = get_compiler_files(files)
            if compiler_files:
                compiler_prs.append(pr_num)
                pr_files_map[pr_num] = compiler_files

    return compiler_prs, pr_files_map
