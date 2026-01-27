# Journey: Tracing a Method Call Through Julia's Compiler

This document traces a concrete example through every stage of Julia's compilation pipeline. By following a simple function from source code to machine code, we will see how all the compiler subsystems work together to produce efficient executables.

**Target audience**: Julia developers who have read the individual deep-dive documents and want to see how the pieces connect.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [Our Example: The Point Magnitude Function](#1-our-example-the-point-magnitude-function)
2. [Stage 1: Lowering (AST to CodeInfo)](#2-stage-1-lowering-ast-to-codeinfo)
3. [Stage 2: Type Inference](#3-stage-2-type-inference)
4. [Stage 3: Caching (CodeInstance Creation)](#4-stage-3-caching-codeinstance-creation)
5. [Stage 4: SSA IR Construction](#5-stage-4-ssa-ir-construction)
6. [Stage 5: Optimization Passes](#6-stage-5-optimization-passes)
7. [Stage 6: Code Generation](#7-stage-6-code-generation)
8. [Complete Pipeline Visualization](#8-complete-pipeline-visualization)
9. [What We Learned](#9-what-we-learned)

---

## 1. Our Example: The Point Magnitude Function

We will trace this simple but illustrative example:

```julia
struct Point
    x::Float64
    y::Float64
end

magnitude(p::Point) = sqrt(p.x^2 + p.y^2)
```

This example is perfect for understanding Julia's compiler because:

1. **It uses a struct**: We can observe SROA (Scalar Replacement of Aggregates)
2. **It calls a math function**: We can observe inlining of `sqrt`
3. **It performs arithmetic**: We can observe how primitive operations are typed
4. **It has a clear expected result**: The Point should be completely eliminated

Let us trace what happens when we call:

```julia
p = Point(3.0, 4.0)
result = magnitude(p)  # Should return 5.0
```

---

## 2. Stage 1: Lowering (AST to CodeInfo)

### What Lowering Does

When Julia parses source code, it creates an Abstract Syntax Tree (AST). **Lowering** transforms this high-level AST into **CodeInfo**, a flattened representation suitable for analysis.

The lowering phase handles:
- Macro expansion
- Desugaring (e.g., `p.x` becomes `getfield(p, :x)`)
- Control flow normalization
- Scope resolution

### Viewing the Lowered Code

```julia
julia> @code_lowered magnitude(Point(3.0, 4.0))
CodeInfo(
1 - %1 = Base.getproperty(p, :x)
|   %2 = Core.apply_type(Base.Val, 2)
|   %3 = (%2)()
|   %4 = Base.literal_pow(^, %1, %3)
|   %5 = Base.getproperty(p, :y)
|   %6 = Core.apply_type(Base.Val, 2)
|   %7 = (%6)()
|   %8 = Base.literal_pow(^, %5, %7)
|   %9 = %4 + %8
|   %10 = Main.sqrt(%9)
|   return %10
)
```

### Understanding the Lowered IR

Let us break down what happened to our one-liner `sqrt(p.x^2 + p.y^2)`:

| Line | Statement | Original Code |
|------|-----------|---------------|
| `%1` | `Base.getproperty(p, :x)` | `p.x` |
| `%2-%4` | `Base.literal_pow(^, %1, Val(2))` | `p.x^2` |
| `%5` | `Base.getproperty(p, :y)` | `p.y` |
| `%6-%8` | `Base.literal_pow(^, %5, Val(2))` | `p.y^2` |
| `%9` | `%4 + %8` | `... + ...` |
| `%10` | `Main.sqrt(%9)` | `sqrt(...)` |

**Key observations**:
- Field access `p.x` becomes `getproperty(p, :x)`
- The power operator `^2` becomes `literal_pow` with a `Val{2}` type parameter
- No types are known yet - this is pure structural transformation

### The CodeInfo Structure

The lowered code is stored in a `CodeInfo` object:

```julia
mutable struct CodeInfo
    code::Vector{Any}      # The statements
    slotnames::Vector{Symbol}  # Variable names
    slotflags::Vector{UInt8}   # Variable properties
    ssavaluetypes::Any         # (filled during inference)
    # ... more fields
end
```

At this stage, `ssavaluetypes` is empty. Type inference will fill it in.

---

## 3. Stage 2: Type Inference

### What Type Inference Does

Type inference determines the type of every value in the program. This is the most critical compilation stage because all subsequent optimizations depend on type information.

**Key questions type inference answers**:
- What is the return type of this function?
- What method will `sqrt` dispatch to?
- Can any calls be inlined?
- What effects does this function have?

### The Inference Algorithm

Type inference uses **worklist-based forward dataflow analysis**:

```
                    +-----------------------+
                    |   Initialize argtypes |
                    |   p::Point            |
                    +-----------------------+
                              |
                              v
                    +-----------------------+
                    |   Process statements  |
                    |   in worklist order   |
                    +-----------------------+
                              |
            +-----------------+-----------------+
            |                                   |
            v                                   v
    +---------------+                   +---------------+
    | abstract_eval |                   | abstract_call |
    | (expressions) |                   | (function calls)|
    +---------------+                   +---------------+
            |                                   |
            +-----------------+-----------------+
                              |
                              v
                    +-----------------------+
                    |   Store results in    |
                    |   ssavaluetypes[]     |
                    +-----------------------+
```

### Viewing the Inferred Types

```julia
julia> @code_typed optimize=false magnitude(Point(3.0, 4.0))
CodeInfo(
1 - %1 = Base.getfield(p, :x)::Float64
|   %2 = Base.mul_float(%1, %1)::Float64
|   %3 = Base.getfield(p, :y)::Float64
|   %4 = Base.mul_float(%3, %3)::Float64
|   %5 = Base.add_float(%2, %4)::Float64
|   %6 = Base.Math.sqrt_llvm(%5)::Float64
|   return %6
) => Float64
```

### What Changed During Inference

| Before Inference | After Inference | Why |
|------------------|-----------------|-----|
| `getproperty(p, :x)` | `getfield(p, :x)::Float64` | Resolved to concrete field access |
| `literal_pow(^, %1, Val(2))` | `mul_float(%1, %1)::Float64` | Constant folded `^2` to multiplication |
| `Main.sqrt(%9)` | `Math.sqrt_llvm(%5)::Float64` | Resolved to intrinsic |
| No return type | `=> Float64` | Inferred from all return paths |

### The Type Lattice in Action

Type inference uses the **type lattice** to track what it knows about each value:

```
For p.x:
- Initial: Union{} (bottom - no information)
- After getfield: Float64 (from struct field type)

For %2 (p.x * p.x):
- Inputs: (Float64, Float64)
- tfunc for mul_float: (Float64, Float64) -> Float64
- Result: Float64
```

**Source**: The lattice operations are in [`typelattice.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typelattice.jl).

### Effects Analysis

Type inference also computes **effects** - what side effects the function might have:

```julia
julia> Base.infer_effects(magnitude, (Point,))
(+c,+e,+n,+t,+s,+m,+u,+o,+r)
```

| Flag | Meaning | Value | Explanation |
|------|---------|-------|-------------|
| `+c` | consistent | yes | Same inputs always give same outputs |
| `+e` | effect_free | yes | No observable side effects |
| `+n` | nothrow | yes | Cannot throw (for valid inputs) |
| `+t` | terminates | yes | Always terminates |
| `+s` | notaskstate | yes | Doesn't access task-local state |
| `+m` | inaccessiblememonly | yes | Only accesses inaccessible or arg memory |
| `+u` | noub | yes | No undefined behavior |
| `+o` | nonoverlayed | yes | No method overlays |
| `+r` | nortcall | yes | No runtime `return_type` call |

These effects enable aggressive optimization. With `effect_free` and `nothrow`, unused calls can be eliminated.

**Source**: Effects are defined in [`effects.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/effects.jl).

---

## 4. Stage 3: Caching (CodeInstance Creation)

### Why Caching Matters

After type inference completes, Julia creates a **CodeInstance** to cache the results. Without caching, every call to `magnitude(p)` would trigger re-inference.

### The Compilation Hierarchy

```
Method: magnitude (generic function)
    |
    +-- MethodInstance: magnitude(::Point)
            |
            +-- CodeInstance (world 1 to MAX_WORLD)
                    - rettype: Float64
                    - effects: consistent, effect_free, nothrow, ...
                    - inferred: <optimized IR>
```

### CodeInstance Fields

The CodeInstance stores everything needed for execution:

| Field | Value for Our Example |
|-------|----------------------|
| `rettype` | `Float64` |
| `exctype` | `Union{}` (cannot throw) |
| `min_world` | World age when compiled |
| `max_world` | `typemax(UInt)` (valid forever, until invalidated) |
| `edges` | Dependencies on `sqrt`, `getfield`, etc. |
| `ipo_purity_bits` | Effect flags |

### Backedges for Invalidation

Julia records **backedges** so that if `sqrt` is redefined, our cached `magnitude` can be invalidated:

```
sqrt (Math.sqrt_llvm)
    |
    +-- backedge --> magnitude(::Point)
```

If someone defines a new `sqrt` method that could apply to `Float64`, Julia walks these backedges and sets `max_world` on affected CodeInstances, forcing recompilation on next call.

**Source**: Caching logic is in [`cicache.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/cicache.jl) and [`typeinfer.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/typeinfer.jl).

---

## 5. Stage 4: SSA IR Construction

### From CodeInfo to IRCode

The typed CodeInfo is converted to **SSA (Static Single Assignment) IR** for optimization. In SSA form, every variable is assigned exactly once, making dataflow analysis trivial.

### The conversion process

The main entry points are defined in [`optimize.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl):
- [`convert_to_ircode`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1139) (line 1139)
- [`slot2reg`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1327) (line 1327)

Supporting functions for slot-to-SSA conversion are in [`ssair/slot2ssa.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/slot2ssa.jl).

```
CodeInfo (with slots/variables that can be reassigned)
    |
    v convert_to_ircode()
IRCode (with SSA values, each assigned once)
    |
    v slot2reg()
IRCode (all slots converted to SSA registers)
```

### The IRCode Structure

```julia
struct IRCode
    stmts::InstructionStream      # Statements with types
    argtypes::Vector{Any}         # [Point] for our function
    cfg::CFG                      # Control flow graph
    # ...
end
```

For our example, the IRCode looks like:

```
Arguments: p::Point
BB #1:
  %1 = getfield(p, :x)::Float64
  %2 = mul_float(%1, %1)::Float64
  %3 = getfield(p, :y)::Float64
  %4 = mul_float(%3, %3)::Float64
  %5 = add_float(%2, %4)::Float64
  %6 = sqrt_llvm(%5)::Float64
  return %6
```

This is a single basic block (no branches), which is common for simple arithmetic functions.

**Source**: IR structures are in [`ssair/ir.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl).

---

## 6. Stage 5: Optimization Passes

This is where the magic happens. Julia runs a series of optimization passes that transform our code from struct-heavy operations to pure floating-point arithmetic.

### The Optimization Pipeline

**Source**: [`optimize.jl:1044-1076`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1044-L1076)

```julia
function run_passes_ipo_safe(ci::CodeInfo, sv::OptimizationState, ...)
    @pass "CC: CONVERT"   ir = convert_to_ircode(ci, sv)
    @pass "CC: SLOT2REG"  ir = slot2reg(ir, ci, sv)
    @pass "CC: COMPACT 1" ir = compact!(ir)
    @pass "CC: INLINING"  ir = ssa_inlining_pass!(ir, sv.inlining, ...)
    @pass "CC: COMPACT 2" ir = compact!(ir)
    @pass "CC: SROA"      ir = sroa_pass!(ir, sv.inlining)
    @pass "CC: ADCE"      (ir, made_changes) = adce_pass!(ir, sv.inlining)
    # COMPACT_3 only runs if ADCE made changes
    if made_changes
        @pass "CC: COMPACT 3" ir = compact!(ir, true)
    end
    return ir
end
```

Note: The "CC: " prefix in pass names stands for "Compiler Core" and is used in the actual source code. The COMPACT_3 pass is conditional - it only runs when ADCE makes changes to avoid unnecessary compaction.

Let us trace our function through each pass.

### Pass 1-3: CONVERT, SLOT2REG, COMPACT

These initial passes convert to SSA form. After COMPACT_1:

```
Arguments: p::Point
BB #1:
  %1 = getfield(p, :x)::Float64
  %2 = mul_float(%1, %1)::Float64
  %3 = getfield(p, :y)::Float64
  %4 = mul_float(%3, %3)::Float64
  %5 = add_float(%2, %4)::Float64
  %6 = sqrt_llvm(%5)::Float64
  return %6
```

No changes yet - our function was already simple.

### Pass 4: INLINING

**What inlining does**: Replaces function calls with the callee's body.

For `magnitude`, there is nothing to inline at the top level (the arithmetic intrinsics are already primitive). But consider if we had called `magnitude` from another function:

```julia
function distance_from_origin(p::Point)
    return magnitude(p)
end
```

After inlining:

```
# Before inlining
%1 = invoke magnitude(p)::Float64
return %1

# After inlining
%1 = getfield(p, :x)::Float64
%2 = mul_float(%1, %1)::Float64
%3 = getfield(p, :y)::Float64
%4 = mul_float(%3, %3)::Float64
%5 = add_float(%2, %4)::Float64
%6 = sqrt_llvm(%5)::Float64
return %6
```

**Source**: [`ssair/inlining.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl)

### Pass 5: COMPACT_2

Cleans up after inlining by renumbering SSA values and removing dead code.

### Pass 6: SROA (Scalar Replacement of Aggregates)

**This is the key optimization for our example.**

SROA eliminates struct allocations when:
1. The struct is only used for field access
2. The struct does not escape

Consider calling `magnitude(Point(3.0, 4.0))`:

```julia
# Before SROA
%1 = new(Point, 3.0, 4.0)::Point
%2 = getfield(%1, :x)::Float64
%3 = mul_float(%2, %2)::Float64
%4 = getfield(%1, :y)::Float64
%5 = mul_float(%4, %4)::Float64
%6 = add_float(%3, %5)::Float64
%7 = sqrt_llvm(%6)::Float64
return %7

# After SROA
%1 = mul_float(3.0, 3.0)::Float64     # x^2 = 9.0
%2 = mul_float(4.0, 4.0)::Float64     # y^2 = 16.0
%3 = add_float(%1, %2)::Float64       # 25.0
%4 = sqrt_llvm(%3)::Float64           # 5.0
return %4
```

**The Point struct allocation is completely eliminated!**

The SROA pass works by:
1. **Collecting leaves**: Finding all allocation sites (`new` expressions)
2. **Tracking uses**: Recording all `getfield` operations on the allocation
3. **Lifting values**: Replacing `getfield(%allocation, :field)` with the field value directly
4. **Eliminating allocation**: If all uses are lifted, the `new` becomes dead code

**Source**: [`ssair/passes.jl:1264-1579`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1264-L1579)

### Pass 7: ADCE (Aggressive Dead Code Elimination)

ADCE removes code that has no effect on the program result:

```julia
const IR_FLAGS_REMOVABLE = IR_FLAG_EFFECT_FREE | IR_FLAG_NOTHROW | IR_FLAG_TERMINATES
```

After SROA eliminated the `getfield` uses, the `new(Point, ...)` statement has no uses and can be removed (since struct allocation is effect-free).

**Source**: [`ssair/passes.jl:2117-2253`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L2117-L2253) (docstring starts at line 2098, function at 2117)

### Viewing the Optimized IR

```julia
julia> @code_typed optimize=true magnitude(Point(3.0, 4.0))
CodeInfo(
1 - %1 = Base.getfield(p, :x)::Float64
|   %2 = Base.mul_float(%1, %1)::Float64
|   %3 = Base.getfield(p, :y)::Float64
|   %4 = Base.mul_float(%3, %3)::Float64
|   %5 = Base.add_float(%2, %4)::Float64
|   %6 = Base.Math.sqrt_llvm(%5)::Float64
|   return %6
) => Float64
```

When the Point is passed as an argument (not allocated inline), SROA cannot eliminate it. But when the allocation is visible:

```julia
julia> test() = magnitude(Point(3.0, 4.0))

julia> @code_typed test()
CodeInfo(
1 - %1 = Base.mul_float(3.0, 3.0)::Float64
|   %2 = Base.mul_float(4.0, 4.0)::Float64
|   %3 = Base.add_float(%1, %2)::Float64
|   %4 = Base.Math.sqrt_llvm(%3)::Float64
|   return %4
) => Float64
```

The Point is completely gone.

---

## 7. Stage 6: Code Generation

### From IRCode to LLVM IR

Julia's codegen converts optimized IRCode to LLVM IR, which LLVM then compiles to machine code.

### Viewing the LLVM IR

```julia
julia> @code_llvm magnitude(Point(3.0, 4.0))
;  @ REPL[2]:1 within `magnitude`
define double @julia_magnitude_123(ptr nocapture noundef nonnull readonly align 8 %"p::Point") #0 {
top:
; | @ REPL[2]:1 within `magnitude`
; | @ float.jl:410 within `*`
  %0 = load double, ptr %"p::Point", align 8
  %1 = fmul double %0, %0
  %2 = getelementptr inbounds i8, ptr %"p::Point", i64 8
  %3 = load double, ptr %2, align 8
  %4 = fmul double %3, %3
; | @ float.jl:408 within `+`
  %5 = fadd double %1, %4
; | @ math.jl:613 within `sqrt`
; | | @ math.jl:573 within `sqrt_llvm`
  %6 = call double @llvm.sqrt.f64(double %5)
  ret double %6
}
```

### Understanding the LLVM IR

| LLVM Instruction | Purpose |
|------------------|---------|
| `load double, ptr %p` | Load `p.x` from memory |
| `fmul double %0, %0` | Compute `p.x * p.x` |
| `getelementptr ... i64 8` | Compute address of `p.y` (8 bytes offset) |
| `fadd double %1, %4` | Compute `x^2 + y^2` |
| `@llvm.sqrt.f64` | Hardware sqrt instruction |

### Viewing the Native Assembly

```julia
julia> @code_native magnitude(Point(3.0, 4.0))
        .text
        .file   "magnitude"
        .globl  julia_magnitude_123
        .p2align        4, 0x90
julia_magnitude_123:
        movsd   (%rdi), %xmm0           # Load p.x
        mulsd   %xmm0, %xmm0            # p.x * p.x
        movsd   8(%rdi), %xmm1          # Load p.y
        mulsd   %xmm1, %xmm1            # p.y * p.y
        addsd   %xmm1, %xmm0            # Add them
        sqrtsd  %xmm0, %xmm0            # Hardware sqrt
        retq
```

This is highly optimized code:
- No function calls (everything inlined)
- No allocations (Point passed by reference)
- Uses hardware floating-point instructions
- Total: 7 instructions for the entire computation

---

## 8. Complete Pipeline Visualization

Here is the complete journey of `magnitude(Point(3.0, 4.0))`:

```
                            Source Code
                                |
            "magnitude(p::Point) = sqrt(p.x^2 + p.y^2)"
                                |
                                v
+================================================================+
|                         LOWERING                                |
|   Desugars p.x -> getproperty(p, :x)                           |
|   Expands ^2 -> literal_pow with Val{2}                        |
+================================================================+
                                |
                                v
                            CodeInfo
                    (untyped lowered IR)
                                |
                                v
+================================================================+
|                     TYPE INFERENCE                              |
|   T2: Type Lattice - tracks Float64 types                      |
|   T3: tfuncs - knows mul_float returns Float64                 |
|   T7: Effects - marks as pure, nothrow                         |
+================================================================+
                                |
                                v
                         InferenceResult
                    (types + effects for all statements)
                                |
                                v
+================================================================+
|                        CACHING                                  |
|   Creates CodeInstance for magnitude(::Point)                  |
|   Records backedges to sqrt, getfield                          |
|   Stores rettype=Float64, effects=(+c,+e,+n,+t,...)           |
+================================================================+
                                |
                                v
+================================================================+
|                     SSA CONSTRUCTION                            |
|   convert_to_ircode: CodeInfo -> IRCode                        |
|   slot2reg: slots -> SSA values                                |
+================================================================+
                                |
                                v
                             IRCode
                     (SSA form with types)
                                |
                                v
+================================================================+
|                      OPTIMIZATION                               |
|   INLINING: Inline callees (sqrt already primitive)            |
|   SROA: Eliminate Point allocation when visible                |
|   ADCE: Remove dead allocations                                |
+================================================================+
                                |
                                v
                        Optimized IRCode
                  (no allocations, pure math)
                                |
                                v
+================================================================+
|                     CODE GENERATION                             |
|   IRCode -> LLVM IR -> Machine Code                            |
|   Uses hardware sqrt instruction                               |
+================================================================+
                                |
                                v
                        Native Machine Code
                    (7 x86 instructions)
```

---

## 9. What We Learned

### Key Insights

1. **Lowering is purely structural**: It transforms syntax without knowing types. `p.x` becomes `getproperty(p, :x)` regardless of what `p` is.

2. **Type inference is the foundation**: Every subsequent optimization depends on knowing types. The inference engine uses the type lattice, tfuncs for builtins, and tracks effects.

3. **Caching enables performance**: Without caching, every call would trigger full recompilation. CodeInstances store inference results, and backedges enable targeted invalidation.

4. **SSA form simplifies analysis**: Converting to SSA (each value assigned once) makes dataflow trivial - just look at the definition.

5. **Optimization passes compose**: Inlining exposes opportunities for SROA. SROA creates dead code for ADCE. The pass order is deliberate.

6. **SROA is Julia's secret weapon**: Struct allocations that do not escape are completely eliminated. This is why small immutable structs are "zero-cost abstractions."

7. **Effects enable dead code elimination**: Knowing a function is `effect_free` and `nothrow` allows removing unused computations.

### The Subsystem Collaboration

| Subsystem | Contribution to `magnitude(Point(3.0, 4.0))` |
|-----------|---------------------------------------------|
| **T1: Type Inference** | Determines all types are Float64 |
| **T2: Type Lattice** | Provides tmerge for control flow (not needed here) |
| **T3: tfuncs** | Knows `mul_float(Float64, Float64) -> Float64` |
| **T4: SSA IR** | Provides IRCode representation for optimization |
| **T5: Optimization** | Inlines and eliminates the Point allocation |
| **T6: Escape Analysis** | Confirms Point doesn't escape (enabling SROA) |
| **T7: Effects** | Marks as pure (enabling ADCE) |
| **T8: Caching** | Stores result so second call is instant |

### Performance Impact

| Compilation Stage | What Would Happen Without It |
|-------------------|------------------------------|
| Type inference | 100x slower (dynamic dispatch for every operation) |
| Inlining | 10x slower (function call overhead) |
| SROA | 10x slower (heap allocations for Points) |
| ADCE | Minor impact (some dead stores) |
| LLVM optimization | 2x slower (no vectorization, poor register allocation) |

---

## Further Reading

- [01-type-inference.md](./01-type-inference.md) - How types flow through code
- [02-type-lattice.md](./02-type-lattice.md) - The mathematical foundation
- [04-ssa-ir.md](./04-ssa-ir.md) - The IRCode representation
- [05-optimization.md](./05-optimization.md) - Inlining and SROA details
- [06-escape-analysis.md](./06-escape-analysis.md) - When allocations can be eliminated
- [07-effects.md](./07-effects.md) - Pure functions and optimization
- [08-caching.md](./08-caching.md) - CodeInstance and invalidation
- [interconnect-map.md](./interconnect-map.md) - How all subsystems connect

---

*Document generated for Julia compiler internals study. Based on Julia commit [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c).*
