---
name: julia-migration
description: Help developers of Julia compiler-dependent packages (JET.jl, Mooncake.jl, Enzyme.jl, GPUCompiler.jl, Diffractor.jl, Cthulhu.jl) migrate between Julia versions. Use when the user asks about Julia version migration, breaking compiler changes, or what changed in a specific Julia PR affecting compiler internals. Also use when analyzing a Julia compiler PR for downstream impact.
---

# Julia Compiler Migration Assistant

Help maintainers of compiler-dependent Julia packages understand what breaks between versions and what to change.

## Audience

Maintainers of packages that use Julia compiler internals: JET.jl, Mooncake.jl, Enzyme.jl, GPUCompiler.jl, Diffractor.jl, Cthulhu.jl, and similar tools.

They need to know:
1. **Will my code break?** — struct fields moved, constructors changed, functions removed
2. **Will behavior differ?** — inference returns different types, optimization produces different IR
3. **Do I need to handle something new?** — new node types, new lattice elements, new flags

They do NOT need: performance estimates, risk rationale, reviewer commentary, or restatements of PR descriptions.

## What Each Package Touches

| Package | Compiler surfaces used |
|---------|----------------------|
| **JET.jl** | Custom `AbstractInterpreter`, extends `abstract_call*`, reads `InferenceState`, uses lattice types |
| **Mooncake.jl** | Custom compiler pass, reads `IRCode`, uses `OpaqueClosure`, depends on IR shape |
| **Enzyme.jl** | LLVM-level AD, depends on codegen output and ABI |
| **GPUCompiler.jl** | Custom codegen pipeline, depends on `IRCode` and inference results |
| **Diffractor.jl** | Source-level AD, custom abstract interpreter, depends on `IRCode` structure |
| **Cthulhu.jl** | Interactive inspection, reads inference results, `CodeInfo`, `IRCode` |

## Workflow

### Migration guide (primary)

When a user asks "what breaks for my package between Julia X and Y":

1. **Identify the package's compiler surface** from the table above (or ask the user what internals they use)
2. **Get the Julia repo**. If `julia/` exists in the working directory, use it. Otherwise:
   ```bash
   git clone --bare https://github.com/JuliaLang/julia.git julia/.git
   cd julia && git config core.bare false && git checkout master
   ```
3. **Find PRs between versions** (see "Finding PRs Between Versions" below)
4. **Diff the compiler-relevant directories** between versions:
   ```bash
   git diff v{OLD}..v{NEW} -- Compiler/src/ src/codegen.cpp src/gc*.c src/subtype.c src/builtins.c
   ```
5. **Focus on the package's surface** — filter changes to structs, functions, and behaviors the package actually uses
6. **Trace breaking changes**: for each struct/function change, use `rg` to find all callers and check if the package would need updating
7. **Produce a migration guide** (see Output Format below)

### Finding PRs between versions

Julia minor versions fork from `master` at a specific date. To find all PRs merged between two versions:

```bash
# 1. Find the fork points (merge-base of release branch and master)
git merge-base origin/master origin/release-1.12   # -> commit A
git merge-base origin/master origin/release-1.13   # -> commit B

# 2. List all merge commits (PRs) between those fork points
git log --first-parent --oneline A..B

# 3. Filter for compiler-relevant PRs by checking which files each touched
git log --first-parent --oneline A..B -- \
  Compiler/src/ src/codegen.cpp src/cgutils.cpp src/intrinsics.cpp \
  src/gc*.c src/subtype.c src/builtins.c src/jitlayers.cpp src/aotcompile.cpp
```

**Note**: The file-path filter is conservative — it may miss PRs that affect compiler behavior through non-obvious paths (e.g., changes to `base/boot.jl` that alter type definitions, or `src/method.c` that changes dispatch). When in doubt, also check:
- `src/method.c`, `src/gf.c` (dispatch, specialization)
- `base/boot.jl`, `base/essentials.jl` (core type definitions)
- `Compiler/test/` (test changes often reveal behavioral shifts)

### PR analysis (secondary)

When a user asks about a specific PR:

1. **Fetch PR metadata**:
   ```bash
   gh pr view {NUMBER} --repo JuliaLang/julia --json title,body,author,mergedAt,labels,files
   ```
2. **Get the diff**:
   ```bash
   cd julia && git fetch origin pull/{NUMBER}/merge:pr-{NUMBER} && git checkout pr-{NUMBER}
   git diff HEAD^..HEAD
   ```
3. **Read full file context** around each change — not just the diff
4. **Trace call chains** with `rg`:
   - Upstream: who calls the modified functions?
   - Downstream: what does the modified code call?
5. **Classify the change** and assess downstream impact

## What to Focus On (in priority order)

**Struct/type changes** (cause immediate breakage):
- Fields gained, lost, or reordered (Julia structs are positional — adding a field in the middle breaks all `new()` calls)
- Constructor signature changes
- Types removed or renamed

**Function changes**:
- Removed or renamed functions
- Changed signatures (new required parameters)
- Use `rg 'function_name\('` to find all callers — if the PR updated N callers, downstream callers need the same update

**Lattice/inference changes**:
- New lattice elements downstream abstract interpreters must handle
- Changed `tfunc` behavior for builtins
- Different inference results for the same code

**IR/optimization changes**:
- New IR node types
- Changed IR shapes (fewer/more `getfield` nodes, different inlining)
- Changed effect flags or escape analysis results

**What to skip**:
- Test-only, comment-only, doc-only changes
- Performance improvements with no API/behavioral change
- CI/build system changes
- Stdlib changes unrelated to compiler

## Output Format

### Migration guide

```markdown
# Julia {OLD} -> {NEW} Migration Guide for {Package}

## Breaking changes (must fix)

### {Change title}
{1-2 sentences: what changed and why}

```julia
# Old (Julia {OLD}):
...
# New (Julia {NEW}):
...
```

**What to change in {Package}:** {concrete instructions}

## Behavioral differences (may affect correctness)

### {Change title}
{What infers/optimizes differently, with concrete example}

## New capabilities (optional adoption)

### {Change title}
{What's now possible}
```

### PR analysis

```markdown
# PR #{number}: {title}

**Author:** {name} | **Merged:** {date} | **Risk:** low|medium|high

{1-3 sentence summary}

## Changes
{Code with file:line references. Old vs new for struct/signature changes.}

## Breaking for downstream tools
{Concrete list, or "None"}

## Behavioral differences
{What infers/optimizes differently, or "None"}
```

## Compiler Pipeline Reference

For detailed compiler internals (subsystems, key structs, source file locations), read [references/compiler-internals.md](references/compiler-internals.md).

```
Source -> Lowering (ast.c) -> CodeInfo
  -> Type Inference (abstractinterpretation.jl, typeinfer.jl)
  -> SSA Construction (slot2ssa.jl) -> IRCode
  -> Optimization: INLINING -> SROA -> ADCE
  -> LLVM Codegen (codegen.cpp)
```

## Common Mistakes

- **Describing code instead of showing it.** Show before/after, not "the function was modified."
- **Missing removals.** Deletions cause immediate errors downstream and are hardest to grep for after the fact.
- **Forgetting field ordering.** Julia structs are positional. Reordering fields breaks positional constructors silently.
- **Treating all changes equally.** A 13-file PR might have 1 important struct change and 12 mechanical caller updates. Focus on the struct change.
- **Over-analyzing trivial PRs.** A comment typo fix doesn't need analysis. A one-line `getfield_tfunc` fix does.
