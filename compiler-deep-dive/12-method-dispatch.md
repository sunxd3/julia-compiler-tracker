# Julia Compiler Deep Dive: Method Dispatch

How Julia selects which method to call and how dispatch interacts with inference and caching.

---

## Table of Contents

1. [What Problem Does Dispatch Solve?](#1-what-problem-does-dispatch-solve)
2. [Method Tables and Generic Functions](#2-method-tables-and-generic-functions)
3. [Specificity and Ambiguity](#3-specificity-and-ambiguity)
4. [Runtime Dispatch vs. Inference-Time Dispatch](#4-runtime-dispatch-vs-inference-time-dispatch)
5. [Caching and World Age Interaction](#5-caching-and-world-age-interaction)
6. [Performance Implications](#6-performance-implications)
7. [Summary](#7-summary)

---

## 1. What Problem Does Dispatch Solve?

When you call `f(x, y)`, Julia must choose the *single best* method out of possibly many definitions:

```julia
f(x::Int, y::Int) = x + y
f(x::Real, y::Real) = x + y
```

Dispatch answers:

- Which method applies to the **actual argument types**?
- Which applicable method is **most specific**?
- Is there an **ambiguity** that needs resolution?

Dispatch is central to performance because it determines whether Julia can generate a direct, specialized call or must use dynamic dispatch.

---

## 2. Method Tables and Generic Functions

Every generic function has an associated **method table**. At runtime, Julia:

1. Builds an argument type tuple (including the function object itself).
2. Looks up matching methods in the method table.
3. Chooses the most specific applicable method.

Key runtime entry points (C):

- `jl_apply_generic` (generic call entry)
- `jl_gf_invoke_lookup` / `_gf_invoke_lookup` (method lookup)

**Source**: `julia/src/gf.c`

### 2.1 Fast-Path Caches in Runtime Dispatch

The hot path is in `jl_lookup_generic_`, which checks several caches before doing a full method search:

1. **Call-site cache** (small associative cache)
2. **Leaf cache** (fast lookup for concrete signatures)
3. **Method cache** (typemap lookup)

**Source**: [`jl_lookup_generic_`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L4181-L4265)

This explains why the same call site gets faster after the first execution: the method instance is cached in a fast lookup structure keyed by callsite and signature.

### 2.2 Single-Method Lookup for `invoke`

`invoke` uses `_gf_invoke_lookup`, which calls `ml_matches` and requires exactly one match:

**Source**: [`_gf_invoke_lookup`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L4320-L4345)

### 2.3 Typemap Search (Generic Matching)

When caches miss, dispatch falls back to typemap search over method signatures.
This is implemented in `jl_typemap_assoc_by_type`, which walks the signature tree
and tests applicability.

**Source**: [`jl_typemap_assoc_by_type`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/typemap.c#L926-L1095)

### 2.4 Central Method Lookup: `ml_matches`

The `ml_matches` function is central to method lookup. It finds all methods matching a given signature type, handling ambiguity detection and sorting by specificity. This is the core workhorse called by both `jl_matching_methods` and `_gf_invoke_lookup`.

**Source**: [`ml_matches`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L4845)

### 2.5 Method Specialization: `jl_specializations_get_linfo`

Once a method is selected, Julia creates or retrieves a specialized `MethodInstance` for the concrete argument types. `jl_specializations_get_linfo` handles this lookup into the method's specialization cache, creating a new `MethodInstance` if one does not already exist.

**Source**: [`jl_specializations_get_linfo`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L256-L268)

---

## 3. Specificity and Ambiguity

Two method signatures can both apply. Julia chooses the **most specific** one.

Simplified rule:

- Method A is more specific than Method B if A's signature is a strict subtype of B's signature. When neither is a subtype of the other, a complex specificity algorithm compares them element-wise.

Ambiguity happens when:

- Two methods are applicable
- Neither is more specific than the other

This triggers an ambiguity warning (or error in some contexts). Dispatch is deterministic within a given **world age**, but ambiguities can change as methods are added.

### 3.1 Specificity Queries in the Compiler

The compiler uses helpers like `findsup` to select the most specific applicable method and to track ambiguity.

**Source**: [`findsup`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/methodtable.jl#L133-L158)

### 3.2 Specificity Logic in C

Specificity comparisons ultimately use subtype checks and `type_morespecific_`.

**Source**: [`jl_type_morespecific`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/subtype.c#L5519-L5530)

---

## 4. Runtime Dispatch vs. Inference-Time Dispatch

**Runtime dispatch** uses concrete argument types and must be correct for all calls:

```
f(x::Any, y::Any)  # runtime sees actual types and picks a method
```

**Inference-time dispatch** uses *abstract* types (e.g., `Union`, `Any`) to predict call targets:

```
abstract_call_gf_by_type(...)  # Compiler-side resolution
```

This is where the compiler decides:

- Can the call be **devirtualized** (one method)?
- Do we need **union splitting**?
- Should we fall back to a generic call?

**Source**: `Compiler/src/abstractinterpretation.jl`

**Entry point**: [`abstract_call_gf_by_type`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl#L109-L330)

### 4.1 Inference-Time Method Search

Inference uses `find_method_matches` to gather applicable methods and apply union-splitting heuristics:

- `find_method_matches` decides between simple matching and union splitting
- `findall` in `methodtable.jl` returns a `MethodLookupResult` with world-range validity

**Sources**:
- [`find_method_matches`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl#L332-L339)
- [`findall`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/methodtable.jl#L70-L113)

---

## 5. Caching and World Age Interaction

Dispatch results are cached in `CodeInstance`s (see [08 - Caching](08-caching.md)). However:

- Method redefinitions change world age
- Cached dispatch results are only valid within a world range
- Invalidation propagates through backedges

This is why "fast after first call" depends on stable method tables and predictable dispatch.

### 5.1 Walkthrough: One Call to `f(x, y)`

Simplified runtime flow:

1. `jl_apply_generic` grabs the current world age.
2. `jl_lookup_generic_` searches caches and the method table.
3. If a match is found, it returns a `MethodInstance`.
4. `_jl_invoke` executes (or triggers compilation of) the method instance.

**Sources**:
- [`jl_apply_generic`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L4310-L4318)
- [`jl_lookup_generic_`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/gf.c#L4181-L4265)

---

## 6. Performance Implications

Dispatch directly impacts optimization:

- **Concrete types** -> direct call, inlining possible
- **Unions** -> union splitting or dynamic dispatch
- **`Any`** -> worst-case: dynamic dispatch, boxing, allocations

**Practical tips**:

- Keep call sites type-stable when possible
- Use function barriers to isolate dynamic parts
- Avoid abstract containers in hot paths

---

## 7. Summary

- Dispatch selects the most specific applicable method.
- Runtime uses concrete types; inference uses abstract types.
- Ambiguity happens when no method is strictly more specific.
- Dispatch results are cached and scoped by world age.

Next: [15 - Specialization Limits](15-specialization-limits.md) for why inference sometimes gives up.
