# PR Analysis Guide

How to write useful compiler PR analyses for downstream package maintainers.

## Audience

People who maintain packages that depend on Julia compiler internals: JET.jl, Mooncake.jl, Enzyme.jl, GPUCompiler.jl, Diffractor.jl, and similar tools. They need to know:

1. **Will my code break?** — struct fields moved, constructors changed, functions removed
2. **Will my code behave differently?** — inference returns different types, optimization produces different IR
3. **Do I need to handle something new?** — new node types, new lattice elements, new flags

They do NOT need: performance estimates, risk rationale, reviewer commentary, or restatements of the PR description.

## Output Format

Write markdown to `analyses/{version}/pr_{number}.md`:

```markdown
# PR #{number}: {title}

**Author:** {name} ({github}) | **Merged:** {date} | **Risk:** low|medium|high

{1-3 sentence summary. What changed and why it matters.}

## Changes

{Actual code with file:line references. Show old vs new for struct/signature changes.}

## Breaking for downstream tools

{Concrete list of what breaks: struct fields, constructor signatures, removed functions.
Write "None" if nothing breaks.}

## Behavioral differences

{What infers differently, what optimizes differently, what IR looks different.
Write "None" if behavior is unchanged.}
```

Target length: 20-80 lines. A 3-line bugfix should be ~25 lines. A major refactor touching 13 files might be ~80 lines.

## Analytical Process

### Step 1: Gather data

```bash
# Get the diff
git log --oneline --grep="#{PR_NUMBER}" julia/
git show {COMMIT} --stat
git diff {COMMIT}^..{COMMIT}

# Get PR metadata
gh pr view {PR_NUMBER} --repo JuliaLang/julia --json title,body,author,mergedAt,labels
```

### Step 2: Classify the change

Before writing anything, decide what kind of change this is:

| Type | What to focus on | Example |
|------|-----------------|---------|
| **Struct change** | Field additions/removals/reordering, constructor signature changes | PR #55601: VarState gains `ssadef` field |
| **Function signature change** | New/removed parameters, callers that need updating | PR #55601: `smerge` gains `join_pc` param |
| **Behavioral fix** | What was wrong, what's now different, test cases | PR #57275: `isTypeDataType` was unsound for Tuple{Any} |
| **Optimization improvement** | What now optimizes better, IR shape changes | PR #58371: mutable consts now propagate |
| **New feature/API** | New types, new functions, new capabilities | New lattice element, new IR node |
| **Refactor** | What moved where, what was renamed | Often low-risk, but check for removed exports |
| **Codegen/LLVM** | ABI changes, calling convention, GC interaction | Usually isolated from inference tools |

Most PRs fit one or two types. The type determines what you focus on.

### Step 3: Identify what matters for downstream tools

This is the core analytical step. Work through this checklist:

**Struct/type changes** (MOST IMPORTANT — these cause immediate breakage):
- Did any struct gain, lose, or reorder fields? (`VarState`, `CodeInfo`, `IRCode`, `InferenceState`, `Conditional`, `MustAlias`, `InferenceResult`, `MethodInstance`, etc.)
- Did any constructor signature change? (new required arguments, removed arguments)
- Were any types/structs removed or renamed?

**Function changes**:
- Were any exported or commonly-used functions removed?
- Did any function signatures change? (new required parameters)
- Were any functions renamed?
- Use `rg 'function_name\('` to find all callers — if callers were updated in the PR, downstream callers need updating too.

**Lattice/inference changes**:
- Does inference return different types for any expressions?
- Are there new lattice elements that downstream abstract interpreters need to handle?
- Did `tfunc` behavior change for any builtins?
- Did conditional/alias tracking change?

**IR/optimization changes**:
- Does the optimizer produce different IR shapes?
- Are there new IR node types?
- Did inlining heuristics change?
- Did effect analysis change? (nothrow, noub, consistent, etc.)

**What to skip**:
- Test-only changes (unless they illustrate a behavioral difference worth noting)
- Comment/documentation changes
- Performance improvements with no API/behavioral change (just note "performance improvement" in summary)
- Changes to files outside the compiler pipeline (stdlib, docs, CI)

### Step 4: Read context, not just diff

The diff shows WHAT changed. To understand WHY it matters, you need context:

- **Read the struct definition**, not just the changed lines — field ordering matters for downstream code that destructures or accesses by position
- **Read the function around the change** — a one-line change in a 200-line function might only affect one code path
- **Read callers** — `rg 'function_name\b' Compiler/src/` shows who depends on the modified function. If the PR updated 5 callers, downstream tools that also call it need the same update
- **Read the PR body** — authors often explain the "why" and flag known impacts
- **Read test changes** — tests show what the author expects to be different. New test assertions = new behavior. Changed test expectations = changed behavior.

