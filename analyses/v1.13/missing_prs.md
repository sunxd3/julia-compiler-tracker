# Missing v1.13 Compiler PRs

PRs identified as missing from the v1.13 analysis coverage.
Branch date: **2025-02-04** (PRs merged on or after this date are v1.13)

## Inference Improvements

| PR | Title | Merged |
|---|---|---|
| 57222 | Inference: propagate struct initialization info on `setfield!` | 2025-02-08 |
| 57248 | improve concurrency safety for `Compiler.finish!` | 2025-02-08 |
| 57275 | Compiler: fix unsoundness of getfield_tfunc on Tuple Types | 2025-02-13 |
| 57293 | Fix getfield_tfunc when order or boundscheck is Vararg | 2025-02-10 |
| 57541 | inference: allow `PartialStruct` to represent strict undef field | 2025-03-02 |
| 57545 | [Compiler] fix some cycle_fix_limited usage | 2025-02-27 |
| 57553 | Compiler: avoid type instability in access to `PartialStruct` field | 2025-02-28 |
| 57582 | Compiler: abstract calls: type assert to help stability | 2025-03-12 |
| 57684 | Compiler: `abstract_apply`: declare type of two closure captures | 2025-03-10 |
| 57878 | inference: add internal SOURCE_MODE_GET_SOURCE mode | 2025-03-28 |

## Optimizer

| PR | Title | Merged |
|---|---|---|
| 57074 | [internals] add time metrics for every CodeInstance | 2025-03-17 |
