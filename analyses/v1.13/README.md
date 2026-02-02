# Julia 1.13 Compiler PR Analyses

This directory contains detailed YAML analyses of compiler-related PRs that were merged before the Julia 1.13 branch point.

## Branch Information

- **Branch point**: 2025-10-28
- **Branch commit**: `abd8457ca85370eefe3788cfa13a6233773ea16f`
- **Core PRs**: 9

## PR List

| PR | Title | Merged | Component |
|----|-------|--------|-----------|
| [#56201](https://github.com/JuliaLang/julia/pull/56201) | Use stmt instead of `Instruction` in `populate_def_use_map!` | 2025-10-14 | Optimizer |
| [#59165](https://github.com/JuliaLang/julia/pull/59165) | ccall: make distinction of pointer vs name a syntactic distinction | 2025-10-09 | Lowering |
| [#59766](https://github.com/JuliaLang/julia/pull/59766) | Align interpreter and codegen error behavior of setglobal! and friends | 2025-10-08 | Runtime |
| [#59772](https://github.com/JuliaLang/julia/pull/59772) | Avoid method instance normalization for opaque closure methods | 2025-10-07 | Runtime |
| [#59784](https://github.com/JuliaLang/julia/pull/59784) | Make `=` and `const` toplevel-preserving syntax | 2025-10-17 | Lowering |
| [#59785](https://github.com/JuliaLang/julia/pull/59785) | Fix missing GC root | 2025-10-08 | GC |
| [#59888](https://github.com/JuliaLang/julia/pull/59888) | Type-assert `isfinite(::AbstractFloat)` | 2025-10-20 | Inference |
| [#59908](https://github.com/JuliaLang/julia/pull/59908) | absint: allow ad-hoc cancellation of concrete evaluation | 2025-10-20 | Inference |
| [#59921](https://github.com/JuliaLang/julia/pull/59921) | Set types of boxed variables in `abstract_eval_nonlinearized_foreigncall_name` | 2025-10-24 | Inference |

## Key Changes Summary

### Lowering
- **ccall syntax distinction** (PR #59165): Changes IR shape for foreign function calls
- **toplevel-preserving** (PR #59784): `=` and `const` now preserve toplevel context

### Inference
- **def-use map fix** (PR #56201): Correct type refinement propagation through IR cycles
- **type assertions** (PR #59888): Invalidation fix for `isfinite`
- **concrete eval cancellation** (PR #59908): Ad-hoc cancellation support
- **boxed variable types** (PR #59921): Fixed inference for foreign calls

### Runtime/GC
- **error behavior alignment** (PR #59766): Consistent semantics across interpreter/codegen
- **opaque closures** (PR #59772): Skip method instance normalization
- **GC root fix** (PR #59785): Safety fix for `jl_type_error_global`

## Downstream Impact

Tools that may need updates for Julia 1.13:

- **JET.jl**: Improved type inference from def-use fix
- **Mooncake.jl**: Validate type inference behavior

See [`../../changelogs/v1.13-compiler-changelog.md`](../../changelogs/v1.13-compiler-changelog.md) for full changelog.
