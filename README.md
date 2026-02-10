# Julia Compiler Tracker

Track and analyze compiler-related changes in Julia for downstream package maintainers.

## Structure

```
├── analyses/
│   ├── v1.13/             # PR analyses (.md) + missing_prs.md tracking
│   └── v1.14/             # PR analyses
├── data/
│   └── v1.13/
│       ├── all_prs.txt        # All 1,274 PRs between 1.12 and 1.13
│       └── compiler_prs.txt   # 269 compiler-related PRs with titles
├── changelogs/            # Human-readable version changelogs
├── compiler-deep-dive/    # Julia compiler internals documentation
├── julia/                 # Julia repo workspace (checkout PRs here)
├── ANALYSIS_GUIDE.md      # How to write PR analyses
└── CLAUDE.md              # Agent instructions
```

## Writing analyses

See [ANALYSIS_GUIDE.md](ANALYSIS_GUIDE.md) for the full guide. Each analysis is a markdown file at `analyses/{version}/pr_{number}.md`.

## Version info

| Version | Branch point | Commit | Total PRs | Compiler PRs |
|---------|-------------|--------|-----------|-------------|
| 1.13 | 2025-10-28 | `abd8457` | 1,274 | 269 |
