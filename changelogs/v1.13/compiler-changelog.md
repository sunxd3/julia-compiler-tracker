# Julia 1.13 Compiler Changes

*Summary of compiler changes from Julia 1.12 to 1.13*

*Branch point: 2025-10-28, commit `abd8457ca85370eefe3788cfa13a6233773ea16f`*

For a longer high-level pass over selected impactful PRs, see [impactful-prs.md](impactful-prs.md).

---

## Frontend and Lowering

### Binding Partitions Fully Switch to Partitioned Semantics (PR #57253)

Binding partitions now define module/global binding semantics directly, removing timing-dependent "resolvedness" behavior and making weak-vs-strong global handling more predictable.

### ccall Syntax Distinction (PR #59165)

The distinction between pointer and name in `ccall` is now a syntactic distinction via tuple syntax, changing the lowering and IR shape for foreign function calls.

### Make `=` and `const` Toplevel-Preserving (PR #59784)

Assignment and const declarations are now toplevel-preserving syntax, fixing closure conversion behavior for certain edge cases.

---

## Type Inference

### Use stmt instead of Instruction in def-use map (PR #56201)

Fixed def-use map population by passing the statement (not Instruction wrapper) to `userefs()`, preventing early scan exits that left def-use counts incomplete. This ensures correct type refinement propagation in the IR interpreter.

### Type-assert `isfinite(::AbstractFloat)` (PR #59888)

Type assertion added to `isfinite(::AbstractFloat)` to fix inference invalidation issues.

### Concrete Evaluation Cancellation (PR #59908)

Abstract interpreter now allows ad-hoc cancellation of concrete evaluation, improving handling of long-running or problematic concrete evaluations.

### Set Types of Boxed Variables in Foreign Calls (PR #59921)

Fixed type setting for boxed variables in `abstract_eval_nonlinearized_foreigncall_name`, improving inference correctness for foreign function calls.

### Prevent a Class of Recursive Inference Hangs (PR #58273)

Inference now avoids caching certain `LimitedAccuracy` intermediates that could recursively trigger more compilation work, fixing a real non-termination class rather than just improving precision.

---

## Dispatch and Compiler Infrastructure

### One Global MethodTable Representation (PR #58131)

Method lookup now centers on one global `MethodTable` plus explicit external-table membership, changing how compiler internals and reflection reason about method ownership.

---

## Codegen and LLVM

### LLVM 20 Toolchain Bump (PR #58142)

Julia 1.13 moves the backend toolchain to LLVM 20, a cycle-level compiler/backend transition that downstream LLVM-facing tooling will notice even when no single frontend behavior changed.

---

## Runtime and GC

### Align Interpreter and Codegen Error Behavior (PR #59766)

Aligned interpreter and codegen error behavior for `setglobal!` and related functions, ensuring consistent semantics across execution modes.

### Avoid Method Instance Normalization for Opaque Closures (PR #59772)

Skips method instance normalization for opaque closure methods, improving runtime correctness for opaque closures.

### Fix Missing GC Root (PR #59785)

Fixed a missing GC root in `jl_type_error_global`. The function now protects `JL_MAYBE_UNROOTED` arguments with `JL_GC_PUSH2` before calling allocation functions. Also corrects `jl_module_globalref` annotation from `JL_GLOBALLY_ROOTED` to `JL_PROPAGATES_ROOT`.

---

## Impact on Downstream Tools

### High Impact

1. **Binding-partition semantics** (PR #57253): Tools that reason about global bindings, imports, or world-age-sensitive module behavior should re-check those assumptions.

2. **Method table representation** (PR #58131): Reflection and compiler-internal tooling should not assume method ownership is inferred from fragmented per-`TypeName` tables.

### Medium Impact

1. **ccall IR shape changes** (PR #59165): Tools processing `ccall` lowered IR may need updates.

2. **Inference robustness** (PRs #56201, #58273): Type refinement works correctly through cycles, and one recursive non-termination class is removed.

3. **LLVM 20 transition** (PR #58142): LLVM-facing backends and compiler extensions should validate compatibility against the new toolchain.

### Recommendations for Downstream Maintainers

- **JET.jl**: Re-check inference behavior, especially around cycle handling and recursive compilation corner cases.
- **Mooncake.jl**: Validate IR and CFG assumptions against the updated inference/runtime behavior.
- **GPUCompiler.jl** and LLVM-facing tooling: Validate against the LLVM 20 toolchain transition.
- Packages touching module/global internals: Re-check assumptions around binding partitions and method-table ownership.

---

*Compiled from direct investigation of the Julia 1.12 -> 1.13 merge window.*
