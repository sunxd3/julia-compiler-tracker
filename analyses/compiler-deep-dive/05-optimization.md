# Julia Compiler Deep Dive: Optimization Passes

This tutorial explains how Julia optimizes your code after type inference. We cover the optimization pipeline, inlining decisions, struct elimination (SROA), and dead code elimination (ADCE). By the end, you will understand what happens to your code between inference and codegen, and how to write code that optimizes well.

**Target audience**: Julia developers who know Julia well but want to understand what the compiler does to their code.

**Commit reference**: All GitHub permalinks reference [commit 4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c).

---

## Table of Contents

1. [The Optimization Pipeline](#1-the-optimization-pipeline)
2. [Deep Dive: Inlining](#2-deep-dive-inlining)
3. [Deep Dive: SROA (Scalar Replacement of Aggregates)](#3-deep-dive-sroa-scalar-replacement-of-aggregates)
4. [ADCE: Aggressive Dead Code Elimination](#4-adce-aggressive-dead-code-elimination)
5. [Controlling Optimization: @inline and @noinline](#5-controlling-optimization-inline-and-noinline)
6. [Cross-References: Escape Analysis and Effects](#6-cross-references-escape-analysis-and-effects)
7. [Summary](#7-summary)

---

## 1. The Optimization Pipeline

After type inference completes, Julia runs a series of optimization passes on the SSA IR (Static Single Assignment Intermediate Representation). These passes transform the code to run faster while preserving semantics.

### 1.1 Pass Order

The optimization pipeline is defined in [`run_passes_ipo_safe`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1044-L1076):

```julia
function run_passes_ipo_safe(ci::CodeInfo, sv::OptimizationState, ...)
    __stage__ = 0
    @pass "CC: CONVERT"   ir = convert_to_ircode(ci, sv)
    @pass "CC: SLOT2REG"  ir = slot2reg(ir, ci, sv)
    @pass "CC: COMPACT_1" ir = compact!(ir)
    @pass "CC: INLINING"  ir = ssa_inlining_pass!(ir, sv.inlining, ci.propagate_inbounds)
    @pass "CC: COMPACT_2" ir = compact!(ir)
    @pass "CC: SROA"      ir = sroa_pass!(ir, sv.inlining)
    @pass "CC: ADCE"      (ir, made_changes) = adce_pass!(ir, sv.inlining)
    if made_changes
        @pass "CC: COMPACT_3" ir = compact!(ir, true)
    end
    return ir
end
```

**Note**: This is the "IPO-safe" pipeline. Other compilation modes and internal passes exist (e.g., additional inlining heuristics, IR cleanups, or experimental passes), so treat this as the core, stable slice of the pipeline.

### 1.2 Understanding Each Pass

| Order | Pass | Function | What It Does |
|-------|------|----------|--------------|
| 1 | CONVERT | `convert_to_ircode` | Convert lowered `CodeInfo` to SSA `IRCode` |
| 2 | SLOT2REG | `slot2reg` | Convert local variable slots to SSA registers |
| 3 | COMPACT_1 | `compact!` | Remove dead statements, renumber SSA values |
| 4 | **INLINING** | `ssa_inlining_pass!` | Replace function calls with inlined bodies |
| 5 | COMPACT_2 | `compact!` | Clean up after inlining |
| 6 | **SROA** | `sroa_pass!` | Eliminate structs by replacing with scalars |
| 7 | **ADCE** | `adce_pass!` | Remove unused and dead code |
| 8 | COMPACT_3 | `compact!` | Final cleanup (only if ADCE changed something) |

### 1.3 Visualizing the Pipeline

```
    CodeInfo (from type inference)
              |
              v
    +-------------------+
    | CONVERT to IRCode |  <- Create SSA form
    +-------------------+
              |
              v
    +-------------------+
    |     SLOT2REG      |  <- Slots become SSA values
    +-------------------+
              |
              v
    +-------------------+
    |     COMPACT       |  <- Clean up
    +-------------------+
              |
              v
    +-------------------+
    |     INLINING      |  <- Inline function calls
    +-------------------+
              |
              v
    +-------------------+
    |     COMPACT       |  <- Clean up after inlining
    +-------------------+
              |
              v
    +-------------------+
    |      SROA         |  <- Eliminate structs
    +-------------------+
              |
              v
    +-------------------+
    |      ADCE         |  <- Remove dead code
    +-------------------+
              |
              v
    +-------------------+
    |     COMPACT       |  <- Final cleanup (if needed)
    +-------------------+
              |
              v
        Optimized IRCode
```

### 1.4 Why This Order Matters

The pass order is deliberate:

1. **Inlining first**: Inlining exposes optimization opportunities. A `getfield` on an argument becomes a `getfield` on a known `new` expression after inlining.

2. **SROA after inlining**: SROA can only eliminate allocations it can see. After inlining, the allocation and all its uses are in the same function.

3. **ADCE last**: Dead code elimination cleans up what SROA leaves behind. Eliminated struct fields often leave unused computations.

---

## 2. Deep Dive: Inlining

Inlining replaces a function call with the body of the called function. This is Julia's most impactful optimization because it enables all subsequent optimizations.

### 2.1 The Two Phases of Inlining

The inlining pass runs in two phases, defined in [`ssa_inlining_pass!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl#L73-L81):

```julia
function ssa_inlining_pass!(ir::IRCode, state::InliningState, propagate_inbounds::Bool)
    # Phase 1: Analysis - identify what to inline
    todo = assemble_inline_todo!(ir, state)
    isempty(todo) && return ir

    # Phase 2: Execution - perform the inlining
    ir = batch_inline!(ir, todo, propagate_inbounds, state.interp)
    return ir
end
```

**Phase 1 (Analysis)** scans all calls and decides which ones to inline, building a todo list.

**Phase 2 (Execution)** performs the actual IR transformation for each item in the list.

### 2.2 The Cost Model

Julia uses a cost model to decide whether inlining is profitable. The key constants are defined in [`types.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/types.jl#L11-L13):

```julia
const InlineCostType = UInt16
const MAX_INLINE_COST = typemax(InlineCostType)  # 65535 - never inline
const MIN_INLINE_COST = InlineCostType(10)       # clamping floor for cost calculations
```

**Key cost parameters:**

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `inline_cost_threshold` | 100 | Maximum cost for auto-inlining (functions with cost <= this are inlined) |
| `inline_nonleaf_penalty` | 1000 | Cost for calling a function that cannot itself be inlined |
| `max_tuple_splat` | 32 | Maximum tuple size for splatting |

**Note**: `MIN_INLINE_COST` (10) is a clamping floor used internally, not the inlining threshold. The actual threshold is `inline_cost_threshold` (default 100).

### 2.3 How Statement Costs Are Computed

The [`statement_cost`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1347-L1452) function assigns a cost to each IR statement:

| Statement Type | Cost | Notes |
|----------------|------|-------|
| `getfield`, `tuple`, `getglobal` | 0 | Cheap operations |
| Intrinsics | Lookup table | `T_IFUNC_COST` |
| Builtins | Lookup table | `T_FFUNC_COST` |
| `:foreigncall` | 20 | Fixed cost |
| `:invoke` (generic call) | 20 | `UNKNOWN_CALL_COST` |
| Backward `GotoNode` (loop) | 40 | Loop penalty |
| `EnterNode` (try/catch) | Infinity | Never inline try/catch |

The [`inline_cost_model`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1477-L1488) sums statement costs with saturation:

```julia
function inline_cost_model(ir::IRCode, params::OptimizationParams, cost_threshold::Int)
    bodycost = 0
    for stmt in ir.stmts
        bodycost = add_flag(bodycost, statement_or_branch_cost(stmt, ...))
        bodycost > cost_threshold && return MAX_INLINE_COST
    end
    return bodycost
end
```

### 2.4 Before/After: Simple Inlining

Consider this code:

```julia
struct Point
    x::Float64
    y::Float64
end

magnitude(p::Point) = sqrt(p.x^2 + p.y^2)

function example(x, y)
    p = Point(x, y)
    return magnitude(p)
end
```

**Before inlining:**

```
%1 = new Point(x, y)
%2 = invoke magnitude(%1)
return %2
```

**After inlining:**

```
%1 = new Point(x, y)
%2 = getfield(%1, :x)        # Inlined from magnitude
%3 = mul(%2, %2)             # p.x^2
%4 = getfield(%1, :y)
%5 = mul(%4, %4)             # p.y^2
%6 = add(%3, %5)
%7 = sqrt(%6)
return %7
```

Now SROA can see that the `Point` allocation is only used for `getfield` operations.

### 2.5 Union Splits

When a function argument has a union type, Julia can generate specialized code for each type. This is called **union splitting**.

The [`UnionSplit`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl#L55-L63) structure represents this:

```julia
struct UnionSplit
    handled_all_cases::Bool      # Did we handle every possible type?
    fully_covered::Bool          # Can we skip the fallback?
    atype::DataType              # The argument with union type
    cases::Vector{InliningCase}  # One case per type
    bbs::Vector{Int}             # Basic blocks for each case
end
```

**Example with union type:**

```julia
function process(x::Union{Int, Float64})
    return x + 1
end
```

**After union split:**

```
if isa(x, Int)
    %1 = add_int(x, 1)       # Specialized for Int
else
    %2 = add_float(x, 1.0)   # Specialized for Float64
end
%3 = phi(%1, %2)             # Merge results
return %3
```

The [`ir_inline_unionsplit!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl#L526-L617) function generates:
- `isa` checks for each type
- Conditional branches to specialized blocks
- PhiNodes to merge the results

### 2.6 Inlining Decision Flow

```
                    Call Site Found
                           |
                           v
              +------------------------+
              | Check @noinline flag   |
              +------------------------+
                    |           |
                 @noinline    no flag
                    |           |
                    v           v
               Don't inline  +------------------------+
                             | Check @inline flag     |
                             +------------------------+
                                  |           |
                               @inline      no flag
                                  |           |
                                  v           v
                            Force inline  +------------------------+
                                          | Compute inline cost    |
                                          +------------------------+
                                                    |
                                          cost <= inline_cost_threshold (100)?
                                                 /        \
                                              yes          no
                                               |            |
                                               v            v
                                          Inline      Don't inline
```

---

## 3. Deep Dive: SROA (Scalar Replacement of Aggregates)

SROA eliminates struct allocations by replacing them with their individual fields. This is one of Julia's most powerful optimizations for performance-critical code.

### 3.1 What SROA Does

The [`sroa_pass!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1264-L1579) function documentation explains:

> "getfield elimination pass, a.k.a. Scalar Replacements of Aggregates optimization. This pass is based on a local field analysis by def-use chain walking."

In plain terms: if a struct is only created and then has its fields read, the struct allocation can be removed entirely.

### 3.2 Before/After: SROA in Action

Continuing our Point example:

**After inlining (before SROA):**

```
%1 = new Point(x, y)
%2 = getfield(%1, :x)
%3 = mul(%2, %2)
%4 = getfield(%1, :y)
%5 = mul(%4, %4)
%6 = add(%3, %5)
%7 = sqrt(%6)
return %7
```

**After SROA:**

```
%1 = mul(x, x)      # p.x^2, using x directly
%2 = mul(y, y)      # p.y^2, using y directly
%3 = add(%1, %2)
%4 = sqrt(%3)
return %4
```

The `Point` allocation is completely eliminated. The fields `x` and `y` are used directly.

### 3.3 How SROA Works: Def-Use Tracking

SROA uses def-use chain analysis to track how values flow through the program. The [`SSADefUse`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L28-L47) structure records:

```julia
struct SSADefUse
    uses::Vector{SSAUse}  # Where is this value used?
    defs::Vector{Int}     # Where is this value defined?
end
```

The use kinds tracked are:

| Use Kind | Meaning |
|----------|---------|
| `GetfieldUse` | Field read via `getfield` |
| `IsdefinedUse` | Check if field is defined via `isdefined` |
| `PreserveUse` | GC preservation in `foreigncall` |
| `FinalizerUse` | Finalizer registration |

### 3.4 The Lifting Process

SROA "lifts" field values from allocations. The process has three steps:

**Step 1: Collect Leaves** - [`collect_leaves`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L187-L193)

Walk backward through PhiNodes to find all allocation sites ("leaves"):

```
getfield(%phi, :x)
    |
    v
phi(%1, %2)  <- walk through this
   / \
  v   v
%1 = new Point(a, b)    <- leaf 1
%2 = new Point(c, d)    <- leaf 2
```

**Step 2: Lift Leaves** - [`lift_leaves`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L409-L500)

For each leaf, compute the field value:

```
%1 = new Point(a, b) -> :x field is 'a'
%2 = new Point(c, d) -> :x field is 'c'
```

**Step 3: Perform Lifting** - [`perform_lifting!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L782-L880)

Create new PhiNodes for the lifted values:

```
Before:
  %phi = phi(%1, %2)
  %result = getfield(%phi, :x)

After:
  %lifted = phi(a, c)   # New phi for the :x field
  %result = %lifted     # getfield eliminated
```

### 3.5 Mutable Structs: A Harder Problem

Mutable structs are harder to optimize because their fields can change. The [`sroa_mutables!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1760-L1994) function handles this by:

1. Partitioning uses by field
2. Using the iterated dominance frontier for phi placement
3. Replacing `getfield` with the most recent value
4. Eliminating `setfield!` when all uses are resolved

**Example with mutable struct:**

```julia
mutable struct Counter
    value::Int
end

function increment(c::Counter)
    c.value += 1
    return c.value
end

function example()
    c = Counter(0)
    return increment(c)
end
```

**After inlining and SROA:**

```
%1 = 0          # Initial value (no allocation!)
%2 = add(%1, 1) # c.value += 1
return %2       # return c.value
```

The mutable struct is eliminated because it does not escape the function.

### 3.6 When SROA Cannot Help

SROA fails when:

1. **The struct escapes**: Passed to a function that might store it, returned, or thrown.

2. **Unknown field access**: Dynamic field access like `getfield(x, field_name)` where `field_name` is not constant.

3. **The struct is aliased**: Multiple references to the same allocation that cannot be tracked.

```julia
# SROA cannot help here
function escape_example()
    p = Point(1.0, 2.0)
    store_somewhere(p)  # p escapes!
    return p.x
end
```

---

## 4. ADCE: Aggressive Dead Code Elimination

The [`adce_pass!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L2098-L2253) removes code that has no effect on the program's result.

### 4.1 What Makes Code "Dead"?

Code is dead if:

1. **Its result is unused**: No other statement reads the value.
2. **It has no side effects**: Removing it does not change program behavior.
3. **It cannot throw**: Or if it can throw, the exception is never observed.

The IR flags track these properties:

```julia
const IR_FLAGS_REMOVABLE = IR_FLAG_EFFECT_FREE | IR_FLAG_NOTHROW | IR_FLAG_TERMINATES
```

### 4.2 Before/After: Dead Code Elimination

**Before ADCE:**

```
%1 = new Point(x, y)      # Allocated but never used after SROA
%2 = mul(x, x)
%3 = mul(y, y)
%4 = add(%2, %3)
%5 = sqrt(%4)
return %5
```

**After ADCE:**

```
%1 = mul(x, x)
%2 = mul(y, y)
%3 = add(%1, %2)
%4 = sqrt(%3)
return %4
```

The `new Point(x, y)` is removed because nothing uses it (SROA lifted all the field accesses).

### 4.3 PhiNode Simplification

ADCE also simplifies PhiNodes. The [`reprocess_phi_node!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L1717-L1731) function handles:

**Single-predecessor elimination:**

```
Before:
  BB1:
    goto BB2
  BB2:
    %phi = phi(BB1 => %1)  # Only one incoming edge

After:
  BB1:
    goto BB2
  BB2:
    # %phi replaced with %1 directly
```

**Self-referential cycle elimination:**

```
Before:
  %phi = phi(%phi, %1)  # References itself

After:
  # %phi replaced with %1
```

### 4.4 Typeassert Elimination

ADCE removes typeasserts that are provably true:

```julia
# In adce_pass! (lines 2146-2152)
if is_known_call(stmt, typeassert, compact) && length(stmt.args) == 3
    ty, isexact = instanceof_tfunc(argextype(stmt.args[3], compact), true)
    if isexact && argextype(stmt.args[2], compact) <: ty
        delete_inst_here!(compact)  # Remove redundant typeassert
    end
end
```

**Example:**

```julia
x::Int  # If x is already known to be Int, this is removed
```

---

## 5. Controlling Optimization: @inline and @noinline

You can influence inlining decisions using `@inline` and `@noinline` annotations.

### 5.1 How Annotations Work

The annotations set IR flags on the function definition:

| Annotation | Flag | Effect |
|------------|------|--------|
| `@inline` | `IR_FLAG_INLINE` | Force inlining (cost = 0) |
| `@noinline` | `IR_FLAG_NOINLINE` | Prevent inlining (cost = MAX) |

The [`src_inlining_policy`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L131-L152) function checks these flags:

```julia
function src_inlining_policy(...)
    if is_stmt_inline(src_flag)      # @inline
        return true, true
    elseif is_stmt_noinline(src_flag) # @noinline
        return false, false
    else
        return is_inlineable(src), may_invoke_generator(...)
    end
end
```

### 5.2 When to Use @inline

Use `@inline` for:

1. **Small functions with high call overhead**: The function body is cheaper than the call itself.

2. **Performance-critical inner loops**: Even small gains matter when called millions of times.

3. **Enabling further optimizations**: Inlining exposes opportunities for SROA, constant propagation, etc.

```julia
# Good use of @inline
@inline getx(p::Point) = p.x  # Trivial accessor

# Without @inline, this might not be inlined due to cost model
@inline function complex_but_critical(x, y, z)
    # ... performance-critical code ...
end
```

### 5.3 When to Use @noinline

Use `@noinline` for:

1. **Large functions**: Prevent code bloat from excessive inlining.

2. **Debugging**: Keep function boundaries visible in stack traces.

3. **Compile time**: Reduce compilation time for rarely-called code.

```julia
# Good use of @noinline
@noinline function error_handler(msg)
    # Large error handling code
    # Called rarely, no need to inline
end

# Prevent inlining of recursive functions
@noinline function recursive_parse(input)
    # Inlining recursion can explode code size
end
```

### 5.4 The Cost Threshold

Without annotations, the compiler uses the cost model. Functions with cost at or below `inline_cost_threshold` (default 100) are auto-inlined. Note that `MIN_INLINE_COST` (10) is merely a clamping floor for cost calculations, not the inlining decision threshold.

```julia
# Likely auto-inlined (very cheap)
getx(p) = p.x

# Likely NOT auto-inlined (too expensive)
function expensive(x)
    result = 0
    for i in 1:100
        result += compute(x, i)
    end
    return result
end
```

---

## 6. Cross-References: Escape Analysis and Effects

The optimization passes integrate with two other compiler subsystems: escape analysis and the effects system.

### 6.1 Escape Analysis Integration

Escape analysis determines whether allocated objects can be optimized away. It answers: "Does this allocation escape the current function?"

**How SROA uses escape analysis:**

The [`sroa_mutables!`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1760-L1994) function calls escape analysis for mutable structs:

```julia
estate = EscapeAnalysis.analyze_escapes(ir, nargs, ...)
hasaliases = EscapeAnalysis.getaliases(SSAValue(defidx), estate) !== nothing
einfo = estate[SSAValue(defidx)]

if !hasaliases && EscapeAnalysis.has_no_escape(einfo)
    # Can optimize this allocation!
end
```

**Key escape predicates:**

| Function | Meaning |
|----------|---------|
| `has_no_escape(info)` | Object does not escape anywhere |
| `has_return_escape(info)` | Object escapes via return |
| `has_thrown_escape(info)` | Object escapes via throw |
| `has_arg_escape(info)` | Object visible to caller as argument |

**Example: escape analysis enabling SROA:**

```julia
function local_only()
    p = Point(1.0, 2.0)  # Does not escape
    return p.x + p.y     # Only field accesses
end
# SROA can eliminate the Point allocation

function escapes()
    p = Point(1.0, 2.0)
    global_storage[] = p  # Escapes!
    return p.x + p.y
end
# SROA cannot eliminate the allocation
```

For more details, see the [Escape Analysis deep dive](./06-escape-analysis.md).

### 6.2 Effects System Integration

The effects system tracks whether statements are effect-free, can throw, etc. These properties determine what can be removed by ADCE.

**IR flags from effects:**

```julia
const IR_FLAG_CONSISTENT  = one(UInt32) << 3   # Same inputs -> same outputs
const IR_FLAG_EFFECT_FREE = one(UInt32) << 4   # No side effects
const IR_FLAG_NOTHROW     = one(UInt32) << 5   # Cannot throw
const IR_FLAG_TERMINATES  = one(UInt32) << 6   # Will terminate
const IR_FLAG_NOUB        = one(UInt32) << 10  # No undefined behavior

# Combined flag for dead code elimination
const IR_FLAGS_REMOVABLE = IR_FLAG_EFFECT_FREE | IR_FLAG_NOTHROW | IR_FLAG_TERMINATES
```

**The [`flags_for_effects`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L72-L98) conversion:**

```julia
function flags_for_effects(effects::Effects)
    flags = zero(UInt32)
    if is_consistent(effects)
        flags |= IR_FLAG_CONSISTENT
    end
    if is_effect_free(effects)
        flags |= IR_FLAG_EFFECT_FREE
    end
    # ... etc
    return flags
end
```

**Example: effects enabling ADCE:**

```julia
function pure_computation()
    x = 1 + 1      # effect_free, nothrow, terminates
    y = 2 + 2      # effect_free, nothrow, terminates
    return x       # y is dead code
end
# ADCE removes y = 2 + 2

function side_effect()
    println("hello")  # NOT effect_free
    x = 1 + 1
    return x
end
# ADCE cannot remove println
```

For more details, see the [Effects System deep dive](./07-effects.md).

### 6.3 The Integration Picture

```
                    Type Inference
                          |
                          v
              +-----------+-----------+
              |                       |
              v                       v
        InferenceResult         Effects (ipo_effects)
              |                       |
              |                       v
              |               flags_for_effects()
              |                       |
              v                       v
           IRCode        +---------> IR Flags
              |         /
              v        /
        INLINING ------
              |
              v
         COMPACT
              |
              v
          SROA <-------- Escape Analysis
              |                |
              v                |
          ADCE <--------- IR Flags (effects)
              |
              v
      Optimized IRCode
```

---

## 7. Summary

### 7.1 Key Takeaways

1. **Pass order matters**: Inlining enables SROA, which enables ADCE. The passes build on each other.

2. **Inlining is critical**: Without inlining, the compiler cannot see through function boundaries. Write small functions and let the compiler inline them.

3. **SROA eliminates allocations**: If a struct is only created and has its fields read, no allocation happens at runtime.

4. **Effects enable dead code elimination**: Code that is effect-free, cannot throw, and terminates can be removed if unused.

5. **Escape analysis enables mutable optimization**: Mutable structs that do not escape can be eliminated like immutable ones.

### 7.2 Writing Optimization-Friendly Code

**Do:**
- Write small, focused functions (they inline better)
- Prefer immutable structs (easier to optimize)
- Use concrete types (enables specialization)
- Keep allocations local when possible (enables SROA)

**Avoid:**
- Large functions with `@inline` (code bloat)
- Type instabilities (prevent optimization)
- Global mutable state (escapes, side effects)
- Dynamic field access (prevents SROA)

### 7.3 Further Reading

- [Type Inference deep dive](./01-type-inference.md)
- [SSA IR deep dive](./04-ssa-ir.md)
- [Escape Analysis deep dive](./06-escape-analysis.md)
- [Effects System deep dive](./07-effects.md)
- [Interconnection Map](./interconnect-map.md)

### 7.4 Source Code References

| Component | File | Key Functions |
|-----------|------|---------------|
| Pass pipeline | [`optimize.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl) | `run_passes_ipo_safe`, `statement_cost` |
| Inlining | [`ssair/inlining.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl) | `ssa_inlining_pass!`, `batch_inline!` |
| SROA | [`ssair/passes.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl) | `sroa_pass!`, `sroa_mutables!` |
| ADCE | [`ssair/passes.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L2098-L2253) | `adce_pass!` |
| Escape Analysis | [`ssair/EscapeAnalysis.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/EscapeAnalysis.jl) | `analyze_escapes` |

Next: [06-escape-analysis.md](./06-escape-analysis.md)
