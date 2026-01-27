# Julia Compiler Deep Dive: The Type Lattice

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [Why a Lattice?](#1-why-a-lattice)
2. [The Tower of Lattice Layers](#2-the-tower-of-lattice-layers)
3. [Key Lattice Types](#3-key-lattice-types)
4. [Lattice Operations](#4-lattice-operations)
5. [Widening: Ensuring Termination](#5-widening-ensuring-termination)
6. [Putting It Together: A Worked Example](#6-putting-it-together-a-worked-example)
7. [Cross-Reference to Type Inference](#7-cross-reference-to-type-inference)

---

## 1. Why a Lattice?

### The Problem with Native Types Alone

Consider this function:

```julia
function example(x)
    if x > 0
        return 42
    else
        return 3.14
    end
end
```

Julia's type system can determine the return type is `Union{Int64, Float64}`. But what about this?

```julia
function smarter(x)
    y = 42        # We know y is exactly 42, not just Int64
    return y + 1  # Compile-time computable!
end
```

The native type of `y` is `Int64`, but the compiler can do better: it knows `y` is *exactly* `42`. This enables constant folding, turning `y + 1` into `43` at compile time.

Or consider conditional refinement:

```julia
function refined(x::Union{Int, Nothing})
    if x === nothing
        return 0
    else
        return x + 1  # Here x must be Int, not Union{Int, Nothing}!
    end
end
```

Inside the `else` branch, the compiler should know `x` is `Int`, not `Union{Int, Nothing}`. But Julia's type system has no way to express "the type of `x` *after* a branch condition."

### The Solution: A Richer Mathematical Structure

The compiler needs to track information *beyond* what Julia's type system can express:

| What the compiler needs | Native type | Extended lattice element |
|-------------------------|-------------|--------------------------|
| Exact constant value | `Int64` | `Const(42)` |
| Field-level precision | `Pair{Int,Any}` | `PartialStruct(Pair{Int,String}, [Const(1), String])` |
| Branch-conditional types | `Bool` | `Conditional(x, Int, Nothing)` |
| Aliased field tracking | `Union{Int, Nothing}` | `MustAlias(x, Some{...}, 1, Union{Int,Nothing})` |

This richer structure is called a **lattice**. Mathematically, a lattice is a partially ordered set where any two elements have:
- A **least upper bound** (join, written `a v b`)
- A **greatest lower bound** (meet, written `a ^ b`)

The compiler uses lattice theory to:
1. **Precisely track** what's known about each value
2. **Merge information** when control flow paths converge
3. **Guarantee termination** through bounded height

---

## 2. The Tower of Lattice Layers

Julia's type lattice is not monolithic. It's built as a **tower of composable layers**, each adding new capabilities:

```
                    +-----------------------+
                    |   InferenceLattice    |  Adds: LimitedAccuracy
                    |   (recursion limits)  |  (marks widened results)
                    +-----------+-----------+
                                |
              +-----------------+-----------------+
              |                                   |
   +----------+----------+            +-----------+-----------+
   | MustAliasesLattice  |            | ConditionalsLattice   |
   | (field aliasing)    |            | (branch refinement)   |
   +----------+----------+            +-----------+-----------+
              |                                   |
              +-----------------+-----------------+
                                |
                    +-----------+-----------+
                    |   PartialsLattice     |  Adds: PartialStruct, PartialOpaque
                    |   (field precision)   |  (know some fields exactly)
                    +-----------+-----------+
                                |
                    +-----------+-----------+
                    |    ConstsLattice      |  Adds: Const, PartialTypeVar
                    |    (constants)        |  (compile-time known values)
                    +-----------+-----------+
                                |
                    +-----------+-----------+
                    |    JLTypeLattice      |  Base: Julia's native types
                    |    (native types)     |  (Int, String, Union{...}, etc.)
                    +-----------+-----------+
```

### Why Layers?

This design provides **modularity** and **flexibility**:

1. **Different contexts need different lattices**: Local inference needs `Conditional` for branch refinement, but cross-function results use `InterConditional` (no SSA definition tracking needed).

2. **Layer operations compose**: Each layer defines how its elements participate in `tmerge`, `tmeet`, and `sqsubseteq`, delegating to the parent layer for elements it doesn't handle.

3. **Easy to extend**: Adding a new lattice element means adding a new layer, not modifying existing code.

### Standard Lattice Compositions

The compiler uses several pre-built lattice compositions:

```julia
# Simple inference (no conditionals)
const SimpleInferenceLattice = typeof(PartialsLattice(ConstsLattice()))

# Local inference with conditionals
const BaseInferenceLattice = typeof(ConditionalsLattice(PartialsLattice(ConstsLattice())))

# Inter-procedural results (for caching)
const IPOResultLattice = typeof(InterConditionalsLattice(PartialsLattice(ConstsLattice())))

# Full inference lattice (with LimitedAccuracy for recursion)
const InferenceLattice = typeof(InferenceLattice(BaseInferenceLattice.instance))
```

**Source**: [abstractlattice.jl#L82-L98](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractlattice.jl#L82-L98)

---

## 3. Key Lattice Types

### 3.1 `Const` - Compile-Time Constants

The simplest extension: wrapping a known value.

```julia
struct Const
    val
    Const(@nospecialize(v)) = new(v)
end
```

**Source**: [boot.jl#L520-L523](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/boot.jl#L520-L523)

**Example**:
```julia
x = 42  # Compiler tracks: Const(42), not just Int64
```

**What this enables**:
- Constant folding: `x + 1` becomes `Const(43)`
- Dead code elimination: `if x > 100` is known to be false
- More precise method dispatch

**Lattice ordering**: `Const(42) sqsubseteq Int64 sqsubseteq Any`

The constant is more specific (lower in the lattice) than the type.

### 3.2 `PartialStruct` - Field-Level Precision

When you know more about an object's fields than its declared type reveals:

```julia
struct PartialStruct
    typ        # The object's concrete type
    undefs::Array{Union{Nothing,Bool}, 1}  # Field definedness
    fields::Array{Any, 1}  # Lattice elements for each field
end
```

**Source**: [boot.jl#L525-L533](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/boot.jl#L525-L533)

**Example**:
```julia
struct Container
    value::Any
end

c = Container(42)
# Type says: Container (with value::Any)
# Lattice tracks: PartialStruct(Container, [false], [Const(42)])
#                 We know value is exactly 42!
```

**Field definedness (`undefs` array)**:
- `nothing` - definedness is unknown (may or may not be defined)
- `false` - field is definitely defined at runtime
- `true` - field is definitely undefined (impossible state, only for `Union{}` fields)

**What this enables**:
- Precise return types from field access: `c.value` returns `Const(42)`, not `Any`
- Better inlining decisions
- Escape analysis precision

### 3.3 `Conditional` - Branch Refinement

The key to making `if isa(x, T)` actually narrow `x`'s type:

```julia
struct Conditional
    slot::Int      # Which variable this condition tests
    ssadef::Int    # SSA definition for validity tracking
    thentype       # Type in the true branch
    elsetype       # Type in the false branch
    isdefined::Bool # From @isdefined check?
end
```

**Source**: [typelattice.jl#L44-L61](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L44-L61)

**Example**:
```julia
function process(x::Union{Int, String})
    if isa(x, Int)      # Returns Conditional(slot=x, thentype=Int, elsetype=String)
        return x * 2    # x is known to be Int here
    else
        return length(x) # x is known to be String here
    end
end
```

**The flow**:
1. `isa(x, Int)` is evaluated, returning a `Conditional`
2. The `GotoIfNot` statement sees this conditional
3. True branch: `x` is refined to `thentype` (Int)
4. False branch: `x` is refined to `elsetype` (String)

**Why `ssadef`?**: The conditional becomes invalid if `x` is reassigned:

```julia
function tricky(x::Union{Int, String})
    cond = isa(x, Int)  # Conditional created here
    x = "hello"         # x reassigned! SSA def changes
    if cond
        return x * 2    # ERROR: x is now String, not Int
    end
end
```

The `ssadef` tracks which definition of `x` the conditional refers to, preventing unsound refinements after reassignment.

### 3.4 `MustAlias` - Field Aliasing

Tracks when multiple accesses refer to the same field:

```julia
struct MustAlias
    slot::Int      # Parent object's slot
    ssadef::Int    # SSA definition for validity
    vartyp::Any    # Parent object's type
    fldidx::Int    # Which field
    fldtyp::Any    # Field's type
end
```

**Source**: [typelattice.jl#L94-L111](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L94-L111)

**Example**:
```julia
function check_some(x::Some{Union{Int, Nothing}})
    val = x.value  # MustAlias(slot=x, fldidx=1, fldtyp=Union{Int,Nothing})
    if val === nothing
        return 0
    else
        # val is refined to Int
        # AND future accesses to x.value are also Int!
        return val + x.value  # Both are Int
    end
end
```

**Key invariant**: `MustAlias` assumes the field doesn't change. This is valid for:
- `const` fields
- Immutable structs
- Code where no mutation occurs

### 3.5 `LimitedAccuracy` - Recursion Marker

Wraps results that were approximated due to inference recursion limits:

```julia
struct LimitedAccuracy
    typ           # The approximated type
    causes::IdSet{InferenceState}  # What caused the limitation
end
```

**Source**: [typelattice.jl#L208-L216](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L208-L216)

**Why tracking causes matters**:

```julia
function recursive_a(n)
    n <= 0 ? 0 : recursive_b(n-1) + 1
end

function recursive_b(n)
    n <= 0 ? 0 : recursive_a(n-1) + 1
end

function uses_a(x)
    recursive_a(x)  # May get LimitedAccuracy from cycle
end

function uses_b(y)
    recursive_b(y)  # Different call stack, might get better result
end
```

By tracking *which* inference states caused the limitation, different call sites can potentially get more precise results if they don't participate in the problematic cycle.

**Lattice property**: `LimitedAccuracy(T)` is considered epsilon-smaller than `T`. This ensures that:
- Unlimited results are preferred when available
- But the limited result is still usable as an upper bound

### 3.6 `InterConditional` - Inter-Procedural Branch Refinement

A variant of `Conditional` used for inter-procedural cached results:

```julia
struct InterConditional
    slot::Int      # Which argument this condition tests
    thentype       # Type in the true branch
    elsetype       # Type in the false branch
end
```

**Source**: [boot.jl#L535-L540](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/boot.jl#L535-L540)

**Difference from `Conditional`**: `InterConditional` lacks the `ssadef` and `isdefined` fields found in `Conditional`. These fields track local SSA definitions and are not meaningful across function boundaries. When storing inference results in the method cache for later use by callers, `InterConditional` provides the essential branch refinement information without the local context.

**Example**:
```julia
# When caching the return type of:
function is_int(x::Union{Int, String})
    return isa(x, Int)
end

# The cached result uses InterConditional(slot=1, thentype=Int, elsetype=String)
# Callers can use this to refine their argument types after the call
```

### 3.7 `InterMustAlias` - Inter-Procedural Field Aliasing

A variant of `MustAlias` for inter-procedural cached results:

```julia
struct InterMustAlias
    slot::Int      # Which argument contains the aliased field
    vartyp::Any    # Argument's type
    fldidx::Int    # Which field
    fldtyp::Any    # Field's type
end
```

**Source**: [typelattice.jl#L118-L131](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L118-L131)

**Difference from `MustAlias`**: Like `InterConditional`, `InterMustAlias` omits the `ssadef` field since SSA definitions are local to a function's IR. This allows caching field aliasing information that callers can use to refine their understanding of arguments passed to the function.

### 3.8 `PartialOpaque` - Opaque Closure Types

Tracks partial information about opaque closures:

```julia
struct PartialOpaque
    typ            # The opaque closure's declared type
    env            # Captured environment type
    parent         # Parent MethodInstance
    source         # Source CodeInfo
end
```

**Source**: [boot.jl#L542-L548](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/boot.jl#L542-L548)

**What this enables**:
- Precise type inference for opaque closures
- Tracking the captured environment's types
- Enabling inlining and optimization of opaque closure calls

**Example**:
```julia
# For an opaque closure like:
f = @opaque (x::Int) -> x + captured_value

# The compiler may track:
# PartialOpaque with env containing Const(captured_value)
```

### 3.9 `PartialTypeVar` - Partial Type Variable

Tracks partial information about type variables:

```julia
struct PartialTypeVar
    tv::TypeVar    # The TypeVar being tracked
    lb_certain::Bool  # Is the lower bound certain?
    ub_certain::Bool  # Is the upper bound certain?
end
```

**Source**: [typelattice.jl#L142-L149](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L142-L149)

**What this enables**:
- More precise reasoning about type parameters during inference
- Tracking whether bounds on type variables are known exactly or approximated
- Better handling of parametric polymorphism

**Example**:
```julia
# When inferring:
function identity(x::T) where T
    return x
end

# The TypeVar T may be tracked as PartialTypeVar(T, lb_certain=true, ub_certain=false)
# indicating the lower bound is known but the upper bound may be approximated
```

---

## 4. Lattice Operations

The lattice provides three fundamental operations that the type inference engine relies on.

### 4.1 Partial Order: `sqsubseteq` (Is More Specific)

Checks if one lattice element is "below" another (more specific, carries more information):

```julia
function sqsubseteq end
sqsubseteq(::JLTypeLattice, a::Type, b::Type) = a <: b
```

**Source**: [abstractlattice.jl#L144-L154](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractlattice.jl#L144-L154)

**Examples**:

```julia
# Native types: uses Julia's subtyping
Int sqsubseteq Number         # true (Int <: Number)
String sqsubseteq Number      # false

# Constants: more specific than their type
Const(42) sqsubseteq Int      # true
Const(42) sqsubseteq Const(42) # true
Const(42) sqsubseteq Const(43) # false (different values)

# PartialStruct: field-wise comparison
PartialStruct(Pair, [Const(1), String]) sqsubseteq Pair{Int,String}  # true
PartialStruct(Pair, [Const(1), String]) sqsubseteq PartialStruct(Pair, [Int, String])  # true

# LimitedAccuracy: epsilon smaller
LimitedAccuracy(Int) sqsubseteq Int  # true (just barely)
Int sqsubseteq LimitedAccuracy(Int)  # false!
```

**Layer implementations**:

| Layer | Location | Rule |
|-------|----------|------|
| `JLTypeLattice` | abstractlattice.jl:153 | `a <: b` |
| `ConstsLattice` | typelattice.jl:532-552 | Same value and type |
| `PartialsLattice` | typelattice.jl:454-530 | Field-wise `sqsubseteq` |
| `ConditionalsLattice` | typelattice.jl:414-439 | Same slot, types compatible |
| `InferenceLattice` | typelattice.jl:395-412 | Handle `LimitedAccuracy` wrapper |

### 4.2 Join: `tmerge` (Combine Information)

Computes an upper bound when control flow paths merge:

```julia
function tmerge end
```

**Source**: [abstractlattice.jl#L117-L125](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractlattice.jl#L117-L125)

**Example - control flow merge**:

```julia
function branching(cond)
    if cond
        x = 42      # Const(42)
    else
        x = 100     # Const(100)
    end
    return x        # tmerge(Const(42), Const(100)) = Int
end
```

Both branches give constants, but different ones. The join must find a common upper bound: `Int`.

**Example - PartialStruct merge**:

```julia
function struct_merge(cond)
    if cond
        p = Pair(1, "hello")  # PartialStruct(Pair, [Const(1), Const("hello")])
    else
        p = Pair(1, "world")  # PartialStruct(Pair, [Const(1), Const("world")])
    end
    return p  # PartialStruct(Pair, [Const(1), String])
              # First field stays Const(1), second widens to String
end
```

The `tmerge` operation merges field-by-field, preserving precision where possible.

**Example - Conditional merge**:

```julia
function cond_merge(x::Union{Int,String,Float64}, flag)
    if flag
        cond = isa(x, Int)     # Conditional(x, Int, Union{String,Float64})
    else
        cond = isa(x, String)  # Conditional(x, String, Union{Int,Float64})
    end
    # tmerge gives: Conditional(x, Union{Int,String}, Union{Int,String,Float64})
    # (thentype = tmerge of thentypes, elsetype = tmerge of elsetypes)
end
```

**Important**: `tmerge` is **not the least upper bound**. It applies complexity limits and may widen more than strictly necessary. This is intentional for termination (see Section 5).

**Layer implementations**:

| Layer | Location | Key Logic |
|-------|----------|-----------|
| `JLTypeLattice` | typelimits.jl:736-750 | Type union with limits |
| `ConstsLattice` | typelimits.jl:724-734 | Widen if different constants |
| `PartialsLattice` | typelimits.jl:678-722 | Field-wise merge |
| `ConditionalsLattice` | typelimits.jl:499-537 | Merge if same slot |
| `MustAliasesLattice` | typelimits.jl:579-589 | Widen to field type |

### 4.3 Meet: `tmeet` (Intersect Information)

Computes a lower bound, typically for type refinement:

```julia
function tmeet end
tmeet(::JLTypeLattice, a::Type, b::Type) =
    (ti = typeintersect(a, b); valid_as_lattice(ti, true) ? ti : Bottom)
```

**Source**: [abstractlattice.jl#L99-L114](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractlattice.jl#L99-L114)

**Example - type refinement after branch**:

```julia
function refine(x::Union{Int, String, Nothing})
    if x !== nothing
        # tmeet(Union{Int,String,Nothing}, Union{Int,String}) = Union{Int,String}
        return process(x)
    end
end
```

**Example - constant meet**:

```julia
# tmeet(Const(42), Int) = Const(42)  # Constant is already Int
# tmeet(Const(42), String) = Bottom  # 42 is not a String
```

**Layer implementations** (typelattice.jl:624-706):
- `PartialsLattice`: Intersect field types element-wise
- `ConstsLattice`: Check if constant matches the type
- `ConditionalsLattice`: Require `Bool <: t` for the meet to be valid

### 4.4 Widening: `widenconst`

Converts extended lattice elements back to native Julia types:

```julia
widenconst(x) -> Type
```

**Source**: [typelattice.jl#L708-L722](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl#L708-L722)

| Input | Output |
|-------|--------|
| `Const(42)` | `Int64` |
| `Const(Int)` | `Type{Int}` |
| `PartialStruct(Pair{Int,String}, ...)` | `Pair{Int,String}` |
| `Conditional(...)` | `Bool` |
| `MustAlias(..., fldtyp=T)` | `widenconst(T)` |

This is used when storing results in the cache (which uses native types) or when lattice precision is no longer needed.

---

## 5. Widening: Ensuring Termination

### The Termination Problem

Type inference must terminate. But consider:

```julia
function problem(x)
    if rand() > 0.5
        return x
    else
        return (x,)  # Wraps x in a tuple
    end
end

# Calling problem(1):
# - First iteration: Union{Int, Tuple{Int}}
# - If we call problem again: Union{Int, Tuple{Int}, Tuple{Tuple{Int}}}
# - And again: Union{Int, Tuple{Int}, Tuple{Tuple{Int}}, Tuple{Tuple{Tuple{Int}}}}
# - Forever...
```

Without intervention, types can grow unboundedly. The compiler needs **widening rules** to ensure finite convergence.

### Complexity Parameters

```julia
const MAX_TYPEUNION_COMPLEXITY = 3
const MAX_TYPEUNION_LENGTH = 3
```

**Source**: [typelimits.jl#L7-L8](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl#L7-L8)

- **Complexity**: Nesting depth of type parameters
- **Length**: Number of elements in a union

### The Core Widening Function: `limit_type_size`

```julia
function limit_type_size(t, compare, source, allowed_tupledepth, allowed_tuplelen)
```

**Source**: [typelimits.jl#L17-L33](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl#L17-L33)

**Algorithm**:
1. Check if `t` is more complex than `compare` via `type_more_complex`
2. If so, apply `_limit_type_size` to simplify
3. Ensure `t <: result` (the widening is sound)

**Example**:

```julia
# Original: Tuple{Tuple{Tuple{Int}}}  (depth 3)
# Limit with depth 2: Tuple{Tuple{Any}}
# The inner Tuple{Int} is replaced with Any
```

### Complexity Detection: `type_more_complex`

**Source**: [typelimits.jl#L223-L307](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl#L223-L307)

Checks:
- Union nesting depth
- Tuple nesting depth
- Whether type parameters appear in known sources
- TypeVar complexity

### Simplicity Checks

```julia
function issimpleenoughtype(t)
    max(unionlen(t), union_count_abstract(t) + 1) <= MAX_TYPEUNION_LENGTH &&
    unioncomplexity(t) <= MAX_TYPEUNION_COMPLEXITY
end
```

**Source**: [typelimits.jl#L312-L317](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl#L312-L317)

### Tuple Merging: `tuplemerge`

Special handling for tuples to prevent explosion:

**Source**: [typelimits.jl#L896-L975](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelimits.jl#L896-L975)

```julia
# Same length: merge element-wise
tmerge(Tuple{Int,String}, Tuple{Float64,String}) = Tuple{Union{Int,Float64}, String}

# Different lengths: collapse to Vararg
tmerge(Tuple{Int}, Tuple{Int,Int}) = Tuple{Int,Vararg{Int}}
```

### Non-Associativity of `tmerge`

**Important**: `tmerge` is intentionally **not associative**:

```julia
tmerge(a, tmerge(b, c)) != tmerge(tmerge(a, b), c)  # Possibly!
```

This is because complexity limits can kick in at different points. The compiler handles this by being careful about merge order and accepting that results may vary slightly.

---

## 6. Putting It Together: A Worked Example

Let's trace through how the lattice is used during type inference:

```julia
function example(x::Union{Int, Nothing})
    if x === nothing
        return 0
    else
        return x + 1
    end
end
```

### Step 1: Initial State

```
x :: VarState(typ=Union{Int, Nothing}, ssadef=0, undef=false)
```

### Step 2: Evaluate `x === nothing`

The comparison `x === nothing` triggers special handling. The compiler recognizes this as a type-narrowing comparison and produces:

```
Conditional(slot=1, ssadef=0, thentype=Nothing, elsetype=Int, isdefined=false)
```

### Step 3: Branch on GotoIfNot

The `GotoIfNot` sees the `Conditional` and:

**True branch** (condition is true, `x === nothing`):
```
x :: VarState(typ=Nothing, ...)
```

**False branch** (condition is false, `x !== nothing`):
```
x :: VarState(typ=Int, ...)  # Refined from Union{Int,Nothing}!
```

### Step 4: Evaluate Branches

**True branch**: `return 0`
- Return type: `Const(0)`

**False branch**: `return x + 1`
- `x` is known to be `Int`
- `x + 1` infers to `Int` (or `Const` if x was constant)
- Return type: `Int`

### Step 5: Merge Return Types

```julia
tmerge(Const(0), Int) = Int
```

The final return type is `Int`.

### The Lattice Operations Used

| Operation | Where | What |
|-----------|-------|------|
| `Conditional` creation | `x === nothing` | Encode branch information |
| `tmeet` | Branch refinement | `tmeet(Union{Int,Nothing}, Int) = Int` |
| `tmerge` | Return type | `tmerge(Const(0), Int) = Int` |
| `sqsubseteq` | Convergence check | Verify types are stable |

---

## 7. Cross-Reference to Type Inference

The type lattice is the mathematical foundation that the type inference engine (T1) builds upon.

### How Type Inference Uses the Lattice

| Inference Operation | Lattice Operation | Purpose |
|---------------------|-------------------|---------|
| Join at phi nodes | `tmerge` | Merge types from different paths |
| Branch refinement | `Conditional` + `tmeet` | Narrow types in branches |
| Convergence check | `sqsubseteq` | Detect when inference is done |
| Return type accumulation | `tmerge` on `bestguess` | Combine all return paths |
| Cache storage | `widenconst` | Convert to native types |

### Key Integration Points

**From typeinfer.jl**:
```julia
# Get the lattice for the current interpreter
lattice = typeinf_lattice(interp)

# Merge types at control flow join
new_type = tmerge(lattice, old_type, incoming_type)

# Check if type changed (for worklist)
if !(new_type sqsubseteq lattice old_type)
    # Need to re-analyze
end
```

**From abstractinterpretation.jl**:
```julia
# Branch handling with Conditional
if isa(condt, Conditional) && condt.slot == slot_id
    # True branch
    refined = tmeet(lattice, current_type, condt.thentype)
    # False branch
    refined = tmeet(lattice, current_type, condt.elsetype)
end
```

### The Lattice Hierarchy in Action

```
Source code → Type Inference (T1)
                    ↓
              Uses lattice operations from (T2):
              - tmerge for joins
              - tmeet for meets
              - sqsubseteq for ordering
              - Const, PartialStruct, etc. for precision
                    ↓
              Calls tfuncs (T3) for builtin return types
                    ↓
              Tracks effects (T7)
                    ↓
              Stores results via widenconst → Cache (T8)
```

For the complete type inference algorithm, see the [Type Inference tutorial (T1)](./01-type-inference.md).

---

## Summary

The type lattice provides a rigorous mathematical foundation for Julia's type inference:

| Concept | Purpose |
|---------|---------|
| **Lattice elements** | Represent compile-time knowledge beyond native types |
| **Layer tower** | Composable design for different contexts |
| **`Const`** | Track exact values |
| **`PartialStruct`** | Track field-level precision |
| **`Conditional`** | Enable branch refinement |
| **`MustAlias`** | Track field aliasing |
| **`LimitedAccuracy`** | Mark recursion-limited results |
| **`tmerge`** | Combine information at joins |
| **`tmeet`** | Intersect for refinement |
| **`sqsubseteq`** | Check precision ordering |
| **Widening** | Ensure termination |

This foundation enables Julia to perform sophisticated type inference while guaranteeing that compilation always terminates in reasonable time.

---

## Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `Compiler/src/typelattice.jl` | ~800 | Lattice type definitions and `sqsubseteq` |
| `Compiler/src/typelimits.jl` | ~980 | `tmerge`, widening rules |
| `Compiler/src/abstractlattice.jl` | ~320 | Layer definitions, operation dispatch |
| `Compiler/src/typeutils.jl` | ~350 | Helper functions |
| `base/boot.jl` | Core types | `Const`, `PartialStruct` definitions |

---

## Further Reading

- **Type Inference (T1)**: How inference uses the lattice to analyze programs
- **tfuncs (T3)**: How builtin functions use lattice types for return type computation
- **Effects (T7)**: The parallel system for tracking computational effects
