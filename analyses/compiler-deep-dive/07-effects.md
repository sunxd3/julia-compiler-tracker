# Julia Compiler Deep Dive: The Effects System

How Julia tracks code purity to enable aggressive optimizations.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [What Are Effects?](#1-what-are-effects)
2. [The Nine Effect Properties](#2-the-nine-effect-properties)
3. [How Effects Enable Optimizations](#3-how-effects-enable-optimizations)
4. [The `@assume_effects` Macro](#4-the-assume_effects-macro)
5. [Effect Inference During Type Inference](#5-effect-inference-during-type-inference)
6. [Checking Effects of Your Code](#6-checking-effects-of-your-code)
7. [Advanced Topics](#7-advanced-topics)
8. [Quick Reference](#8-quick-reference)

---

## 1. What Are Effects?

When Julia compiles your code, it doesn't just figure out the *types* of values flowing through your program. It also analyzes the *computational properties* of each operation: Does this function always return the same result for the same inputs? Can it throw an exception? Does it modify global state?

These properties are called **effects**. Understanding effects answers a fundamental question: *What can the compiler safely assume about this code?*

Consider this simple example:

```julia
function square(x::Int)
    return x * x
end
```

The compiler can prove several things about `square`:
- It always returns the same result for the same input (`consistent`)
- It has no side effects (`effect_free`)
- It never throws an exception (`nothrow`)
- It always terminates (`terminates`)

With these guarantees, the compiler can safely:
- Evaluate `square(5)` at compile time instead of runtime
- Eliminate `y = square(3)` entirely if `y` is never used
- Reorder `square` calls freely without changing program behavior

Effects are tracked in the [`Effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L119-L150) struct, which contains nine distinct properties:

```julia
struct Effects
    consistent::UInt8
    effect_free::UInt8
    nothrow::Bool
    terminates::Bool
    notaskstate::Bool
    inaccessiblememonly::UInt8
    noub::UInt8
    nonoverlayed::UInt8
    nortcall::Bool
end
```

---

## 2. The Nine Effect Properties

Each effect property captures a specific guarantee about code behavior. Let's explore each one with practical examples.

### 2.1 `consistent` - Same Inputs, Same Outputs

**Definition**: A function is `:consistent` if calling it with the same arguments always produces the same result.

```julia
# Consistent: Pure mathematical functions
sin(1.0)              # Always returns the same value
string(42)            # Deterministic conversion

# NOT consistent: Functions with observable non-determinism
rand()                # Different result each time
time()                # Depends on when called
objectid(x)           # Depends on memory allocation
```

**Why it matters**: Consistent functions can have their results cached and reused. If `f(x)` is consistent and the compiler sees `f(x) + f(x)`, it can compute `f(x)` once and double the result.

**Multi-state values**: The `consistent` field is a `UInt8` because it can have conditional states:

| Value | Constant | Meaning |
|-------|----------|---------|
| `0x00` | `ALWAYS_TRUE` | Guaranteed consistent |
| `0x01` | `ALWAYS_FALSE` | May be inconsistent |
| `0x02` | `CONSISTENT_IF_NOTRETURNED` | Consistent if mutable allocations don't escape |
| `0x04` | `CONSISTENT_IF_INACCESSIBLEMEMONLY` | Consistent if only internal memory is accessed |

The conditional states allow the compiler to defer decisions. For example, a function that allocates a mutable object internally might still be consistent if that object never escapes to the caller.

### 2.2 `effect_free` - No Observable Side Effects

**Definition**: A function is `:effect_free` if it doesn't produce any externally observable side effects.

```julia
# Effect-free: No external state changes
sum([1, 2, 3])        # Computes a value, nothing else
Dict(:a => 1)[:a]     # Reads from dict, doesn't modify it

# NOT effect-free: Modifies external state
push!(arr, x)         # Modifies the array
println("hello")      # Writes to stdout (external)
global_var[] = 1      # Modifies global state
```

**Key insight**: Allocating memory is *not* considered a side effect for `effect_free`. A function can allocate freely and still be effect-free, as long as it doesn't modify pre-existing external state.

**Why it matters**: Effect-free functions can be removed entirely if their result isn't used. The compiler performs Dead Code Elimination (DCE) on effect-free code.

**Multi-state values**:

| Value | Constant | Meaning |
|-------|----------|---------|
| `0x00` | `ALWAYS_TRUE` | Completely effect-free |
| `0x01` | `ALWAYS_FALSE` | May have side effects |
| `0x02` | `EFFECT_FREE_IF_INACCESSIBLEMEMONLY` | Effect-free if only internal memory is accessed |
| `0x03` | `EFFECT_FREE_GLOBALLY` | Effect-free globally but not removable within function |

### 2.3 `nothrow` - Never Throws Exceptions

**Definition**: A function is `:nothrow` if it is guaranteed never to throw an exception.

```julia
# Nothrow: Guaranteed success
1 + 1                 # Integer addition can't fail
length([1,2,3])       # Always works on arrays

# May throw: Potential exceptions
arr[i]                # BoundsError if i out of range
parse(Int, s)         # ArgumentError if s invalid
open(filename)        # SystemError if file doesn't exist
1 / x                 # DivideError if x == 0 for integers
```

**Why it matters**: If a function is nothrow, the compiler can:
- Remove exception handling code around the call
- Delete the call entirely if it's also effect-free (no need to preserve potential exceptions)
- Simplify control flow analysis

### 2.4 `terminates` - Always Completes

**Definition**: A function is `:terminates` if it always finishes execution (no infinite loops).

```julia
# Terminates: Bounded computation
map(x -> x^2, 1:10)   # Finite iteration
foldl(+, 1:100)       # Finite reduction

# May not terminate: Potentially infinite
while true end        # Infinite loop
recursive_search(tree) # Might not halt on cyclic structures
```

**Why it matters**: A function must terminate for its result to be computed at compile time. Even if a function is consistent and effect-free, the compiler cannot evaluate it at compile time if it might run forever.

**Practical note**: The compiler is conservative about termination. It typically cannot prove termination for user-defined loops unless annotated.

### 2.5 `notaskstate` - No Task-Local State Access

**Definition**: A function is `:notaskstate` if it doesn't access state bound to the current task.

```julia
# No task state: Independent of execution context
sin(1.0)              # Pure computation
Dict(:a => 1)         # Local allocation

# Uses task state: Depends on current task
current_task()        # Accesses task identity
task_local_storage()  # Task-local data
yield()               # Interacts with scheduler
```

**Why it matters**: Functions that don't access task state can have their results migrated between tasks. This is important for:
- Finalizer inlining (finalizers run on arbitrary tasks)
- Work stealing in parallel contexts
- Caching results across task boundaries

### 2.6 `inaccessiblememonly` - Only Internal Memory Access

**Definition**: A function only accesses memory that is "inaccessible" to the rest of the program (like stack allocations or locally allocated heap memory).

```julia
# Inaccessible memory only: Local allocations
function foo(x)
    arr = [x, x+1, x+2]  # Local array
    return sum(arr)       # Access local memory only
end

# Accesses external memory: Reads/writes caller-visible state
function bar(arr)
    return arr[1]         # Reads memory passed by caller
end
```

**Multi-state values**:

| Value | Constant | Meaning |
|-------|----------|---------|
| `0x00` | `ALWAYS_TRUE` | Only accesses inaccessible memory (LLVM's `inaccessiblememonly`) |
| `0x01` | `ALWAYS_FALSE` | May access external memory |
| `0x02` | `INACCESSIBLEMEM_OR_ARGMEMONLY` | Only accesses inaccessible or argument memory |

**Why it matters**: This property helps with alias analysis and escape analysis. If a function only touches its own local memory, the compiler can be more aggressive about optimizations like stack allocation and register promotion.

### 2.7 `noub` - No Undefined Behavior

**Definition**: A function is `:noub` if it never executes undefined behavior (like out-of-bounds memory access in unsafe code).

```julia
# No UB: Safe operations
arr[i]                # Bounds-checked access
@inbounds arr[i]      # May have UB if i out of bounds!

# Potential UB: Unsafe operations
unsafe_load(ptr)      # No bounds checking
ccall with wrong types # Memory corruption possible
```

**Multi-state values**:

| Value | Constant | Meaning |
|-------|----------|---------|
| `0x00` | `ALWAYS_TRUE` | No undefined behavior |
| `0x01` | `ALWAYS_FALSE` | May have undefined behavior |
| `0x02` | `NOUB_IF_NOINBOUNDS` | No UB if `@boundscheck` is not elided |

**Why it matters**: Undefined behavior invalidates all compiler assumptions. A function with potential UB cannot be safely optimized, as UB allows the compiler to assume "this path is never taken."

The `NOUB_IF_NOINBOUNDS` state is common: code is safe when bounds checking is enabled, but may have UB if `@inbounds` is applied by a caller.

### 2.8 `nonoverlayed` - No Method Table Overlays

**Definition**: A function is `:nonoverlayed` if it doesn't invoke methods from overlay method tables.

```julia
# Typical case: Normal method dispatch
f(x) = x + 1          # Uses standard method tables

# Overlayed: Custom dispatch via overlays
# (Used in specialized contexts like GPU compilation)
```

**Why it matters**: Method overlays allow replacing methods for specialized compilation contexts (like GPU code). A function marked `:nonoverlayed` can have its results cached and reused across contexts that don't use overlays.

**Multi-state values**:

| Value | Constant | Meaning |
|-------|----------|---------|
| `0x00` | `ALWAYS_TRUE` | No overlayed methods invoked |
| `0x01` | `ALWAYS_FALSE` | May invoke overlayed methods |
| `0x02` | `CONSISTENT_OVERLAY` | May invoke overlays, but they are consistent with originals |

### 2.9 `nortcall` - No `return_type` Calls

**Definition**: A function is `:nortcall` if it doesn't call `Core.Compiler.return_type` or similar type inference introspection.

```julia
# No rtcall: Typical code
f(x) = x + 1

# Uses rtcall: Type introspection
g(f, x) = Core.Compiler.return_type(f, (typeof(x),))
```

**Why it matters**: Calling `return_type` during compilation can create circular dependencies and interfere with caching. Functions that don't use this feature can be optimized more aggressively.

---

## 3. How Effects Enable Optimizations

The effects system is not just bookkeeping; it directly enables powerful compiler optimizations. Let's see how each combination of effects unlocks specific optimizations.

### 3.1 Dead Code Elimination (DCE)

**Required effects**: `effect_free` + `nothrow` + `terminates`

When a statement has no side effects, can't throw, and always completes, the compiler can remove it if its result is unused.

```julia
function example(x)
    y = expensive_pure_function(x)  # If unused, can be removed
    z = 2 * x
    return z
end
```

The check for removability is implemented in [`is_removable_if_unused`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L320-L323):

```julia
function is_removable_if_unused(effects::Effects)
    return is_effect_free(effects) && is_nothrow(effects) && is_terminates(effects)
end
```

### 3.2 Constant Folding (Compile-Time Evaluation)

**Required effects**: `consistent` + `effect_free` + `terminates` + `noub`

When a function is pure and the compiler knows all its inputs at compile time, it can evaluate the function during compilation and replace the call with its result.

```julia
const MAGIC = factorial(10)  # Computed at compile time!
```

The check for foldability is in [`is_foldable`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L308-L313):

```julia
is_foldable(effects::Effects, check_rtcall::Bool=false) =
    is_consistent(effects) &&
    (is_noub(effects) || is_noub_if_noinbounds(effects)) &&
    is_effect_free(effects) &&
    is_terminates(effects) &&
    (!check_rtcall || is_nortcall(effects))
```

There is also a related function `is_foldable_nothrow` which combines `is_foldable` with `is_nothrow`:

```julia
is_foldable_nothrow(effects::Effects, check_rtcall::Bool=false) =
    is_foldable(effects, check_rtcall) &&
    is_nothrow(effects)
```

### 3.3 Concrete Evaluation

When effects permit, the compiler can actually *run* function calls during type inference. This is done in [`abstract_call_known`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl#L938-L948):

```julia
if result.edge !== nothing && is_foldable(effects, #=check_rtcall=#true)
    if (is_nonoverlayed(interp) || is_nonoverlayed(effects) ||
        is_consistent_overlay(effects))
        # Can perform concrete evaluation at compile time
    end
end
```

### 3.4 Finalizer Inlining

**Required effects**: `nothrow` + `notaskstate`

Finalizers (cleanup code for garbage-collected objects) can be inlined if they're safe to run on any task and don't throw exceptions. The check is in [`is_finalizer_inlineable`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L325-L327):

```julia
function is_finalizer_inlineable(effects::Effects)
    return is_nothrow(effects) && is_notaskstate(effects)
end
```

### 3.5 Common Subexpression Elimination (CSE)

**Required effects**: `consistent`

If a function is consistent, duplicate calls with the same arguments can be merged:

```julia
# Before optimization
a = expensive_consistent_fn(x)
b = expensive_consistent_fn(x)  # Same call

# After CSE (if consistent)
tmp = expensive_consistent_fn(x)
a = tmp
b = tmp
```

### 3.6 IR Flags for Per-Statement Optimization

Effects are converted to IR flags for per-statement optimization via [`flags_for_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L72-L98):

| IR Flag | Effect | Bit Position |
|---------|--------|--------------|
| `IR_FLAG_CONSISTENT` | `:consistent` | 1 << 3 |
| `IR_FLAG_EFFECT_FREE` | `:effect_free` | 1 << 4 |
| `IR_FLAG_NOTHROW` | `:nothrow` | 1 << 5 |
| `IR_FLAG_TERMINATES` | `:terminates` | 1 << 6 |
| `IR_FLAG_NOUB` | `:noub` | 1 << 10 |
| `IR_FLAG_NORTCALL` | `:nortcall` | 1 << 13 |

Combined flags:
- `IR_FLAGS_REMOVABLE` = `EFFECT_FREE | NOTHROW | TERMINATES` - enables DCE

---

## 4. The `@assume_effects` Macro

Sometimes the compiler cannot prove effects that you, as the programmer, know to be true. The `@assume_effects` macro lets you assert these properties, enabling optimizations that would otherwise be blocked.

### 4.1 Basic Usage

```julia
Base.@assume_effects :total function my_pure_fn(x::Int)
    # Complex but pure computation
    return complicated_but_deterministic(x)
end
```

### 4.2 Available Effect Annotations

| Annotation | Effect | Meaning |
|------------|--------|---------|
| `:consistent` | `consistent` | Same inputs always produce same outputs |
| `:effect_free` | `effect_free` | No externally visible side effects |
| `:nothrow` | `nothrow` | Never throws exceptions |
| `:terminates_globally` | `terminates` | Always terminates |
| `:terminates_locally` | - | Terminates if callees terminate |
| `:notaskstate` | `notaskstate` | Doesn't access task-local state |
| `:inaccessiblememonly` | `inaccessiblememonly` | Only accesses local memory |
| `:noub` | `noub` | No undefined behavior |
| `:nortcall` | `nortcall` | Doesn't call `Core.Compiler.return_type` (and callees don't either) |
| `:foldable` | multiple | Shorthand for constant-foldable |
| `:removable` | multiple | Shorthand for DCE-eligible |
| `:total` | all | All effects guaranteed |

### 4.3 Shorthand Combinations

```julia
# :foldable is equivalent to:
# :consistent, :effect_free, :terminates_globally, :noub, :nortcall
#
# Note: :foldable does NOT imply :nothrow. Constant folding may still record
# a thrown error at compile time if it is consistent for the given inputs.

# :removable is equivalent to:
# :effect_free, :nothrow, :terminates_globally

# :total is equivalent to:
# :consistent, :effect_free, :nothrow, :terminates_globally, :notaskstate,
# :inaccessiblememonly, :noub, :nortcall
```

### 4.4 Practical Examples

**Example 1: Recursive function with provable termination**

```julia
# Compiler can't prove termination for recursive functions
Base.@assume_effects :terminates_globally function fib(n::Int)
    n <= 1 && return n
    return fib(n-1) + fib(n-2)
end
```

**Example 2: External library call that you know is pure**

```julia
# Calling into C code - compiler can't analyze it
Base.@assume_effects :total function external_hash(data::Vector{UInt8})
    ccall(:my_hash_function, UInt64, (Ptr{UInt8}, Csize_t), data, length(data))
end
```

**Example 3: Complex but deterministic computation**

```julia
Base.@assume_effects :foldable function compile_time_table_lookup(idx::Int)
    table = [precomputed_values...]  # Expensive but constant
    return table[idx]
end
```

### 4.5 Caution: Effect Assertions Are Promises

**WARNING**: If you assert effects that are incorrect, you create undefined behavior. The compiler will optimize based on your assertions, potentially causing:
- Incorrect results
- Crashes
- Security vulnerabilities

Only use `@assume_effects` when you are **absolutely certain** of the properties.

```julia
# DANGEROUS: This assertion is FALSE
Base.@assume_effects :nothrow function bad_example(x)
    return 1 / x  # Throws DivideError when x == 0!
end
```

### 4.6 Override Implementation

Effect overrides are applied in [`override_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/abstractinterpretation.jl#L3594-L3606):

```julia
function override_effects(effects::Effects, override::EffectsOverride)
    return Effects(effects;
        consistent = override.consistent ? ALWAYS_TRUE : effects.consistent,
        effect_free = override.effect_free ? ALWAYS_TRUE : effects.effect_free,
        nothrow = override.nothrow ? true : effects.nothrow,
        # ... other effects
    )
end
```

---

## 5. Effect Inference During Type Inference

Effects aren't just declared; they're *inferred* by the compiler during type inference. Let's trace how this works.

### 5.1 Initialization

When type inference begins for a method, effects start at the best possible state ([`EFFECTS_TOTAL`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L178)):

```julia
const EFFECTS_TOTAL = Effects(
    ALWAYS_TRUE,   # consistent
    ALWAYS_TRUE,   # effect_free
    true,          # nothrow
    true,          # terminates
    true,          # notaskstate
    ALWAYS_TRUE,   # inaccessiblememonly
    ALWAYS_TRUE,   # noub
    ALWAYS_TRUE,   # nonoverlayed
    true           # nortcall
)
```

This is the "innocent until proven guilty" approach: assume everything is pure until evidence proves otherwise.

Special cases immediately taint effects ([`InferenceState` initialization](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/inferencestate.jl#L375-L397)):

```julia
ipo_effects = EFFECTS_TOTAL
# Code coverage insertion taints effect_free
if insert_coverage
    ipo_effects = Effects(ipo_effects; effect_free = ALWAYS_FALSE)
end
```

### 5.2 Statement-Level Analysis

As type inference processes each statement, it computes statement-level effects and merges them into the method's overall effects.

**For function calls**: Effects come from the callee's inferred effects via `abstract_call_known` or `abstract_call_unknown`.

**For builtins**: Effects are computed by [`builtin_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2631-L2709). Each builtin has known effect properties:

```julia
# getfield is usually effect-free but may throw
# setfield! is definitely not effect-free
# typeof is completely pure
```

**For intrinsics**: Effects are computed by [`intrinsic_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L3060-L3079). Low-level intrinsics have carefully categorized effects.

### 5.3 Effect Merging

Effects from each statement are merged into the method's inter-procedural (IPO) effects using [`merge_effects!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/inferencestate.jl#L1060-L1067):

```julia
function merge_effects!(::AbstractInterpreter, caller::InferenceState, effects::Effects)
    if effects.effect_free === EFFECT_FREE_GLOBALLY
        effects = Effects(effects; effect_free=ALWAYS_TRUE)
    end
    caller.ipo_effects = merge_effects(caller.ipo_effects, effects)
end
```

The [`merge_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L275-L286) function combines effects conservatively:

```julia
function merge_effectbits(old::UInt8, new::UInt8)
    if old === ALWAYS_FALSE || new === ALWAYS_FALSE
        return ALWAYS_FALSE  # Once tainted, always tainted
    end
    return old | new  # Accumulate conditional bits
end

merge_effectbits(old::Bool, new::Bool) = old & new  # AND for boolean
```

**Key insight**: Effects can only get worse, never better. Once a single statement taints an effect, the whole method is tainted for that effect.

### 5.4 Post-Inference Refinement

After inference completes, effects may be refined based on the inferred return type ([`adjust_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typeinfer.jl#L567-L622)):

```julia
# If return type doesn't contain mutable objects,
# conditional consistency can be upgraded
if is_consistent_if_notreturned(ipo_effects) && is_identity_free_argtype(rt)
    consistent = ipo_effects.consistent & ~CONSISTENT_IF_NOTRETURNED
    ipo_effects = Effects(ipo_effects; consistent)
end
```

This allows the compiler to resolve conditional effects like `CONSISTENT_IF_NOTRETURNED` once it knows what type is actually returned.

### 5.5 Architecture Diagram

```
                    +------------------+
                    |  @assume_effects |
                    | (user overrides) |
                    +--------+---------+
                             |
                             v
+----------------+   +-------+--------+   +------------------+
| builtin_effects|-->|  merge_effects!|<--| intrinsic_effects|
| (tfuncs.jl)    |   | (per statement)|   | (tfuncs.jl)      |
+----------------+   +-------+--------+   +------------------+
                             |
                             v
                    +--------+---------+
                    | ipo_effects      |
                    | (InferenceState) |
                    +--------+---------+
                             |
                             v
                    +--------+---------+
                    | adjust_effects   |
                    | (typeinfer.jl)   |
                    +--------+---------+
                             |
            +----------------+----------------+
            v                                 v
    +-------+--------+               +--------+-------+
    | encode_effects |               | flags_for_     |
    | (CodeInstance) |               | effects (IR)   |
    +----------------+               +--------+-------+
                                              |
                                              v
                                     +--------+-------+
                                     | Optimizations  |
                                     | - DCE          |
                                     | - Const fold   |
                                     | - Inlining     |
                                     +----------------+
```

---

## 6. Checking Effects of Your Code

Julia provides tools to inspect the effects of your functions, helping you understand what optimizations are possible.

### 6.1 Using `Base.infer_effects`

The primary way to check effects is `Base.infer_effects`:

```julia
julia> Base.infer_effects(sin, (Float64,))
(+c,+e,+n,+t,+s,+m,+u,+o,+r)

julia> Base.infer_effects(println, (String,))
(-c,-e,-n,+t,-s,-m,+u,+o,+r)
```

### 6.2 Reading the Effect String

Effects are displayed as a compact string: `+c+e+n+t+s+m+u+o+r`

| Symbol | Effect | `+` means | `-` means | `?` means |
|--------|--------|-----------|-----------|-----------|
| `c` | consistent | Always consistent | May be inconsistent | Conditionally consistent |
| `e` | effect_free | Effect-free | Has side effects | Conditionally effect-free |
| `n` | nothrow | Never throws | May throw | - |
| `t` | terminates | Always terminates | May not terminate | - |
| `s` | notaskstate | No task state | Uses task state | - |
| `m` | inaccessiblememonly | Local memory only | Accesses external memory | Arg memory only |
| `u` | noub | No undefined behavior | May have UB | No UB if bounds checked |
| `o` | nonoverlayed | No overlays | Uses overlays | Consistent overlays |
| `r` | nortcall | No return_type calls | Calls return_type | - |

### 6.3 Practical Effect Inspection

**Example: Investigating why a function isn't constant-folded**

```julia
julia> function my_hash(x::Int)
           result = 0
           for i in 1:x
               result = result * 31 + i
           end
           return result
       end

julia> Base.infer_effects(my_hash, (Int,))
(+c,+e,+n,-t,+s,+m,+u,+o,+r)
#                 ^^--- terminates is false!
```

The compiler can't prove termination because it doesn't know if `x` is positive. Adding an assertion helps:

```julia
julia> function my_hash_v2(x::Int)
           x >= 0 || throw(ArgumentError("x must be non-negative"))
           result = 0
           for i in 1:x
               result = result * 31 + i
           end
           return result
       end

julia> Base.infer_effects(my_hash_v2, (Int,))
(+c,+e,-n,-t,+s,+m,+u,+o,+r)
# Still -t, but now also -n due to possible throw
```

In this case, you might use `@assume_effects :terminates_globally` if you know callers will always pass valid values.

### 6.4 Effect Comparison

You can compare effects to understand what changed:

```julia
julia> effects1 = Base.infer_effects(+, (Int, Int))
(+c,+e,+n,+t,+s,+m,+u,+o,+r)

julia> effects2 = Base.infer_effects(+, (Float64, Float64))
(+c,+e,+n,+t,+s,+m,+u,+o,+r)

# Both are total - same effects for different numeric types
```

---

## 7. Advanced Topics

### 7.1 Effect Encoding and Storage

Effects are stored in compiled code by encoding them into a compact `UInt32` representation via [`encode_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L339-L349):

```julia
function encode_effects(e::Effects)
    # Pack all effect fields into bit positions of a UInt32
    return (UInt32(e.consistent) << 0) |
           (UInt32(e.effect_free) << 3) |
           # ... other fields
end
```

This encoding is stored in `CodeInstance` and decoded when needed via [`decode_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L351-L362).

### 7.2 Conditional Effects Resolution

Conditional effects (like `CONSISTENT_IF_NOTRETURNED`) are resolved during optimization when more information becomes available.

For example, if escape analysis proves that an allocated mutable object never escapes:
1. `CONSISTENT_IF_NOTRETURNED` can be upgraded to `ALWAYS_TRUE`
2. This enables constant folding that was previously blocked

### 7.3 Predefined Effect Constants

The compiler defines several common effect combinations ([effects.jl:178-181](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L178-L181)):

| Constant | Description |
|----------|-------------|
| `EFFECTS_TOTAL` | Completely pure (all effects positive) |
| `EFFECTS_THROWS` | Pure except may throw |
| `EFFECTS_UNKNOWN` | Unknown effects (conservative default) |

### 7.4 Cross-Subsystem Integration

Effects flow through multiple compiler subsystems:

**Type Inference (T1)**: Computes and accumulates effects during inference
- [`InferenceState.ipo_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/inferencestate.jl#L303)
- [`InferenceResult.ipo_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/types.jl#L127)

**Type Functions (T3)**: Provides effects for builtin operations
- [`builtin_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2631-L2709)
- [`intrinsic_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L3060-L3079)

**Optimization (T5)**: Uses effects to enable transformations
- [`flags_for_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L72-L98) converts to IR flags
- ADCE pass checks `IR_FLAGS_REMOVABLE`
- Inlining considers effects for cost model

**Escape Analysis (T6)**: Works with `inaccessiblememonly` effect
- Refines conditional effects based on escape information

**Caching (T8)**: Stores effects in `CodeInstance`
- Encoded effects are part of cached compiled code

---

## 8. Quick Reference

### 8.1 Effect Properties Summary

| Effect | Type | Good Value | Enables |
|--------|------|------------|---------|
| `consistent` | `UInt8` | `ALWAYS_TRUE` | CSE, constant folding |
| `effect_free` | `UInt8` | `ALWAYS_TRUE` | DCE |
| `nothrow` | `Bool` | `true` | DCE, exception simplification |
| `terminates` | `Bool` | `true` | Compile-time evaluation |
| `notaskstate` | `Bool` | `true` | Finalizer inlining |
| `inaccessiblememonly` | `UInt8` | `ALWAYS_TRUE` | Alias analysis |
| `noub` | `UInt8` | `ALWAYS_TRUE` | Safe optimization |
| `nonoverlayed` | `UInt8` | `ALWAYS_TRUE` | Cross-context caching |
| `nortcall` | `Bool` | `true` | Safe constant folding |

### 8.2 Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `Effects` | [effects.jl:119-150](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L119-L150) | Effects struct definition |
| `merge_effects` | [effects.jl:275-286](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L275-L286) | Combine effects |
| `is_foldable` | [effects.jl:308-313](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L308-L313) | Check constant-foldability |
| `is_removable_if_unused` | [effects.jl:320-323](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl#L320-L323) | Check DCE eligibility |
| `builtin_effects` | [tfuncs.jl:2631-2709](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/tfuncs.jl#L2631-L2709) | Effects for builtins |
| `flags_for_effects` | [optimize.jl:72-98](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L72-L98) | Convert to IR flags |

### 8.3 Common `@assume_effects` Patterns

```julia
# Pure mathematical function
Base.@assume_effects :total function pure_math(x::Int)
    # deterministic computation
end

# Function that may throw but is otherwise pure
Base.@assume_effects :consistent :effect_free function maybe_throws(x)
    # pure but may error
end

# IO function with known termination
Base.@assume_effects :terminates_globally function bounded_io(data)
    # terminates but has side effects
end
```

---

## See Also

- [Type Inference Deep Dive](./01-type-inference.md) - How effects are inferred
- [Optimization Passes](./05-optimization.md) - How effects enable optimizations
- [Escape Analysis](./06-escape-analysis.md) - Interaction with memory analysis
- [Compiler Interconnection Map](./interconnect-map.md) - How effects fit in the compiler architecture
