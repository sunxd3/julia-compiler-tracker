# Missing v1.12 Compiler PRs

PRs identified as missing from the v1.12 analysis coverage.
Branch date: **2025-02-04** (PRs merged before this date are v1.12)

## Major Restructuring/Infrastructure

| PR | Title | Merged |
|---|---|---|
| 54894 | Add `edges` vector to CodeInstance/CodeInfo to keep backedges as edges | 2024-11-01 |
| 55575 | Change compiler to be stackless | 2024-10-01 |
| 56299 | Teach compiler about partitioned bindings | 2024-11-02 |

## Inference Improvements

| PR | Title | Merged |
|---|---|---|
| 55081 | Add missing setting of inferred field when setting inference result | 2024-07-09 |
| 55216 | inference: refine branched `Conditional` types | 2024-07-24 |
| 55229 | inference: backward constraint propagation from call signatures | 2024-07-25 |
| 55271 | inference: Remove special casing for `!` | 2024-08-01 |
| 55289 | Move `typename` and `<:` to Core and have inference check by value | 2024-08-02 |
| 55338 | compiler: apply more accurate effects to return_type_tfunc | 2024-08-10 |
| 55362 | inference: fix missing LimitedAccuracy markers | 2024-08-05 |
| 55364 | inference: represent callers_in_cycle with view slices of a stack | 2024-08-20 |
| 55533 | inference: propagate partially initialized mutable structs more | 2024-08-22 |
| 55884 | inference: add missing `TypeVar` handling for `instanceof_tfunc` | 2024-09-27 |
| 56264 | inference: fix inference error from constructing invalid `TypeVar` | 2024-10-21 |
| 56314 | inference: don't allow `SSAValue`s in assignment lhs | 2024-10-25 |
| 56391 | irinterp: set `IR_FLAG_REFINED` for narrowed `PhiNode`s | 2024-11-01 |
| 56495 | infer_compilation_signatures for more cases | 2024-11-12 |
| 56547 | compiler: fix several more specialization mistake introduced by #40985 | 2024-11-14 |
| 56551 | inference: complete the inference even for recursive cycles | 2024-11-14 |
| 56552 | inference: infer_compilation_signatures for even more cases | 2024-11-14 |
| 56565 | infer more completely everything that the optimizer/codegen requires | 2024-11-15 |
| 56915 | Compiler: fix `tmerge(Const(s), Const(t))` st. `(s !== t) && (s == t)` | 2025-01-05 |
| 57080 | inference: fix lattice for unusual InterConditional return and Const Bool | 2025-01-21 |
| 57088 | inference: ensure inferring reachable code methods | 2025-01-21 |

## Optimizer

| PR | Title | Merged |
|---|---|---|
| 54972 | Inline statically known method errors | 2024-09-17 |
| 55306 | AllocOpt: Fix stack lowering where alloca contains boxed and unboxed data | 2024-08-06 |
| 55796 | A minor improvement for EA-based `:effect_free`-ness refinement | 2024-09-19 |
| 55976 | optimizer: fix up the inlining algorithm to use correct `nargs`/`isva` | 2024-10-03 |
| 56189 | Fix `goto` insertion when dom-sorting IR in `slot2ssa` pass | 2024-10-18 |
| 56686 | optimizer: handle `EnterNode` with `catch_dest == 0` | 2024-11-27 |
| 56737 | effects: pack bits better | 2024-12-04 |
| 57201 | Optimizer: Update SROA def-uses after DCE | 2025-02-03 |

## Other Fixes

| PR | Title | Merged |
|---|---|---|
| 55757 | Fix hang in tmerge_types_slow | 2024-09-16 |
| 56081 | fix `Vararg{T,T} where T` crashing `code_typed` | 2024-10-11 |
| 56598 | fix some new-edges issues | 2024-11-20 |
| 56945 | fix handling of experimental module compile flag | 2025-01-06 |
| 57082 | codegen: use correct rettype ABI for aotcompile | 2025-01-21 |
