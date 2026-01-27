# Julia Compiler Deep Dive: Type Functions (tfuncs)

A deep dive into how the compiler knows return types of builtins.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [What Are tfuncs?](#1-what-are-tfuncs)
2. [How tfuncs Are Organized](#2-how-tfuncs-are-organized)
3. [Key tfuncs Walkthrough](#3-key-tfuncs-walkthrough)
4. [The Lattice-Aware Dispatch Pattern](#4-the-lattice-aware-dispatch-pattern)
5. [Connection to the Effects System](#5-connection-to-the-effects-system)
6. [The Cost Model for Inlining](#6-the-cost-model-for-inlining)
7. [Summary](#7-summary)

---

## 1. What Are tfuncs?

**tfuncs** (type functions) are Julia's mechanism for inferring return types of **builtin operations** and **intrinsic functions** during type inference. Unlike regular Julia functions that dispatch on runtime values, builtins are primitives implemented directly in C or LLVM. The compiler cannot infer their behavior through normal abstract interpretation; instead, it relies on handwritten tfuncs that encode human knowledge about each operation.

### The Problem tfuncs Solve

Consider this code:

```julia
struct Point
    x::Float64
    y::Float64
end

function get_x(p::Point)
    return p.x  # getfield(p, :x)
end
```

The expression `p.x` compiles to `getfield(p, :x)`. But `getfield` is a builtin, not a Julia function. The compiler cannot look at `getfield`'s implementation to determine that accessing field `:x` of a `Point` returns `Float64`. Instead, the `getfield_tfunc` function encodes this knowledge.

### What tfuncs Provide

For each builtin, a tfunc provides:

1. **Return type inference**: Given argument types, compute the most precise return type
2. **Constant folding**: When arguments are constants, return `Const` types for compile-time evaluation
3. **Effect information**: Whether the operation can throw, is consistent, or has side effects
4. **Cost estimation**: A numeric value used in inlining decisions

**Source file**: [`Compiler/src/tfuncs.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl) (~3,300 lines)

---

## 2. How tfuncs Are Organized

tfuncs are organized into two categories stored in separate lookup tables.

### Intrinsics vs. Builtins

**Intrinsic functions** (`Core.IntrinsicFunction`) map directly to machine instructions or LLVM operations. Examples include `add_int`, `mul_float`, and `bitcast`. They have fixed integer IDs assigned at compile time.

**Builtin functions** (`Core.Builtin`) are higher-level primitives that may involve more complex logic. Examples include `getfield`, `setfield!`, `isa`, and `typeof`.

### The Lookup Tables

```julia
# Intrinsics: Indexed by intrinsic ID (fixed at compile time)
const T_IFUNC = Vector{Tuple{Int, Int, Any}}(undef, N_IFUNC)
const T_IFUNC_COST = Vector{Int}(undef, N_IFUNC)

# Builtins: Parallel arrays (dynamic lookup)
const T_FFUNC_KEY = Vector{Any}()      # The builtin function
const T_FFUNC_VAL = Vector{Tuple{Int, Int, Any}}()  # (min_args, max_args, tfunc)
const T_FFUNC_COST = Vector{Int}()     # Inlining cost
```

**Source**: [tfuncs.jl#L54-L58](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L54-L58)

### The `add_tfunc` Registration Function

Every tfunc is registered using `add_tfunc`, which records the function, its argument count bounds, the inference function, and a cost:

```julia
function add_tfunc(f::IntrinsicFunction, minarg::Int, maxarg::Int,
                   @nospecialize(tfunc), cost::Int)
    idx = reinterpret(Int32, f) + 1
    T_IFUNC[idx] = (minarg, maxarg, tfunc)
    T_IFUNC_COST[idx] = cost
end

function add_tfunc(@nospecialize(f::Builtin), minarg::Int, maxarg::Int,
                   @nospecialize(tfunc), cost::Int)
    push!(T_FFUNC_KEY, f)
    push!(T_FFUNC_VAL, (minarg, maxarg, tfunc))
    push!(T_FFUNC_COST, cost)
end
```

**Source**: [tfuncs.jl#L79-L88](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L79-L88)

### File Layout Overview

| Section | Lines | Purpose |
|---------|-------|---------|
| Setup & Registration | 1-90 | `@nospecs` macro, lookup tables, `add_tfunc` |
| Intrinsic tfuncs | 151-322 | Arithmetic, bitwise, conversion operations |
| Builtin tfuncs | 324-1950 | Field access, type operations, control flow |
| Memory operations | 2012-2258 | Memory/memoryref operations |
| Effects inference | 2260-2783 | `builtin_effects`, `builtin_nothrow` |
| Special functions | 2785-3197 | `builtin_tfunction`, `return_type_tfunc` |

---

## 3. Key tfuncs Walkthrough

Let us examine three essential tfuncs to understand the patterns.

### 3.1 `typeof_tfunc`: Inferring the Type of a Value

The `typeof` builtin returns the runtime type of its argument. The tfunc must compute what type `typeof(x)` returns given the inferred type of `x`.

**Source**: [tfuncs.jl#L810-L857](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L810-L857)

```julia
# Simplified for clarity
@nospecs function typeof_tfunc(lattice::AbstractLattice, t)
    # Case 1: Constant value - return the exact type as a constant
    isa(t, Const) && return Const(typeof(t.val))

    t = widenconst(t)

    # Case 2: Type{T} - typeof a type is DataType (or typeof the specific type)
    if isType(t)
        tp = t.parameters[1]
        if hasuniquerep(tp)
            return Const(typeof(tp))
        end
    # Case 3: Concrete DataType - return the type as a constant
    elseif isa(t, DataType)
        if isconcretetype(t)
            return Const(t)
        elseif t === Any
            return DataType
        else
            return Type{<:t}  # Abstract type: typeof returns some subtype
        end
    # Case 4: Union - recurse on both branches
    elseif isa(t, Union)
        a = typeof_tfunc(lattice, t.a)
        b = typeof_tfunc(lattice, t.b)
        return tmerge(lattice, a, b)
    end
    return DataType  # Conservative fallback
end
```

**Example behavior**:

| Input Type | `typeof_tfunc` Returns | Explanation |
|------------|----------------------|-------------|
| `Const(42)` | `Const(Int64)` | Constant value has constant type |
| `Int64` | `Const(Int64)` | Concrete type is known exactly |
| `Integer` | `Type{<:Integer}` | Abstract type: could be any subtype |
| `Union{Int64,Float64}` | `Union{Type{Int64},Type{Float64}}` | Merge results for union branches |

### 3.2 `isa_tfunc`: Type Checking with Constant Results

The `isa` builtin checks whether a value is an instance of a type. When the compiler can prove the result at compile time, the tfunc returns `Const(true)` or `Const(false)`.

**Source**: [tfuncs.jl#L877-L909](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L877-L909)

```julia
# Simplified for clarity
@nospecs function isa_tfunc(lattice::AbstractLattice, v, tt)
    # Extract the type being tested against
    t, isexact = instanceof_tfunc(tt, true)

    if t === Bottom
        # Type argument is not a valid type
        hasintersect(widenconst(tt), Type) || return Union{}
        return Const(false)
    end

    if !has_free_typevars(t)
        # Can we prove v <: t? Then isa(v, t) is definitely true
        if lattice_subtype(lattice, v, t)
            if isexact && isnotbrokensubtype(v, t)
                return Const(true)
            end
        else
            # Is there any overlap between v and t?
            if !hasintersect(widenconst(v), t)
                return Const(false)  # No overlap: definitely false
            end
        end
    end

    return Bool  # Cannot determine at compile time
end
```

**Example behavior**:

```julia
function example(x::Int64)
    isa(x, Integer)  # isa_tfunc returns Const(true) - Int64 <: Integer
    isa(x, String)   # isa_tfunc returns Const(false) - no overlap
    isa(x, Number)   # isa_tfunc returns Const(true) - Int64 <: Number
end

function example2(x::Union{Int64,Float64})
    isa(x, Number)   # Const(true) - both branches are Numbers
    isa(x, Int64)    # Bool - cannot determine which branch
end
```

### 3.3 `getfield_tfunc`: Field Access with PartialStruct Support

Field access is one of the most important operations for type inference. The `getfield_tfunc` must handle multiple cases: known field names, constant indices, and partial struct information.

**Source**: [tfuncs.jl#L1081-L1097](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L1081-L1097) and [tfuncs.jl#L1125-L1287](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L1125-L1287)

```julia
@nospecs function getfield_tfunc(lattice::AbstractLattice, s00, name)
    # Dispatch to the lattice-aware implementation
    return _getfield_tfunc(lattice, s00, name, false)
end

# The core implementation handles different lattice levels
@nospecs function _getfield_tfunc(lattice::PartialsLattice, s00, name, setfield::Bool)
    # Handle PartialStruct: we know field types more precisely
    if isa(s00, PartialStruct)
        s = s00.typ
        if isa(name, Const)
            nv = name.val
            if isa(nv, Symbol)
                nv = fieldindex(s, nv, false)
            end
            if isa(nv, Int) && 1 <= nv <= length(s00.fields)
                return unwrapva(s00.fields[nv])
            end
        end
    end
    # Fall through to the next lattice level
    return _getfield_tfunc(widenlattice(lattice), s00, name, setfield)
end
```

**Example with PartialStruct**:

```julia
struct Container
    data::Vector{Int}
    length::Int
end

function process(c::Container)
    # During inference, if c is represented as:
    # PartialStruct(Container, [Vector{Int}, Const(10)])

    c.length  # getfield_tfunc returns Const(10)!
    c.data    # getfield_tfunc returns Vector{Int}
end
```

This is how the compiler can constant-propagate field values through struct construction and access.

---

## 4. The Lattice-Aware Dispatch Pattern

A distinguishing feature of tfuncs is **lattice-aware dispatch**. The type lattice has multiple levels of refinement, and tfuncs dispatch on the lattice type to handle each level appropriately.

### The Pattern

```julia
# Entry point uses the full inference lattice
@nospecs function _getfield_tfunc(lattice::InferenceLattice, s00, name, setfield::Bool)
    # Delegate to the next lattice level
    return _getfield_tfunc(widenlattice(lattice), s00, name, setfield)
end

# Handle PartialStruct at the PartialsLattice level
@nospecs function _getfield_tfunc(lattice::PartialsLattice, s00, name, setfield::Bool)
    if isa(s00, PartialStruct)
        # Extract field from known struct layout
        # ...
    end
    # Fall through to ConstsLattice
    return _getfield_tfunc(widenlattice(lattice), s00, name, setfield)
end

# Handle Const at the ConstsLattice level
@nospecs function _getfield_tfunc(lattice::ConstsLattice, s00, name, setfield::Bool)
    if isa(s00, Const)
        # Evaluate field access at compile time
        # ...
    end
    # Fall through to JLTypeLattice
    return _getfield_tfunc(widenlattice(lattice), s00, name, setfield)
end

# Final fallback: use only Julia type information
@nospecs function _getfield_tfunc(lattice::JLTypeLattice, s00, name, setfield::Bool)
    # Use fieldtype() to determine the declared field type
    # ...
end
```

### Why This Matters

This pattern ensures that:

1. **Maximum precision**: Each lattice level extracts as much information as possible
2. **Graceful degradation**: When refined information is not available, the tfunc falls back to less precise but still sound results
3. **Modularity**: Each lattice level handles its own concerns

### Visual Flow

```
InferenceLattice (most refined)
    |
    v
AnyConditionalsLattice (handles Conditional types)
    |
    v
AnyMustAliasesLattice (handles must-alias information)
    |
    v
PartialsLattice (handles PartialStruct, Conditional)
    |
    v
ConstsLattice (handles Const values)
    |
    v
JLTypeLattice (base Julia types only)
```

---

## 5. Connection to the Effects System

tfuncs do not just compute return types; they also determine the **effects** of builtin operations. Effects describe computational properties that enable optimizations.

### Effect Categories

| Effect | Meaning |
|--------|---------|
| `consistent` | Same inputs always produce same outputs |
| `effect_free` | No externally visible side effects |
| `nothrow` | Cannot throw an exception |
| `terminates` | Guaranteed to finish |
| `inaccessiblememonly` | Only accesses stack-allocated memory |
| `noub` | No undefined behavior |

### Builtin Classification Lists

The file defines lists categorizing builtins by their effects.

**Source**: [tfuncs.jl#L2342-L2452](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2342-L2452)

```julia
const _PURE_BUILTINS = Any[
    tuple, svec, ===, typeof, nfields,
    # ...
]

const _CONSISTENT_BUILTINS = Any[
    throw,
    # ...
]

const _EFFECT_FREE_BUILTINS = Any[
    typeof, sizeof, isa,
    # ...
]
```

### The `builtin_effects` Function

This function computes effects for each builtin call.

**Source**: [tfuncs.jl#L2631-L2708](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2631-L2708)

```julia
# Simplified for clarity
function builtin_effects(lattice::AbstractLattice, @nospecialize(f::Builtin),
                         argtypes::Vector{Any}, @nospecialize(rt))
    if f === getfield
        return getfield_effects(lattice, argtypes, rt)
    elseif f === setfield!
        return setfield!_effects(lattice, argtypes, rt)
    # ... other builtins
    end

    # Default classification based on lists
    consistent = f in _CONSISTENT_BUILTINS
    effect_free = f in _EFFECT_FREE_BUILTINS
    nothrow = builtin_nothrow(lattice, f, argtypes, rt)

    return Effects(; consistent, effect_free, nothrow, ...)
end
```

### Example: `getfield_effects`

**Source**: [tfuncs.jl#L2520-L2557](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2520-L2557)

```julia
function getfield_effects(lattice::AbstractLattice, argtypes::Vector{Any}, @nospecialize(rt))
    # Consistency depends on mutability
    obj = argtypes[1]
    consistent = is_immutable_argtype(obj) ? ALWAYS_TRUE : CONSISTENT_IF_INACCESSIBLEMEMONLY

    # nothrow depends on bounds checking and field existence
    nothrow = getfield_nothrow(lattice, argtypes, boundscheck)

    return Effects(EFFECTS_TOTAL; consistent, nothrow, inaccessiblememonly, noub)
end
```

**Key insight**: Accessing a field of an immutable struct is always consistent because the field cannot change. Accessing a mutable struct is only consistent if the memory is inaccessible to other code.

---

## 6. The Cost Model for Inlining

Each tfunc registration includes a **cost** value that influences inlining decisions. Lower costs encourage inlining; higher costs discourage it.

### How Cost Is Registered

```julia
# Cheap operations - always inline
add_tfunc(throw, 1, 1, throw_tfunc, 0)
add_tfunc(Core.Intrinsics.bitcast, 2, 2, bitcast_tfunc, 0)

# Medium cost - inline when beneficial
add_tfunc(getfield, 2, 4, getfield_tfunc, 1)
add_tfunc(isa, 2, 2, isa_tfunc, 1)
add_tfunc(typeof, 1, 1, typeof_tfunc, 1)

# Expensive - avoid inlining unless necessary
add_tfunc(apply_type, 1, INT_INF, apply_type_tfunc, 10)
add_tfunc(Core.memorynew, 2, 2, memorynew_tfunc, 10)

# Very expensive - rarely inline
add_tfunc(applicable, 1, INT_INF, applicable_tfunc, 40)
add_tfunc(Core._typevar, 3, 3, typevar_tfunc, 100)
```

### Cost Interpretation

| Cost Range | Interpretation | Examples |
|------------|---------------|----------|
| 0 | Trivial, always inline | `throw`, `bitcast` |
| 1 | Simple field access/type check | `getfield`, `isa`, `typeof` |
| 10-20 | Moderate complexity | `apply_type`, memory operations |
| 40-100 | Expensive runtime operations | `applicable`, `_typevar` |

### How Cost Affects Compilation

The inlining pass uses these costs when deciding whether to inline a call:

```julia
# Pseudocode from the inliner
function should_inline(call_cost, inline_budget)
    if call_cost == 0
        return true  # Always inline trivial operations
    end
    return call_cost <= inline_budget
end
```

The cost model ensures that:

1. Simple operations like field access are always inlined
2. Complex operations are inlined only when the budget permits
3. Very expensive operations are rarely inlined, preserving code size

---

## 7. Summary

### Key Takeaways

1. **tfuncs are the bridge** between builtin operations and type inference. They encode human knowledge about what each primitive operation returns.

2. **Two registration tables** exist: `T_IFUNC` for intrinsics (indexed by ID) and `T_FFUNC_*` for builtins (parallel arrays).

3. **Lattice-aware dispatch** allows tfuncs to extract maximum precision from refined types like `Const` and `PartialStruct`, with graceful fallback to less precise inference.

4. **Effects tracking** is integrated into tfuncs, determining whether operations are consistent, effect-free, or may throw.

5. **Cost values** guide the inliner, with simple operations (cost 0-1) always inlined and expensive operations (cost 40+) rarely inlined.

### How It Fits Together

```
Source Code
    |
    v
Type Inference (abstractinterpretation.jl)
    |
    +---> builtin_tfunction() (tfuncs.jl)
    |         |
    |         +---> typeof_tfunc, getfield_tfunc, isa_tfunc, ...
    |         |
    |         +---> Returns: inferred type + effects
    |
    v
InferenceResult (type + effects for the method)
    |
    v
Optimization (uses effects for DCE, CSE, constant folding)
    |
    v
Code Generation
```

### Further Reading

- **Type Lattice**: How `Const`, `PartialStruct`, and other refined types work
- **Effects System**: The full effects model and its impact on optimization
- **Inlining Pass**: How the cost model influences inlining decisions
- **Abstract Interpretation**: The overall type inference algorithm

---

## References

- [tfuncs.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl) - Main source file
- [effects.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl) - Effects system
- [abstractinterpretation.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl) - Type inference engine
