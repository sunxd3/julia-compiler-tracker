# Julia Compiler Deep Dive: Escape Analysis

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

**Primary source file**: [`Compiler/src/ssair/EscapeAnalysis.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl)

---

## Table of Contents

1. [Why Escape Analysis?](#1-why-escape-analysis)
2. [The Escape Lattice: Understanding Escape States](#2-the-escape-lattice-understanding-escape-states)
3. [The Analysis Algorithm: Backward Dataflow](#3-the-analysis-algorithm-backward-dataflow)
4. [Alias Tracking with Union-Find](#4-alias-tracking-with-union-find)
5. [Code Examples: What Escapes and What Doesn't](#5-code-examples-what-escapes-and-what-doesnt)
6. [How Optimizations Use Escape Information](#6-how-optimizations-use-escape-information)
7. [Writing Allocation-Free Code](#7-writing-allocation-free-code)

---

## 1. Why Escape Analysis?

When you write Julia code that creates objects, the compiler faces a fundamental question: **where should this object live?** The answer determines whether your code allocates on the heap (slow, requires garbage collection) or the stack (fast, automatically cleaned up).

### The Allocation Elimination Problem

Consider this simple function:

```julia
function sum_point(x, y)
    p = Point(x, y)
    return p.x + p.y
end
```

If `Point` is a mutable struct, Julia must decide:
- **Heap allocation**: Create `p` on the heap, track it for garbage collection
- **Stack allocation**: Create `p` on the stack, eliminate it entirely via SROA

The key insight is that heap allocation is only *necessary* when the object "escapes" the function. If `p` never leaves `sum_point`, we can eliminate the allocation entirely.

### What "Escape" Means

An object **escapes** when it becomes visible outside its creation context:

| Escape Type | Example | Why It Escapes |
|-------------|---------|----------------|
| Return escape | `return p` | Caller receives the object |
| Thrown escape | `throw(p)` | Exception handler may catch it |
| Argument escape | Function argument | Caller passed it, can still see it |
| Global escape | `global_var = p` | Visible to entire program |

If an object has **no escape**, the compiler can:
1. Replace heap allocation with stack allocation
2. Inline finalizers safely
3. Eliminate the allocation entirely via Scalar Replacement of Aggregates (SROA)

---

## 2. The Escape Lattice: Understanding Escape States

Escape analysis uses a [lattice](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L45-L123) to represent escape states. The lattice provides a mathematical framework where states can be compared and combined.

### The EscapeInfo Structure

Each value in the IR has an associated [`EscapeInfo`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L45-L123):

```julia
struct EscapeInfo
    Analyzed::Bool        # Has this value been analyzed?
    ReturnEscape::Bool    # Can escape via return statement?
    ThrownEscape::BitSet  # SSA positions where it can be thrown
    AliasInfo             # Field-level aliasing information
    Liveness::BitSet      # SSA positions where value must be live
end
```

### Escape State Hierarchy

The lattice forms a hierarchy from "most optimizable" to "least optimizable":

```
                    AllEscape
                   (top - cannot optimize)
                        |
           +-----------+-----------+
           |           |           |
    ReturnEscape  ThrownEscape  GlobalRef
           |           |           |
           +-----------+-----------+
                       |
                  ArgEscape
                  (visible to caller)
                       |
                   NoEscape
              (bottom - fully optimizable)
                       |
                  NotAnalyzed
              (before analysis runs)
```

**Note**: This diagram is a simplification. `EscapeInfo` tracks multiple escape dimensions (return, throw, aliasing, liveness), and the analysis combines them with additional bookkeeping beyond a simple linear lattice.

### Convenience Constructors

The module provides [constructors](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L139-L145) for common escape states:

| Constructor | Description | Can Optimize? |
|-------------|-------------|---------------|
| `NotAnalyzed()` | Value has not been analyzed yet | N/A |
| `NoEscape()` | Value does not escape anywhere | Yes |
| `ArgEscape()` | Value is a function argument | Partially |
| `ReturnEscape(pc)` | Value escapes via return at statement `pc` | No |
| `AllReturnEscape()` | Value escapes via return (any statement) | No |
| `ThrownEscape(pc)` | Value may be thrown at statement `pc` | No |
| `AllEscape()` | Value escapes everywhere (conservative) | No |

### Predicate Functions

To query escape states, use these [predicate functions](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L150-L156):

```julia
has_no_escape(info)     # True if fully optimizable
has_arg_escape(info)    # True if visible as argument
has_return_escape(info) # True if returned to caller
has_thrown_escape(info) # True if may be thrown
has_all_escape(info)    # True if escapes everywhere
```

---

## 3. The Analysis Algorithm: Backward Dataflow

Escape analysis uses a **backward dataflow algorithm**. This design choice is natural because escapes propagate backward: if a value escapes at a return statement, that escape information must flow back to where the value was created.

### Entry Point: analyze_escapes

The main entry point is [`analyze_escapes`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L560-L652):

```julia
function analyze_escapes(ir::IRCode, nargs::Int, 𝕃ₒ::AbstractLattice, get_escape_cache)
    # 1. Initialize state
    estate = EscapeState(ir, nargs)

    # 2. Mark arguments as ArgEscape
    for i in 1:nargs
        estate[Argument(i)] = ArgEscape()
    end

    # 3. Compute try-catch regions for exception handling
    frameinfo = compute_frameinfo(ir)

    # 4. Iterate backward until convergence
    while changes_made
        for pc in reverse(1:length(ir.stmts))
            analyze_statement!(estate, ir, pc, frameinfo)
        end
    end

    return estate
end
```

### Statement Analysis

Each IR statement type has specific escape behavior:

| Statement Type | Handler | Escape Effect |
|----------------|---------|---------------|
| `ReturnNode` | Direct | `ReturnEscape(pc)` added to returned value |
| `:call` | [`escape_call!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L1073-L1099) | Depends on callee analysis |
| `:invoke` | [`escape_invoke!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L947-L1004) | Uses cached interprocedural info |
| `:new`, `:splatnew` | [`escape_new!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L1140-L1205) | Tracks field aliasing |
| `:foreigncall` | [`escape_foreigncall!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L1027-L1060) | Conservative (may escape) |
| `PhiNode` | [`escape_edges!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L852-L860) | Creates aliases between branches |
| `GlobalRef` | Direct | `AllEscape` (top of lattice) |

