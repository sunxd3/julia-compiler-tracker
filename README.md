# julia-compiler-tracker

Tracks Julia compiler PRs and their downstream impact on packages that depend on compiler internals.

## Contents

- `analyses/`: per-PR analyses by Julia version
- `changelogs/`: version-level compiler change summaries
- `compiler-deep-dive/`: reference material on compiler internals
- `.agents/skills/` and `.claude/skills/`: `julia-migration` skill definitions

## Workflow

Use a separate `julia/` checkout to inspect a PR, then write the result to `analyses/{version}/pr_{number}.md`.

See `AGENTS.md` and `ANALYSIS_GUIDE.md` for the analysis process and output format.
