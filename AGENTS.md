- Use `uv` for all Python work; never call `pip` or `python` directly.
- Always run tools via `uv run` (no `uv pip`, no `uv python`).

- Use `ruff` and `pyrefly` for quality checks (install dev deps first: `uv sync --dev`).