### Backward Propagation Illustrated

Consider this IR:

```
%1 = new Point(x, y)
%2 = getfield(%1, :x)
%3 = getfield(%1, :y)
%4 = add(%2, %3)
return %4
```

The analysis proceeds backward:

1. **`return %4`**: `%4` gets `ReturnEscape`. But `%4` is a primitive, so this is fine.
2. **`%4 = add(%2, %3)`**: Addition doesn't capture arguments. No escape propagation.
3. **`%3 = getfield(%1, :y)`**: Field read. Escape of `%3` propagates to the field, not the object.
4. **`%2 = getfield(%1, :x)`**: Same as above.
5. **`%1 = new Point(x, y)`**: `%1` has **no escape** - it can be eliminated!

### Convergence via Fixed-Point Iteration

The algorithm iterates until no changes occur. Each iteration may discover new escapes that propagate to earlier statements. The [propagation functions](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L681-L756) handle this:

- [`propagate_changes!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L681-L694): Drives convergence loop
- [`propagate_escape_change!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L696-L723): Updates escape info and aliases
- [`propagate_liveness_change!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L726-L742): Propagates liveness information
- [`propagate_alias_change!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L745-L756): Merges alias sets

---

## 4. Alias Tracking with Union-Find

A critical challenge in escape analysis is **aliasing**: when two SSA values refer to the same object, they must share escape information. Julia solves this using a **union-find** (disjoint-set) data structure.

### The Union-Find Data Structure

The [`IntDisjointSet`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/disjoint_set.jl) (about 140 lines) provides efficient alias tracking:

```julia
# Conceptual operations
find_root(set, x)      # Find representative of x's equivalence class
union!(set, x, y)      # Merge equivalence classes of x and y
in_same_set(set, x, y) # Check if x and y alias
```

### Why Aliases Matter

Consider:

```julia
function pick(cond, a, b)
    p = cond ? a : b    # p aliases either a or b
    return p
end
```

In SSA form, this becomes a PhiNode:

```
%3 = phi([%1: a], [%2: b])
return %3
```

When `%3` gets `ReturnEscape`, this must propagate to both `a` and `b` because they might alias `%3`.

### Alias Creation Points

Aliases are created at several IR constructs:

| IR Construct | Aliasing Effect |
|--------------|-----------------|
| `PhiNode` | All incoming edges alias the result |
| `PiNode` | Value aliases the result |
| `UpsilonNode` | Value aliases the result |
| `ifelse(c, a, b)` | Both `a` and `b` may alias result |
| Function return | Returned argument may alias return value |

### The AliasInfo Field

Each [`EscapeInfo`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L164-L172) tracks field-level aliasing:

| AliasInfo Value | Meaning |
|-----------------|---------|
| `false` | Not yet analyzed |
| `true` | Cannot be analyzed (unknown type) |
| `IndexableFields` | Field aliases with known indices |
| `Unindexable` | Field aliases without index information |

This enables **field-sensitive analysis**: knowing that `p.x` escapes doesn't mean `p.y` escapes.

