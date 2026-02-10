# Current State & Next Steps

## What's been done

1. **PR extraction**: Identified all 1,274 PRs merged between Julia 1.12 and 1.13 branch points using `git log --first-parent` between the two merge-base commits. Validated against GitHub API. Data in `data/v1.13/`.

2. **Compiler PR filtering**: 269 of those PRs touch compiler-related files (Compiler/src, src/codegen, src/gc, etc.). Listed in `data/v1.13/compiler_prs.txt` with format `PR_NUMBER|TITLE`. Note: this filter is conservative — it may miss PRs that affect compiler behavior through non-obvious paths (e.g., `src/builtins.c`, `src/subtype.c`).

3. **Existing analyses**: 67 YAML analyses existed before this work (in `analyses/v1.13/`). Only 11 overlap with the 269 compiler PRs — the other 56 were for PRs the file-path filter missed.

4. **Missing PR tracking**: `analyses/v1.13/missing_prs.md` lists 258 compiler PRs that don't have analyses yet, categorized by pipeline stage (Inference, Optimizer, Lowering, Codegen/LLVM, GC/Runtime, etc.).

5. **New format**: Switched from verbose YAML (100-600 lines each) to concise markdown (20-80 lines). Three sample analyses produced: PRs #55601, #57275, #58371. See `ANALYSIS_GUIDE.md` for the format spec.

6. **Codex pipeline**: Tested using OpenAI Codex CLI (gpt-5.3-codex) for analysis generation. Key finding: **Codex must be given pre-baked data and told not to use tools.** When it has tool access it explores endlessly and never produces output. The working pipeline is:
   - You gather: `git diff`, `gh pr view`, struct/function context via grep
   - Compose a prompt with all data inlined + "Do NOT run any commands"
   - Codex synthesizes the markdown
   - See `/tmp/codex_pure_*.txt` for example prompts (may not persist across sessions)

## What needs to happen next

### Priority 1: Analyze the 258 missing compiler PRs

Work through `analyses/v1.13/missing_prs.md` by category. Suggested order (highest downstream impact first):

1. **Inference** (40 PRs) — most likely to affect JET.jl, type-level tools
2. **Optimizer** (14 PRs) — affects IR shape, impacts Mooncake.jl, Enzyme.jl
3. **IR/Verification** (10 PRs) — affects IRCode structure
4. **Lowering** (23 PRs) — affects CodeInfo shape
5. **Binding Partitions** (19 PRs) — new system, high impact
6. **Codegen/LLVM** (51 PRs) — mostly isolated, lower priority for inference-level tools
7. **GC/Runtime** (28 PRs) — mostly isolated
8. **Compilation Infrastructure** (45 PRs) — caching, loading, mostly internal
9. **Other** (28 PRs) — mixed bag

For each PR:
```bash
# 1. Find the merge commit
git log --oneline --grep="#{PR_NUMBER}" julia/

# 2. Get the diff
git show {COMMIT} --stat
git diff {COMMIT}^..{COMMIT}

# 3. Get metadata
gh pr view {PR_NUMBER} --repo JuliaLang/julia --json title,body,author,mergedAt

# 4. Read struct definitions and callers for context
rg 'modified_function\b' julia/Compiler/src/

# 5. Write analysis to analyses/v1.13/pr_{NUMBER}.md
```

Skip PRs that are purely:
- CI/build system changes
- Comment/doc-only changes
- Test-only changes with no behavioral difference
- Stdlib changes unrelated to compiler

### Priority 2: Convert existing YAMLs to markdown

67 YAML files in `analyses/v1.13/` need conversion. Don't just reformat — re-analyze with the new focus (what breaks, what's different). The existing YAMLs have useful data but are padded with boilerplate.

### Priority 3: Reconcile the 56 "extra" analyzed PRs

56 of the 67 existing YAML analyses are for PRs NOT in the 269 compiler PR list (the file-path filter missed them). These PRs may still be compiler-relevant. Decide whether to:
- Add them to `compiler_prs.txt`
- Or note them as "related but not core compiler"

## Key files

| File | Purpose |
|------|---------|
| `ANALYSIS_GUIDE.md` | How to write analyses (format, process, checklist) |
| `CLAUDE.md` | Agent workflow instructions |
| `analyses/v1.13/missing_prs.md` | Work tracker — 258 PRs by category |
| `data/v1.13/all_prs.txt` | All 1,274 PR numbers (one per line) |
| `data/v1.13/compiler_prs.txt` | 269 compiler PRs as `NUMBER\|TITLE` |
| `julia/` | Full Julia repo clone for reading code |

## Julia repo state

The `julia/` directory is a full clone of JuliaLang/julia. To look at a specific PR's changes:
```bash
cd julia
git log --oneline --grep="#{PR_NUMBER}"   # find merge commit
git diff {COMMIT}^..{COMMIT}               # see the diff
```
