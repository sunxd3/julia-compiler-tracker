# Compiler Change: Julia 1.12 -> 1.13

Goal: collect every PR and commit that affects the Julia compiler between the 1.12 and 1.13 releases, then summarize and categorize them for analysis.

## Planned steps (high-level)
- identify the release tag/branch boundaries
- enumerate PRs and commits touching compiler-related paths
- export results into structured data for review

## Prototype data collection

The current workflow expects a local Julia checkout. The script filters commits by compiler-related paths and outputs JSON or CSV.

```bash
uv run python scripts/collect_compiler_changes.py \
  --repo /path/to/julia \
  --start-tag v1.12.0 \
  --end-tag v1.13.0-beta1 \
  --output compiler_changes.json
```

By default, the script considers the following paths compiler-related:

```
src/
compiler/
base/compiler/
base/inference/
base/ircode/
base/ast/
base/optimizer/
```

Override the list with `--paths` to refine the scope.

## Latest output

`compiler_changes.json` contains the current list of compiler-related commits for
`v1.12.0..v1.13.0-beta1`, generated with the command above.