### Querying Aliases

Use [`getaliases`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L450-L472) and [`isaliased`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L474-L477):

```julia
aliases = getaliases(ssa_value, estate)  # Get all aliased values
isaliased(val1, val2, estate)            # Check if two values alias
```

---

## 5. Code Examples: What Escapes and What Doesn't

Understanding escape analysis helps you write more efficient code. Here are practical examples.

### Example 1: No Escape (Optimizable)

```julia
struct Point
    x::Float64
    y::Float64
end

function distance_squared(x, y)
    p = Point(x, y)
    return p.x^2 + p.y^2
end
```

**Analysis**: `p` is created, its fields are read, but `p` itself is never returned or stored anywhere. The compiler can eliminate the allocation entirely.

**Result**: Zero heap allocation. The fields `x` and `y` stay in registers.

### Example 2: Return Escape (Not Optimizable)

```julia
function make_point(x, y)
    p = Point(x, y)
    return p  # p escapes here
end
```

**Analysis**: `p` is returned to the caller. The caller might store it in a global, pass it to other functions, or keep it alive indefinitely.

**Result**: Heap allocation required.

### Example 3: Escape via Field (Not Optimizable)

```julia
mutable struct Container
    value::Any
end

const global_container = Container(nothing)

function store_point(x, y)
    p = Point(x, y)
    global_container.value = p  # p escapes via global
    return nothing
end
```

**Analysis**: `p` is stored in a global mutable container. It becomes visible to the entire program.

**Result**: Heap allocation required.

### Example 4: Conditional Escape

```julia
function maybe_return(x, y, return_it::Bool)
    p = Point(x, y)
    if return_it
        return p
    else
        return p.x + p.y
    end
end
```

**Analysis**: `p` *might* escape via return. The compiler must be conservative.

**Result**: Heap allocation required (in general). With constant propagation on `return_it`, one branch might be eliminated.

### Example 5: No Escape Despite Function Call

```julia
function norm(p::Point)
    sqrt(p.x^2 + p.y^2)  # Only reads fields
end

function compute_norm(x, y)
    p = Point(x, y)
    return norm(p)
end
```

**Analysis**: This depends on interprocedural analysis. If `norm` is inlined, the compiler sees that `p` never escapes. The [`ArgEscapeCache`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L504-L523) mechanism caches escape information for callees:

```julia
struct ArgEscapeCache
    argescapes::Vector{ArgEscapeInfo}  # Per-argument escape info
    argaliases::Vector{ArgAliasing}    # Argument aliasing info
end
```

With interprocedural analysis, the compiler knows `norm` doesn't capture `p`.

**Result**: Can be optimized if inlined or with interprocedural analysis.

### Example 6: Thrown Escape

```julia
function validate_point(x, y)
    p = Point(x, y)
    if x < 0 || y < 0
        throw(ArgumentError("Negative coordinates: $p"))
    end
    return p.x + p.y
end
```

**Analysis**: `p` appears in the exception message. Even though the happy path doesn't return `p`, it might be thrown. The compiler tracks this with [`ThrownEscape`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl#L144).

**Result**: Heap allocation required.

---

## 6. How Optimizations Use Escape Information

Escape analysis is not an optimization itself, it enables other optimizations. Here's how the Julia compiler uses escape information.

### 6.1 SROA (Scalar Replacement of Aggregates)

The [SROA pass](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1264-L1579) replaces aggregate allocations with scalar values. It uses escape analysis to determine safety:

```julia
# From passes.jl (conceptually)
estate = EscapeAnalysis.analyze_escapes(ir, nargs, ...)
hasaliases = EscapeAnalysis.getaliases(SSAValue(defidx), estate) !== nothing
einfo = estate[SSAValue(defidx)]

if !hasaliases && EscapeAnalysis.has_no_escape(einfo)
    # Safe to decompose this allocation into scalars
    sroa_mutables!(ir, defidx, ...)
end
```

SROA transforms:
```julia
p = Point(x, y)
result = p.x + p.y
```

Into:
```julia
# p eliminated - fields become local variables
result = x + y
```

### 6.2 Finalizer Inlining

Julia objects can have finalizers that run when the object is garbage collected. If an object doesn't escape, its finalizer can be inlined at a known point rather than running at an unpredictable GC time.

From [`passes.jl:1800-1817`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1800-L1817):

```julia
estate = EscapeAnalysis.analyze_escapes(ir, nargs, ...)
einfo = estate[SSAValue(defidx)]

if !hasaliases && EscapeAnalysis.has_no_escape(einfo)
    # Can inline finalizer - we know exactly when object dies
    inline_finalizer!(ir, defidx, finalizer_func)
end
```

