---
name: julia-migration
description: Help developers of Julia compiler-dependent packages migrate between Julia versions. Use when the user asks about Julia version migration, breaking compiler changes, or what changed in a specific Julia PR affecting compiler internals.
---

# Julia Compiler Migration Assistant

Help maintainers of compiler-dependent Julia packages understand what breaks between versions and what to change.

## Julia-specific gotcha

Julia structs are positional. Field *reordering* is the silent footgun — `new()` calls compile fine but put wrong data in wrong fields. Field addition/removal usually changes arity and fails loudly, but reordering doesn't. Always diff struct field order when a struct changes.

## Compiler source layout across versions

The compiler source has been reorganized several times. When investigating changes between versions, be aware that paths have moved.

| Date | First in | Change |
|------|----------|--------|
| Jan 2018 | 0.7 | `base/compiler/` created — inference refactored from single file into modules (PR #25517) |
| Feb 2018 | 0.7 | `base/compiler/ssair/` added — SSA IR pipeline (PR #26079) |
| Jun 2023 | 1.10 | JuliaSyntax added as external dependency, enabled as default parser (PR #46372) |
| Jul 2024 | 1.12 | GC modularized: `src/gc.c` → `src/gc-stock.c`, pluggable `src/gc-interface.h` (PR #55256) |
| Nov 2024 | 1.12 | `Compiler/` becomes independent package at repo root — `base/compiler/` deleted (PR #56409). **1.11 uses `base/compiler/`, 1.12+ uses `Compiler/`** |
| Jan 2025 | 1.12 | MMTk GC backend: `src/gc-mmtk.c` (PR #56288) |
| Nov 2025 | unreleased | JuliaSyntax + JuliaLowering moved into top-level directories as in-tree source (PR #59870) |

### Current layout (as of ~1.14-dev)

| Directory | Contents |
|-----------|----------|
| `Compiler/src/` | Type inference, optimization, effects, escape analysis, SSA IR |
| `Compiler/src/ssair/` | IR representation, domtree, inlining, optimization passes |
| `JuliaSyntax/` | Tokenizer, parser, green tree, syntax nodes |
| `JuliaLowering/` | Desugaring, scope analysis, macro expansion, closure conversion (in-tree but **not active by default** — requires explicit opt-in) |
| `src/flisp/` | Default parser and lowering (flisp-based, also used for bootstrap) |
| `src/codegen.cpp`, `src/aotcompile.cpp` | LLVM code generation (C++) |
| `src/gc-*.{c,h}` | Modular GC: `gc-stock.*` (default), `gc-mmtk.*`, `gc-interface.h` |

### Pipeline

```
Source -> JuliaSyntax parser -> flisp lowering (default) -> CodeInfo
  -> Type Inference (Compiler/src/abstractinterpretation.jl)
  -> Optimizer (Compiler/src/optimize.jl):
     CONVERT -> SLOT2REG -> COMPACT -> INLINING -> COMPACT -> SROA -> ADCE
  -> LLVM Codegen (src/codegen.cpp)
```

Note: JuliaLowering can replace flisp lowering but is not active by default.

## Compiler internals reference

For detailed struct definitions, lattice types, IR flags, and source file locations, read [references/compiler-internals.md](references/compiler-internals.md).
