# Julia Compiler Deep Dive: Caching and Invalidation

How Julia caches compiled code and invalidates it when methods are redefined.

---

## Table of Contents

1. [Why Caching Matters](#1-why-caching-matters)
2. [CodeInstance: The Unit of Cached Compilation](#2-codeinstance-the-unit-of-cached-compilation)
3. [The World Age System](#3-the-world-age-system)
4. [Invalidation Triggers](#4-invalidation-triggers)
5. [Backedge-Based Invalidation](#5-backedge-based-invalidation)
6. [Precompilation and Revalidation](#6-precompilation-and-revalidation)
7. [Tips for Avoiding Invalidation](#7-tips-for-avoiding-invalidation)

---

## 1. Why Caching Matters

Julia is a just-in-time (JIT) compiled language. When you call a function for the first time with specific argument types, Julia performs type inference and generates optimized machine code. This compilation can take significant time, especially for complex functions.

Without caching, Julia would need to recompile functions every time you call them. Consider this example:

```julia
function compute(x)
    sum(i^2 for i in 1:x)
end

# First call: triggers compilation
@time compute(1000)  # 0.05 seconds (includes compilation)

# Second call: uses cached code
@time compute(2000)  # 0.000001 seconds (just execution)
```

The dramatic speedup on the second call comes from Julia's caching system. The compiler stores the generated code and reuses it for subsequent calls with compatible types.

### The Caching Challenge

Caching would be straightforward if Julia were a static language. But Julia is dynamic, and you can:

- Redefine methods at any time
- Add new method specializations
- Change global variables that affect compilation

This creates a fundamental tension: **How do you cache aggressively while ensuring correctness when code changes?**

Julia's answer is a sophisticated system built on three pillars:

1. **CodeInstance**: A cached compilation result with validity bounds
2. **World Age**: A monotonic counter tracking code changes
3. **Backedges**: Reverse dependency links enabling targeted invalidation

---

## 2. CodeInstance: The Unit of Cached Compilation

### The Compilation Hierarchy

Julia organizes compiled code in a three-level hierarchy:

```
Method (generic function definition)
   |
   +-- MethodInstance (specialized for specific type signature)
          |
          +-- CodeInstance (compiled code with world age validity)
                 |
                 +-- CodeInstance.next (linked list for different world ranges)
```

**Method**: A generic function definition, like `function foo(x) ... end`. One method can handle many different argument types.

**MethodInstance**: A method specialized for a specific type signature. For example, `foo(::Int64)` and `foo(::Float64)` are different MethodInstances of the same Method.

**CodeInstance**: The actual compiled code for a MethodInstance, valid within a specific world age range. A MethodInstance can have multiple CodeInstances, each valid for different world age ranges.

### What CodeInstance Contains

A CodeInstance stores everything needed to execute compiled code:

| Field | Purpose |
|-------|---------|
| `rettype` | Inferred return type |
| `exctype` | Inferred exception type |
| `inferred` | Inferred IR or `nothing` |
| `min_world` | First world where this code is valid |
| `max_world` | Last world where this code is valid |
| `edges` | Dependencies (methods, bindings) |
| `ipo_purity_bits` | Effect information |

### Cache Operations

The caching system is implemented in [`cicache.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/cicache.jl).

**Cache lookup** finds a CodeInstance valid for a given world:

```julia
# From cicache.jl:58-64
function get(wvc::InternalCodeCache, mi::MethodInstance, default)
    ci = ccall(:jl_rettype_inferred, Any,
               (Any, Any, UInt, UInt),
               wvc.owner, mi, wvc.min_world, wvc.max_world)
    return ci
end
```

Note: `InternalCodeCache` contains an `owner::Any` field that identifies the compilation owner (e.g., `:native` for native code generation), along with `min_world` and `max_world` fields defining the validity range.

The runtime searches the linked list of CodeInstances for one where `min_world <= current_world <= max_world`.

**Cache insertion** stores a new CodeInstance:

```julia
# From cicache.jl:44-52
function setindex!(cache::InternalCodeCache, ci::CodeInstance, mi::MethodInstance)
    m = mi.def
    if isa(m, Method)
        ccall(:jl_push_newly_inferred, Cvoid, (Any,), ci)
    end
    ccall(:jl_mi_cache_insert, Cvoid, (Any, Any), mi, ci)
    return cache
end
```

---

## 3. The World Age System

The world age system is Julia's mechanism for tracking code changes and ensuring consistency during execution.

### What is World Age?

World age is a monotonically increasing counter maintained by the Julia runtime. It increments on **code-changing events** such as:

- Method definition or redefinition
- Type definition

Global bindings can still affect inference and invalidation, but **not every binding change increments world age**. World age is primarily about new or replaced code.

Each CodeInstance has `min_world` and `max_world` fields defining when that compiled code is valid:

```julia
# From cicache.jl:3-14
struct WorldRange
    min_world::UInt
    max_world::UInt
end

# Check if a world is within range
in(world::UInt, wr::WorldRange) = wr.min_world <= world <= wr.max_world
```

A `max_world` of `typemax(UInt)` means the code is valid "forever" (until something invalidates it).

### How World Age Affects Execution

When you call a function, Julia looks for a CodeInstance valid at the *current* world age. This has important implications:

```julia
julia> f(x) = x + 1
f (generic function with 1 method)

julia> g() = f(1)
g (generic function with 1 method)

julia> g()  # Compiles g() at world age N, inlining f
2

julia> f(x) = x + 2  # World age becomes N+1
f (generic function with 1 method)

julia> g()  # Still returns 2! Uses cached code from world N
2

julia> Base.invokelatest(g)  # Forces use of latest world
3
```

This behavior exists because Julia "snapshots" the world age when entering a top-level call. Functions called during that execution see the snapshotted world, not newer definitions. This prevents inconsistencies from method redefinitions during execution.

### The Revalidation Sentinel

The special value `WORLD_AGE_REVALIDATION_SENTINEL = 1` marks CodeInstances that need revalidation. This is used when loading precompiled code that might have been invalidated by packages loaded before it.

---

## 4. Invalidation Triggers

Two main events trigger invalidation: method changes and binding changes.

### Method-Based Invalidation

When you define or redefine a method, Julia must invalidate any cached code that might call that method. The dispatch status flags help determine the severity of changes:

```julia
# From reinfer.jl:617-621
const METHOD_SIG_LATEST_WHICH = 0x1  # Method returned by `which` for its signature
const METHOD_SIG_LATEST_ONLY = 0x2   # Method is the only result from `methods`
```

For example, adding a more specific method can change which method gets dispatched:

```julia
# Initial state
f(x::Number) = "number"
g() = f(1)  # Compiled to call f(::Number)

# Add more specific method
f(x::Int) = "integer"  # Invalidates g() because dispatch target changed
```

### Binding-Based Invalidation

Changes to global variables can also affect compiled code. The function [`invalidate_code_for_globalref!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/bindinginvalidations.jl#L90-L163) handles this:

```julia
# From bindinginvalidations.jl:90-163
function invalidate_code_for_globalref!(gr::GlobalRef, new_max_world::UInt)
    # 1. Check if binding change affects inference results
    # 2. Invalidate methods using the GlobalRef
    # 3. Invalidate CodeInstances with explicit binding edges
    # 4. Propagate to modules that `using` the binding
end
```

This handles cases like:

```julia
const THRESHOLD = 100
f(x) = x > THRESHOLD  # Compiler might inline THRESHOLD

# If THRESHOLD is redefined, f must be invalidated
```

---

## 5. Backedge-Based Invalidation

The key to efficient invalidation is knowing *what* to invalidate. Julia uses "backedges" (reverse dependency links) to track this.

### What are Backedges?

When Julia compiles function `g()` that calls function `f()`, it records a backedge from `f` to `g`. If `f` changes, Julia can follow the backedge to invalidate `g`.

There are three types of backedges:

| Type | Purpose |
|------|---------|
| Method Instance Backedges | Track calls between specific specializations |
| Binding Backedges | Track dependencies on global variables |
| Method Table Backedges | Track dependencies on method existence |

### How Backedges are Recorded

During type inference, when Julia decides to inline or specialize on a call target, it records the dependency. From [`typeinfer.jl:786-813`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typeinfer.jl#L786-L813):

```julia
# Record method instance backedge
ccall(:jl_method_instance_add_backedge, Cvoid, (Any, Any, Any), callee_mi, invokesig, caller_ci)

# Record binding backedge
maybe_add_binding_backedge!(caller_ci, binding)

# Record method table backedge
ccall(:jl_method_table_add_backedge, Cvoid, (Any, Any, Any), mt, typ, caller_ci)
```

### Invalidation Propagation

When a method changes, Julia walks the backedges to find affected CodeInstances:

```
Method f() is redefined
    |
    v
Find all CodeInstances with backedges to f()
    |
    v
For each affected CodeInstance:
    - Set max_world to current_world - 1
    - Recursively invalidate its dependents
```

This cascading invalidation ensures correctness but can sometimes invalidate more code than necessary.

---

## 6. Precompilation and Revalidation

Julia's precompilation system saves compiled code to disk, but this code must be validated when loaded because the environment might have changed.

### The Precompilation Challenge

When you precompile a package, Julia saves:

- Inferred types and effects
- Optimized IR
- Backedge information

But when that package is loaded, other packages might have been loaded first that:

- Define methods that shadow the ones used during precompilation
- Change bindings the precompiled code depends on

### The Revalidation Process

The [`insert_backedges()`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/reinfer.jl#L71-L79) function in `reinfer.jl` handles this validation on load:

```julia
# From reinfer.jl:71-79
function insert_backedges(internal_methods::Vector{Any})
    # Process internal methods containing CodeInstances and their edges
    # Verify each CodeInstance's dependencies are still valid
    # Either restore the CodeInstance or mark for re-inference
end
```

### Tarjan's Algorithm for Verification

The verification process uses Tarjan's strongly connected components (SCC) algorithm to handle cycles efficiently. From [`verify_method()`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/reinfer.jl#L160-L389):

The algorithm proceeds in stages:

1. **`:init_and_process_callees`** - Initialize and validate non-CodeInstance edges
2. **`:recursive_phase`** - Recursively verify CodeInstance edges
3. **`:cleanup`** - Handle cycle completion
4. **`:return_to_parent`** - Propagate results upward

This ensures that mutually recursive functions are validated together.

### Verification of Call Edges

The [`verify_call()`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/reinfer.jl#L467-L615) function checks if a dispatch edge is still valid:

```julia
# From reinfer.jl:467-615
function verify_call(...)
    # Fast path: check if the method is still "the one"
    if (dispatch_status & METHOD_SIG_LATEST_WHICH) != 0
        # Quick check using `which()`
    end

    # Slow path: full method lookup comparison
    matches = findall(...)
    # Compare with stored matches
end
```

---

## 7. Tips for Avoiding Invalidation

Excessive invalidation can hurt performance, especially during development and in large applications. Here are practical strategies to minimize it.

### 7.1 Avoid Type-Unstable Globals

Type-unstable globals force conservative compilation and create binding dependencies:

```julia
# Bad: Type-unstable global
CONFIG = Dict{String,Any}()

function process()
    CONFIG["threshold"]  # Must handle any type
end

# Better: Typed global
const CONFIG = Ref{Float64}(0.0)

function process()
    CONFIG[]  # Compiler knows it's Float64
end
```

### 7.2 Use Function Barriers

When you must use type-unstable code, isolate it with function barriers:

```julia
# Bad: Type instability infects entire function
function process_data(data)
    config = load_config()  # Returns Any
    threshold = config["threshold"]
    # Everything after this is type-unstable
    result = filter(x -> x > threshold, data)
    sum(result)
end

# Better: Barrier function isolates instability
function process_data(data)
    config = load_config()
    threshold = config["threshold"]::Float64  # Assert type
    _process_data(data, threshold)
end

function _process_data(data, threshold::Float64)
    # This function is fully type-stable
    result = filter(x -> x > threshold, data)
    sum(result)
end
```

### 7.3 Be Careful with Method Redefinition

Each method redefinition triggers invalidation. During development, this is unavoidable, but in production code:

```julia
# Bad: Redefining in a loop
for i in 1:100
    @eval myfunction(x) = x + $i  # 100 invalidations!
end

# Better: Use closures or parameters
function make_adder(n)
    x -> x + n
end
```

### 7.4 Prefer Parametric Types over Abstract Types

Narrow type annotations reduce invalidation scope:

```julia
# Broader: Changes to any AbstractArray method might invalidate
function process(x::AbstractArray)
    sum(x)
end

# Narrower: Only changes to Vector{Float64} methods matter
function process(x::Vector{Float64})
    sum(x)
end
```

### 7.5 Use SnoopCompile to Diagnose Invalidations

The `SnoopCompile.jl` package provides tools for understanding invalidation:

```julia
using SnoopCompile

# Record invalidations during package loading
invalidations = @snoop_invalidations using MyPackage

# Analyze what triggered invalidations
trees = invalidation_trees(invalidations)
```

This helps identify which method definitions cause the most cascading invalidations.

### 7.6 Consider Package Load Order

Package load order affects invalidation. Packages loaded later might invalidate code from packages loaded earlier:

```julia
# If PackageB defines methods that shadow PackageA's assumptions
using PackageA  # Precompiled code loaded
using PackageB  # Might invalidate PackageA's code

# Consider: does PackageA actually need to be loaded first?
```

---

## Summary

Julia's caching and invalidation system balances performance with correctness through:

1. **CodeInstance**: Stores compiled code with world age validity bounds
2. **World Age**: Monotonic counter tracking code changes, ensuring consistent execution
3. **Backedges**: Reverse dependencies enabling targeted invalidation
4. **Lazy Revalidation**: Precompiled code validated on-demand using Tarjan's SCC algorithm
5. **Binding Tracking**: Global variable changes trigger appropriate invalidations

Understanding this system helps you:

- Diagnose unexpected recompilation
- Write code that caches effectively
- Structure packages to minimize invalidation
- Debug performance issues in large Julia applications

---

## Further Reading

- [SnoopCompile documentation](https://timholy.github.io/SnoopCompile.jl/stable/) - Tools for analyzing compilation and invalidation
- [Precompilation Deep Dive](./16-precompilation.md) - How caching and precompile statements reduce latency
- [Julia Compiler source](https://github.com/JuliaLang/julia/tree/master/Compiler/src) - The implementation details
- [Julia Developer Documentation](https://docs.julialang.org/en/v1/devdocs/eval/) - Official developer documentation on evaluation and world age

---

## Key Source Files

| File | Lines | Purpose |
|------|-------|---------|
| [`cicache.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/cicache.jl) | ~71 | CodeInstance cache abstraction |
| [`reinfer.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/reinfer.jl) | ~658 | Re-inference and validation |
| [`bindinginvalidations.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/bindinginvalidations.jl) | ~202 | Binding invalidation logic |
| [`methodtable.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/methodtable.jl) | ~159 | Method table queries |
| [`typeinfer.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typeinfer.jl) | ~1882 | Type inference and caching integration |