### 6.3 Effect Refinement

The compiler uses escape analysis to refine effect information. If a function only allocates non-escaping mutable objects, those allocations can be considered effect-free.

From [`optimize.jl:686-694`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L686-L694):

```julia
# Effect refinement uses escape analysis
function refine_effects!(sv::OptimizationState, ir::IRCode)
    # Analyze escapes to determine if mutable allocations escape
    estate = analyze_escapes(ir, ...)

    # If mutable allocations don't escape,
    # the function can be considered effect-free
    for stmt in ir.stmts
        if is_mutable_allocation(stmt)
            if !has_no_escape(estate[stmt])
                return  # Cannot refine - allocation escapes
            end
        end
    end

    # All mutable allocations are local - mark as effect-free
    sv.ipo_effects = add_effect_free(sv.ipo_effects)
end
```

---

## 7. Writing Allocation-Free Code

Understanding escape analysis helps you write faster Julia code. Here are practical guidelines.

### Guideline 1: Prefer Immutable Structs

Immutable structs are always easier to optimize:

```julia
# Good: Immutable - compiler can freely copy/eliminate
struct Point
    x::Float64
    y::Float64
end

# Less optimal: Mutable - requires escape analysis
mutable struct MutablePoint
    x::Float64
    y::Float64
end
```

### Guideline 2: Avoid Returning Mutable Objects Created in Function

```julia
# Bad: Creates escaped allocation
function make_pair(x, y)
    return MutablePoint(x, y)
end

# Better: Let caller create, function fills
function fill_pair!(p::MutablePoint, x, y)
    p.x = x
    p.y = y
    return p
end
```

### Guideline 3: Avoid Storing in Globals or Containers with Abstract Element Types

```julia
# Bad: Forces heap allocation due to unknown escape
const results = Any[]
function compute_and_store(x, y)
    p = Point(x, y)
    push!(results, p)  # p escapes
    return p.x + p.y
end

# Better: Return value, let caller decide storage
function compute(x, y)
    p = Point(x, y)
    return p.x + p.y  # p doesn't escape
end
```

### Guideline 4: Use `@inline` for Small Helper Functions

Inlining exposes escape analysis opportunities:

```julia
# Without inlining, escape analysis may be conservative
function helper(p::Point)
    return p.x + p.y
end

# With inlining, escape analysis sees the full picture
@inline function helper(p::Point)
    return p.x + p.y
end
```

### Guideline 5: Avoid Exception Messages That Capture Objects

```julia
# Bad: p escapes via thrown exception
function validate(p::Point)
    p.x < 0 && throw(ArgumentError("Invalid point: $p"))
    return p
end

# Better: Only use primitive values in exception
function validate(p::Point)
    p.x < 0 && throw(ArgumentError("Invalid x coordinate: $(p.x)"))
    return p
end
```

### Guideline 6: Check with @code_llvm

You can verify allocation elimination:

```julia
function sum_point(x, y)
    p = Point(x, y)
    return p.x + p.y
end

@code_llvm debuginfo=:none sum_point(1.0, 2.0)
```

Look for absence of `gc_pool_alloc` or `jl_gc_alloc` calls. If you see them, the allocation wasn't eliminated.

### Guideline 7: Use StaticArrays for Small Fixed-Size Arrays

The standard `Array` always heap-allocates. For small fixed-size arrays, use `StaticArrays.jl`:

```julia
using StaticArrays

# Bad: Always heap allocates
function sum_array(x, y, z)
    arr = [x, y, z]
    return sum(arr)
end

# Good: Stack allocated
function sum_static(x, y, z)
    arr = SVector(x, y, z)
    return sum(arr)
end
```

---

## Summary

Escape analysis is the compiler's tool for answering "does this object need to live on the heap?" The key concepts are:

1. **Escape states** form a lattice from `NoEscape` (optimizable) to `AllEscape` (must heap-allocate)

2. **Backward dataflow** naturally propagates escape information from uses to definitions

3. **Union-find** efficiently tracks which values alias and must share escape status

4. **Optimizations** like SROA and finalizer inlining use escape info to eliminate allocations

5. **Writing efficient code** means understanding what causes escapes and avoiding them

The escape analysis implementation in Julia is self-contained (about 1400 lines in [`EscapeAnalysis.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl)) and provides a solid foundation for allocation optimization. Understanding its principles helps you write faster Julia code and debug performance issues.

---

## Further Reading

- [EscapeAnalysis.jl source](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl) - The full implementation
- [disjoint_set.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/disjoint_set.jl) - Union-find data structure
- [passes.jl SROA section](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1264-L1579) - How SROA uses escape info
- [optimize.jl effect refinement](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L686-L694) - Effect system integration
