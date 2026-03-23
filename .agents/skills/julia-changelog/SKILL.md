---
name: julia-changelog
description: Generate and update compiler changelogs for Julia releases by scanning merged PRs in the Julia repo. Use when the user asks to build, update, or extend a compiler changelog for a Julia version.
---

# Julia Compiler Changelog Generator

Generate compiler-focused changelogs for Julia releases by scanning merged PRs in the JuliaLang/julia repo.

## Output format

Follow the style of the official Julia NEWS.md (`https://github.com/JuliaLang/julia/blob/master/NEWS.md`):

- Title: `# Julia vX.Y Compiler Release Notes`
- Sections with `##` for major areas (see categories below)
- Each item is a `*` bullet, 1-3 sentences, ending with `([#NNNNN])`
- Link reference definitions at the bottom: `[#NNNNN]: https://github.com/JuliaLang/julia/issues/NNNNN`
- No per-PR sub-headings — bullets only
- Tone is factual and concise: what changed and why it matters to downstream tooling

See `changelogs/v1.13/compiler-changelog.md` for a worked example.

## Section categories

Use these `##` sections, dropping any that have no entries:

1. **Frontend and Lowering** — parser, lowering, syntax changes, binding semantics
2. **Type Inference and Effects** — abstract interpretation, lattice, tfuncs, effect modeling, invalidation
3. **Custom Interpreters and Tooling Extensions** — `AbstractInterpreter` hooks, JIT integration, reflection
4. **Dispatch and Compiler Infrastructure** — method tables, dispatch metadata, compilation lifecycle
5. **Optimizer and IR** — SSA IR, inlining, SROA, ADCE, CFG invariants
6. **Codegen and LLVM** — LLVM version bumps, codegen changes, ABI
7. **Runtime and GC** — GC roots, runtime builtins, interpreter/codegen consistency

## How to find compiler PRs

### Using the GitHub API (preferred for scanning)

```bash
# Find the branch point for a release
git -C /path/to/julia merge-base origin/master origin/release-X.Y

# List first-parent merges since branch point
git -C /path/to/julia log --first-parent --oneline <branch-point>..origin/release-X.Y
```

Extract only the trailing `(#NNNNN)` from each commit subject. Do **not** scrape every `#12345` mention — revert titles, issue refs, and cross-repo references leak bogus numbers.

### Using `gh` CLI

```bash
# Get PR details
gh pr view NNNNN --repo JuliaLang/julia --json title,body,labels,files

# Search for compiler PRs by label
gh pr list --repo JuliaLang/julia --label "compiler" --state merged --limit 100
```

### Filtering for compiler relevance

A PR is compiler-relevant if it touches files in these areas:

**Compiler package** (1.12+; was `base/compiler/` before 1.12):
- `Compiler/src/` — inference, optimization, effects, escape analysis
- `Compiler/src/ssair/` — SSA IR, domtree, inlining, optimization passes
- `Compiler/test/`

**LLVM codegen and JIT**:
- `src/codegen.cpp`, `src/aotcompile.cpp` — main codegen
- `src/jitlayers.cpp`, `src/engine.cpp`, `src/pipeline.cpp` — JIT pipeline
- `src/cgutils.cpp`, `src/cgmemmgr.cpp` — codegen utilities
- `src/ccall.cpp` — foreign call codegen
- `src/intrinsics.cpp`, `src/intrinsics.h` — LLVM intrinsic lowering
- `src/debuginfo.cpp`, `src/disasm.cpp` — debug info and disassembly
- `src/llvm-*.cpp` — custom LLVM passes (GC lowering, alloc-opt, multiversioning, etc.)

**Type system and dispatch**:
- `src/subtype.c` — subtype algorithm
- `src/gf.c` — generic function dispatch
- `src/typemap.c` — method table lookup
- `src/datatype.c` — datatype construction
- `src/method.c` — method objects

**Lowering and parsing**:
- `src/flisp/` — flisp interpreter (lowering engine)
- `src/julia-syntax.scm`, `src/julia-parser.scm`, `src/macroexpand.scm`, `src/jlfrontend.scm` — Scheme lowering passes
- `src/ast.c` — AST construction
- `JuliaSyntax/` — Julia-native parser
- `JuliaLowering/` — Julia-native lowering (in-tree, not default)

**Runtime, GC, and interpreter**:
- `src/gc-*.c`, `src/gc-*.h` — GC (stock, MMTk, interface)
- `src/interpreter.c` — interpreter
- `src/builtins.c` — builtin functions
- `src/runtime_intrinsics.c` — runtime intrinsic implementations
- `src/toplevel.c` — top-level evaluation
- `src/module.c` — module management
- `src/opaque_closure.c` — opaque closures
- `src/safepoint.c` — GC safepoints

**Serialization and precompilation**:
- `src/staticdata.c`, `src/staticdata_utils.c` — sysimage serialization
- `src/ircode.c` — IR serialization
- `src/precompile.c`, `src/precompile_utils.c`

**Base compiler-facing files**:
- `base/boot.jl`, `base/essentials.jl` — core type definitions
- `base/expr.jl`, `base/meta.jl` — expression and macro utilities
- `base/reflection.jl`, `base/coreir.jl` — reflection and Core IR
- `base/opaque_closure.jl`, `base/runtime_internals.jl`
- `base/loading.jl` — package loading / precompilation

**Tests** (when they reveal semantic shifts):
- `test/compiler/`, `test/llvmpasses/`, `test/gc/`, `test/gcext/`
- `test/subtype.jl`, `test/intrinsics.jl`, `test/opaque_closure.jl`, `test/precompile.jl`

Skip PRs that are pure docs, CI, test-only with no semantic change, or stdlib-only.

## Writing good entries

- Lead with what changed, not the PR title
- Include downstream impact: what breaks, what tools need to update
- For representation changes (IR, lattice, lowered forms), name the old and new shapes
- For soundness fixes, say what was unsound
- For extension-point changes, name the affected hooks/types
- Keep each bullet self-contained — a reader should not need to read other bullets to understand it

## Gotchas

- PR numbers reflect when a PR was *opened*, not when it merged. Old PR numbers can land in late release cycles.
- Use branch-point commits, not calendar dates, to decide version boundaries.
- The `Compiler/` package lives at the repo root since Julia 1.12 (PR #56409). Before that it was `base/compiler/`.