### Step 5: Write the analysis

**Summary**: State what changed and why, in terms a downstream maintainer cares about. Not "refactors the type lattice" but "adds `ssadef` field to `VarState`, `Conditional`, and `MustAlias` to track reaching definitions."

**Changes section**: Show code. For struct changes, show old vs new. For function changes, show the signature diff. Always include `file:line`. Don't describe code — show it.

```markdown
## Changes

`Compiler/src/types.jl:73` — `VarState` gains `ssadef` field:
```julia
# Old:
VarState(@nospecialize(typ), undef::Bool)
# New:
VarState(@nospecialize(typ), ssadef::Int, undef::Bool)
```
```

**Breaking section**: Be specific. Not "struct changed" but:
- `VarState` constructor now requires `ssadef::Int` as second argument
- `Conditional` constructor now requires `ssadef::Int` after `slot::Int`
- `invalidate_slotwrapper` removed — use `conditional_valid()` instead

**Behavioral section**: Only if user-observable or inference-observable. "Inference now returns `Int` instead of `Union{Int, Float64}` for X pattern." Show a concrete example if possible.

## Risk Levels

- **low**: Pure bugfix with no API changes. Internal refactor that doesn't change any signatures or behavior. Codegen-only changes isolated from inference.
- **medium**: Struct field changes, function signature changes, behavioral changes in inference/optimization. Things that WILL break downstream code that touches these internals.
- **high**: Fundamental changes to the type lattice, IR representation, or compilation pipeline. Changes that affect many callers or change widely-used interfaces.

## Common Mistakes

1. **Describing code instead of showing it.** "The function was modified to handle the new case" — show the actual before/after.

2. **Padding with boilerplate.** No "risk rationale", "recommendations", "reviewer notes", "summary of discussion". Just: what changed, what breaks, what's different.

3. **Treating all changes equally.** A 13-file PR might have 1 important struct change and 12 files of mechanical updates to callers. Focus on the struct change. Mention the caller updates briefly.

4. **Missing removed functions/constructors.** Deletions are the hardest to grep for after the fact. Always note what was REMOVED — these cause immediate compilation errors downstream.

5. **Forgetting field ordering.** Julia structs are positional. Adding a field in the middle breaks `new()` calls that use positional arguments, even if the field names didn't change.

6. **Over-analyzing trivial PRs.** A one-line typo fix in a comment doesn't need an analysis. A one-line bugfix in `getfield_tfunc` does — because it changes inference behavior. Use judgment.

## Pipeline Stage Reference

When identifying which pipeline stage a PR touches:

```
Source code
  → JuliaSyntax (tokenizer/parser)
  → Macro expansion + hygiene
  → Lowering + desugaring + scope analysis
  → Closure conversion + linearization → CodeInfo
  → Abstract interpretation + type inference    ← most analyses live here
  → Effects + escape analysis
  → Inlining + optimization passes
  → Codegen / LLVM pipeline
  → Interpreter fallback
```

Key source directories:
- `Compiler/src/abstractinterpretation.jl` — inference main loop
- `Compiler/src/typelattice.jl` — lattice types (Conditional, MustAlias, PartialStruct, etc.)
- `Compiler/src/tfuncs.jl` — builtin type functions (getfield_tfunc, etc.)
- `Compiler/src/types.jl` — core types (VarState, InferenceState, etc.)
- `Compiler/src/ssair/` — SSA IR construction and manipulation
- `Compiler/src/optimize.jl` — optimization entry point
- `Compiler/src/ssair/passes.jl` — optimization passes (SROA, etc.)
- `Compiler/src/ssair/inlining.jl` — inlining
- `Compiler/src/effectanalysis.jl` — effect inference
- `Compiler/src/stmtinfo.jl` — call info types
- `src/codegen.cpp` — LLVM codegen
- `src/gc*.c` — garbage collector

## Downstream Packages to Consider

When assessing impact, think about what these tools touch:

- **JET.jl**: Custom `AbstractInterpreter`, extends `abstract_call*`, reads `InferenceState`, uses lattice types
- **Mooncake.jl**: Custom compiler pass, reads `IRCode`, uses `OpaqueClosure`, depends on IR shape
- **Enzyme.jl**: LLVM-level AD, depends on codegen output and ABI
- **GPUCompiler.jl**: Custom codegen pipeline, depends on `IRCode` and inference results
- **Diffractor.jl**: Source-level AD, custom abstract interpreter, depends on `IRCode` structure
- **Cthulhu.jl**: Interactive inspection, reads inference results, `CodeInfo`, `IRCode`
