# Julia Compiler Deep Dive: Specialization Limits and Inference Budgets

Julia balances **precision** and **latency**. This tutorial explains the limits and heuristics that cause inference to widen or stop specializing, and how to recognize them.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

**Source anchor**: `Compiler/src/types.jl` (`InferenceParams` documentation).

---

## Table of Contents

1. [Why Limits Exist](#1-why-limits-exist)
2. [InferenceParams: The Key Knobs](#2-inferenceparams-the-key-knobs)
3. [Controlling Specialization with @nospecialize](#3-controlling-specialization-with-nospecialize)
4. [Type Widening Constants](#4-type-widening-constants)
5. [How Limits Manifest](#5-how-limits-manifest)
6. [Practical Signals in @code_warntype](#6-practical-signals-in-code_warntype)
7. [Guidelines for Library Authors](#7-guidelines-for-library-authors)
8. [Summary](#8-summary)

---

## 1. Why Limits Exist

Inference is expensive. Without limits, type inference can:

- explode in method combinations
- loop on recursive calls
- spend huge time for tiny precision gains

Julia therefore uses **heuristics and budgets** to cap work.

---

## 2. InferenceParams: The Key Knobs

Selected parameters from `InferenceParams` (see `Compiler/src/types.jl`):

- `max_methods`: cap on the number of methods to consider at a call site
- `max_union_splitting`: limit on union splitting for tuples and arguments
- `max_apply_union_enum`: limit on union enumeration for `_apply_iterate`
- `max_tuple_splat`: maximum tuple length to splat in inference
- `tuple_complexity_limit_depth`: controls tuple-type blowup

These are *tradeoffs* between compile-time cost and precision.

**Source**: [`InferenceParams`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/types.jl#L216-L290)

**Defaults (as of this snapshot)**:

- `max_methods = BuildSettings.MAX_METHODS`
- `max_union_splitting = 4`
- `max_apply_union_enum = 8`
- `max_tuple_splat = 32`
- `tuple_complexity_limit_depth = 3`

### 2.1 Per-Module Overrides

Some limits can be adjusted via `@max_methods`:

```julia
# Module-level (at top of module, limited to values 1-4)
Base.Experimental.@max_methods 4

# Per-function (forward declaration only, allows 1-255)
Base.Experimental.@max_methods 5 function f end
```

Note that `@max_methods` cannot be applied inline with a function body. The per-function form only works with forward declarations.

This trades compile latency for precision at specific call sites.

### 2.2 Where Limits Are Enforced

Inference checks budgets at dispatch and union-splitting boundaries:

- `get_max_methods` resolves per-function and per-module caps
- `find_method_matches` applies `max_methods`
- `unionsplitcost` drives `max_union_splitting`

**Sources**:
- [`get_max_methods`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/inferencestate.jl#L1097-L1133)
- [`find_method_matches`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl#L332-L355)
- [`unionsplitcost`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typeutils.jl#L201-L220)

---

## 3. Controlling Specialization with @nospecialize

The `@nospecialize` macro prevents the compiler from specializing on specific arguments. This is directly related to specialization limits and provides fine-grained control over when specialization occurs.

### 3.1 Basic Usage

```julia
function process(@nospecialize(x), y)
    # x will not trigger specialization
    # y will specialize as normal
    ...
end
```

### 3.2 When to Use @nospecialize

- **High-arity generic functions**: When a function is called with many different types but the type information doesn't improve codegen
- **Error handling paths**: Exception handling code that shouldn't bloat the method cache
- **Logging and debugging**: Functions where type specialization adds compile time without runtime benefit
- **Wrapper functions**: Pass-through functions that immediately call another function

### 3.3 @nospecialize vs @specialize

You can also re-enable specialization within a `@nospecialize` block:

```julia
function f(@nospecialize(x::T)) where T
    @specialize
    # specialization re-enabled here
    ...
end
```

### 3.4 Module-Level @nospecialize

For multiple functions, use the block form:

```julia
@nospecialize
function f(x)
    ...
end
function g(x)
    ...
end
@specialize  # re-enable for subsequent functions
```

---

## 4. Type Widening Constants

Beyond method limits, Julia controls type complexity through constants in `Compiler/src/typelimits.jl`.

### 4.1 Union Type Limits

```julia
MAX_TYPEUNION_COMPLEXITY = 3  # Maximum nesting depth of union types
MAX_TYPEUNION_LENGTH = 3      # Maximum number of elements in a union
```

These prevent unbounded growth of union types during inference.

### 4.2 Key Type Limiting Functions

- **`limit_type_size()`**: Truncates overly complex types to simpler approximations
- **`type_more_complex()`**: Compares type complexity to decide when widening is needed
- **`issimpleenoughtype()`**: Checks if a type is simple enough to avoid widening

These functions work together to ensure inference terminates while preserving useful type information.

**Source**: [`typelimits.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl)

---

## 5. How Limits Manifest

When limits are hit, you'll often see:

- `Any` or widened unions in `@code_warntype`
- Inference stopping at a call site with "too many methods"
- Fallback to generic calls instead of inlining

This is **expected behavior** for large, highly-generic code.

### 5.1 A Common Trigger: `max_methods`

If a call site has too many applicable methods, inference returns a conservative result.
This is why large unions or very generic APIs often yield `Any` in hot loops.

---

## 6. Practical Signals in @code_warntype

Look for:

- `invoke` or `jl_apply_generic` in `@code_llvm`
- large `Union` types at loop headers
- loss of constants (no `Const(...)`)

These are hints that inference hit a budget or a widening heuristic.

### 6.1 Debugging Tip

Use `@code_typed optimize=false` to inspect inference results before inlining and optimization.

---

## 7. Guidelines for Library Authors

- Keep hot-path APIs type-stable
- Use **function barriers** to isolate dynamic input
- Avoid unbounded unions and deeply nested tuples in hot loops
- Prefer concrete container element types
- Use `@nospecialize` on arguments that don't benefit from specialization

---

## 8. Summary

- Limits are a design choice to keep Julia responsive.
- The most common ones are `max_methods` and `max_union_splitting`.
- Use `@nospecialize` to prevent specialization where it's not beneficial.
- Type widening constants (`MAX_TYPEUNION_COMPLEXITY`, `MAX_TYPEUNION_LENGTH`) control union complexity.
- Widening isn't failure; it's a controlled tradeoff.

Next: [16-precompilation.md](./16-precompilation.md)
