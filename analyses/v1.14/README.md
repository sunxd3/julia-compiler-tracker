# Julia 1.14 Compiler PR Analyses

This directory contains detailed YAML analyses of compiler-related PRs merged to master after the Julia 1.13 branch point, targeting Julia 1.14.

## Branch Information

- **Status**: Development branch (not yet released)
- **Base**: master branch after 1.13 branch point (2025-10-28)
- **Core PRs**: 26

## PR List

| PR | Title | Merged | Component |
|----|-------|--------|-----------|
| [#55601](https://github.com/JuliaLang/julia/pull/55601) | inference: track reaching defs for slots | 2025-12-30 | Inference |
| [#59413](https://github.com/JuliaLang/julia/pull/59413) | inference: reinfer and track missing code for inlining | 2025-11-10 | Inference |
| [#59870](https://github.com/JuliaLang/julia/pull/59870) | Move JuliaSyntax + JuliaLowering into the main tree | 2025-11-14 | Frontend |
| [#59974](https://github.com/JuliaLang/julia/pull/59974) | inference: revisit all methods in cycle | 2025-11-01 | Inference |
| [#60011](https://github.com/JuliaLang/julia/pull/60011) | fix `pointerarith_tfunc` for Const ptr | 2025-11-01 | Inference |
| [#60018](https://github.com/JuliaLang/julia/pull/60018) | Provide mechanism for Julia syntax evolution | 2025-11-25 | Frontend |
| [#60079](https://github.com/JuliaLang/julia/pull/60079) | disable compiling for typeinf world during incremental compile | 2025-11-09 | Compilation |
| [#60093](https://github.com/JuliaLang/julia/pull/60093) | aotcompile: implement build healing | 2025-11-13 | Compilation |
| [#60105](https://github.com/JuliaLang/julia/pull/60105) | Add JLJITLinkMemoryManager (ports memory manager to JITLink) | 2025-11-13 | Codegen |
| [#60140](https://github.com/JuliaLang/julia/pull/60140) | [JuliaLowering] Fix placeholders in parameters and decls | 2025-11-18 | Lowering |
| [#60214](https://github.com/JuliaLang/julia/pull/60214) | inference: fix the ptrfree field check | 2025-11-24 | Inference |
| [#60257](https://github.com/JuliaLang/julia/pull/60257) | [JuliaLowering] `ccall((lib,sym)...)` and `cfunction` fixes | 2025-12-01 | Lowering |
| [#60311](https://github.com/JuliaLang/julia/pull/60311) | threads: Implement asymmetric atomic fences | 2025-12-15 | Threading |
| [#60316](https://github.com/JuliaLang/julia/pull/60316) | [JuliaLowering] Refactor scope resolution pass | 2025-12-11 | Lowering |
| [#60353](https://github.com/JuliaLang/julia/pull/60353) | codegen load/store/union cleanup and fix | 2025-12-11 | Codegen |
| [#60388](https://github.com/JuliaLang/julia/pull/60388) | codegen: improve size layout for on-stack pointer-ful types | 2025-12-17 | Codegen |
| [#60410](https://github.com/JuliaLang/julia/pull/60410) | [JuliaLowering] Add support for `Expr(:loopinfo, ...)` | 2025-12-18 | Lowering |
| [#60416](https://github.com/JuliaLang/julia/pull/60416) | lowering: Fix `@nospecialize` on unnamed arguments | 2026-01-07 | Lowering |
| [#60517](https://github.com/JuliaLang/julia/pull/60517) | Remove `jl_gc_external_obj_hdr_size` | 2026-01-03 | GC |
| [#60551](https://github.com/JuliaLang/julia/pull/60551) | [JuliaLowering] Add remap for assigned-to arguments | 2026-01-07 | Lowering |
| [#60567](https://github.com/JuliaLang/julia/pull/60567) | [JuliaLowering] Implement flisp-compatible Box optimization | 2026-01-10 | Lowering |
| [#60576](https://github.com/JuliaLang/julia/pull/60576) | Enable JITLink everywhere | 2026-01-12 | Codegen |
| [#60577](https://github.com/JuliaLang/julia/pull/60577) | [JuliaLowering] Enrich closure tests and fix static parameter capture | 2026-01-12 | Lowering |
| [#60597](https://github.com/JuliaLang/julia/pull/60597) | flisp: Port closure box optimization fixes from JuliaLowering.jl | 2026-01-09 | Lowering |
| [#60619](https://github.com/JuliaLang/julia/pull/60619) | [JuliaLowering] Fix-up handling of `stmt_offset` in `K"enter"` | 2026-01-09 | Lowering |
| [#60646](https://github.com/JuliaLang/julia/pull/60646) | [JuliaLowering] Avoid analyzing variables 'owned' by outer closures | 2026-01-12 | Lowering |

## Key Changes Summary

### Frontend (JuliaSyntax/JuliaLowering)
- **In-tree integration** (PR #59870): JuliaSyntax and JuliaLowering vendored as top-level packages
- **Syntax evolution** (PR #60018): Mechanism for versioned parsing behavior
- **Box optimization** (PR #60567): Single-assigned captured variables avoid `Core.Box` allocations
- Multiple JuliaLowering fixes for ccall, closures, scope resolution

### Type Inference
- **Reaching definitions** (PR #55601): `VarState`, `Conditional`, and `MustAlias` carry `ssadef` field
- **Cycle handling** (PR #59974): Proper revisitation of methods in recursive cycles
- **Inlining** (PR #59413): Reinfer and track missing code for inlining decisions

### Codegen/Backend
- **JITLink everywhere** (PR #60576): Default memory manager on all platforms
- **Union codegen cleanup** (PR #60353): New `StoreKind` enum, shared helpers for TBAA
- **JITLink memory manager** (PR #60105): `JLJITLinkMemoryManager` introduction

### Threading
- **Asymmetric fences** (PR #60311): New `Threads.atomic_fence_light()` and `Threads.atomic_fence_heavy()` APIs

### GC
- **API removal** (PR #60517): `jl_gc_external_obj_hdr_size()` removed from GC extensions API

## Breaking Changes

1. **GC Extensions API**: `jl_gc_external_obj_hdr_size()` removed (PR #60517)
2. **atomic_fence arity**: `Core.Intrinsics.atomic_fence` requires syncscope argument (PR #60311)

## Downstream Impact

Tools that need updates for Julia 1.14:

### High Priority
- **Enzyme.jl, GPUCompiler**: Verify JITLink compatibility and union codegen changes
- **JET.jl**: Update for reduced Box allocations and new IR patterns from JuliaLowering
- **Mooncake.jl**: Review changes to Conditional/MustAlias construction (ssadef field)

### Medium Priority
- **C extensions using GC API**: Update for `jl_gc_external_obj_hdr_size` removal
- **Tools using atomic_fence**: Add syncscope argument

See [`../../changelogs/v1.14-compiler-changelog.md`](../../changelogs/v1.14-compiler-changelog.md) for full changelog.
