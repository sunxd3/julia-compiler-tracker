# Julia Compiler Deep Dive: Practical Debugging Guide

Quick reference for inspecting compiler behavior with `@code_warntype`, `@code_typed`, and related tools.

---

## Table of Contents

1. [Quick Reference: @code_* Macros](#1-quick-reference-code_-macros)
2. [@code_lowered](#2-code_lowered)
3. [@code_typed](#3-code_typed)
4. [@code_warntype](#4-code_warntype)
5. [@code_llvm and @code_native](#5-code_llvm-and-code_native)
6. [Base.infer_effects](#6-baseinfer_effects)
7. [Cthulhu.jl](#7-cthulujl)
8. [SnoopCompile](#8-snoopcompile)
9. [Cheat Sheet](#9-cheat-sheet)

---

## 1. Quick Reference: @code_* Macros

| Macro | Shows | When to Use |
|-------|-------|-------------|
| `@code_lowered` | Desugared AST before type inference | Understanding how Julia expands syntax constructs |
| `@code_typed` | SSA IR with inferred types | Investigating type inference results and instability |
| `@code_warntype` | Type-annotated IR with color coding | Quick identification of type instability |
| `@code_llvm` | LLVM IR | Checking if Julia optimizations reached LLVM correctly |
| `@code_native` | Machine assembly | Final generated code, allocation patterns |

**Decision flow:**

```
"Why is my code slow?"
        |
        v
+------------------+     Type instability?     +------------------+
| @code_warntype   | -----------------------> | Fix type issues  |
+------------------+                          +------------------+
        |
        | Types look good
        v
+------------------+     See allocations?      +------------------+
| @code_llvm       | -----------------------> | Check boxing     |
+------------------+                          +------------------+
        |
        | Need more detail
        v
+------------------+
| @code_native     |
+------------------+
```

---

## 2. @code_lowered

### What It Shows

`@code_lowered` displays the **desugared AST** - the intermediate representation after Julia has expanded macros and syntactic sugar but before type inference runs.

### When to Use

- Understanding how `for` loops, generators, and comprehensions expand
- Debugging macro behavior
- Seeing the raw control flow structure

### Basic Usage

```julia
julia> function example(x)
           for i in 1:x
               println(i)
           end
       end

julia> @code_lowered example(5)
CodeInfo(
1 - %1 = 1:x
|   %2 = Base.iterate(%1)
|   %3 = %2 === nothing
|   %4 = Base.not_int(%3)
+-- goto #4 if not %4
2 - %5 = Base.indexed_iterate(%2, 1)
|   i = Core.getfield(%5, 1)
|   %7 = Core.getfield(%5, 2)
|   Main.println(i)
|   %9 = Base.iterate(%1, %7)
|   %10 = %9 === nothing
|   %11 = Base.not_int(%10)
+-- goto #4 if not %11
3 - goto #2
4 - return nothing
)
```

### Reading the Output

| Element | Meaning |
|---------|---------|
| `%1`, `%2`, ... | SSA values (intermediate results) |
| `1 -`, `2 -`, ... | Basic block numbers |
| `goto #4 if not %4` | Conditional branch |
| `i = ...` | Assignment to local variable |
| `+--` | Control flow instruction |

### Key insight

`@code_lowered` shows **no type information** - it is purely structural. Use it to understand control flow, not performance.

---

## 3. @code_typed

### Basic Usage

```julia
julia> function sum_example(v::Vector{Int})
           total = 0
           for x in v
               total += x
           end
           return total
       end

julia> @code_typed sum_example([1,2,3])
CodeInfo(
1 - %1 = Base.arraylen(v)::Int64
+-- goto #7 if not true
2 - %3 = Base.arrayref(true, v, 1)::Int64
|   %4 = Base.add_int(0, %3)::Int64
|   %5 = Base.add_int(1, 1)::Int64
+-- goto #4 if not true
3 - %7 = Base.slt_int(%5, %1)::Bool
+-- goto #5 if not %7
... (continues)
) => Int64
```

### optimize=false vs optimize=true

```julia
# See types BEFORE optimization passes
@code_typed optimize=false sum_example([1,2,3])

# See types AFTER optimization (default)
@code_typed optimize=true sum_example([1,2,3])
```

**When to use each:**

| Option | Use Case |
|--------|----------|
| `optimize=false` | See raw inference results, debug type instability |
| `optimize=true` | See what actually gets compiled, check inlining |

### Reading SSA Values and Types

```
%3 = Base.arrayref(true, v, 1)::Int64
^    ^                         ^
|    |                         +-- Inferred return type
|    +-- Statement (function call)
+-- SSA value number
```

**Type annotations to watch:**

| Pattern | Meaning | Action |
|---------|---------|--------|
| `::Int64` | Concrete type | Good |
| `::Any` | Type unknown | Investigate |
| `::Union{Int64, Float64}` | Union type | May need fixing |
| `::Union{Int64, Nothing}` | Nullable type | Often acceptable |

### Identifying Type Instability

Look for these patterns:

```julia
# BAD: Type instability
%5 = (Main.compute)(x)::Any
%6 = (Main.process)(%5)::Any  # Cascading instability

# BAD: Large unions
%7 = phi(#2 => %3, #3 => %4)::Union{Int64, Float64, String}

# GOOD: Concrete types throughout
%5 = Base.add_int(%3, %4)::Int64
%6 = Base.mul_int(%5, 2)::Int64
```

### Programmatic Access

```julia
# Get the result as a data structure
result = code_typed(sum_example, (Vector{Int},); optimize=true)

# Returns Vector{Pair{CodeInfo, DataType}}
ci, rt = only(result)

# ci is the CodeInfo, rt is the return type
println("Return type: ", rt)

# Access statement types
for (i, stmt) in enumerate(ci.code)
    println("$i: $stmt :: $(ci.ssavaluetypes[i])")
end
```

---

## 4. @code_warntype

### Basic Usage

```julia
julia> function unstable_example(x)
           if x > 0
               return 1
           else
               return 1.0
           end
       end

julia> @code_warntype unstable_example(5)
MethodInstance for unstable_example(::Int64)
  from unstable_example(x) @ Main REPL[1]:1
Arguments
  #self#::Core.Const(unstable_example)
  x::Int64
Body::Union{Float64, Int64}
1 - %1 = (x > 0)::Bool
+-- goto #3 if not %1
2 - return 1
3 - return 1.0
```

### Color Coding Explanation

In a terminal with color support:

| Color | Meaning | Example |
|-------|---------|---------|
| **Red** | Type instability (::Any, large Union) | `Body::Union{Float64, Int64}` |
| **Yellow** | Small union (2-3 types), may be acceptable | `::Union{Nothing, Int64}` |
| **Normal/Blue** | Concrete type, good performance | `::Int64` |

### Common Patterns to Look For

**Pattern 1: Return type instability**
```julia
Body::Union{Float64, Int64}  # RED - different return types on branches
```

**Pattern 2: Field access instability**
```julia
%3 = Base.getproperty(%1, :data)::Any  # RED - untyped field
```

**Pattern 3: Container element instability**
```julia
%2 = Base.getindex(%1, 1)::Any  # RED - Vector{Any} or similar
```

**Pattern 4: Global variable access**
```julia
%1 = Main.global_var::Any  # RED - non-const global
```

### Quick Fix Patterns

| Problem | Solution |
|---------|----------|
| Different return types | Use consistent types or parametric return |
| Untyped struct field | Add type parameter or annotation |
| Vector{Any} | Use concrete element type |
| Non-const global | Make `const` or pass as argument |

---

## 5. @code_llvm and @code_native

### When You Need These

Use `@code_llvm` and `@code_native` when:
- Types look fine but performance is still poor
- You suspect unnecessary allocations or boxing
- You need to verify vectorization or SIMD
- You are debugging ccall or unsafe code

### @code_llvm: What to Look For

```julia
julia> @code_llvm debuginfo=:none sum_example([1,2,3])
```

**Key patterns to identify:**

| LLVM Pattern | Meaning | Performance Impact |
|--------------|---------|-------------------|
| `gc_preserve_begin` / `gc_preserve_end` | GC roots preserved | Normal for Julia |
| `jl_box_int64` | Integer boxing | Slow - investigate |
| `jl_apply_generic` | Dynamic dispatch | Very slow |
| `alloca` | Stack allocation | Fast, local memory |
| `call void @julia.write_barrier` | Heap write barrier | Normal for mutable structs |

**Example of boxing (bad):**
```llvm
%4 = call nonnull {}* @jl_box_int64(i64 signext %3)
```
This indicates the compiler had to box an integer, often due to type instability.

### @code_native: Final Assembly

```julia
julia> @code_native debuginfo=:none sum_example([1,2,3])
```

**Look for:**

| Pattern | Meaning |
|---------|---------|
| `callq *%r...` or `call ...` to runtime | Runtime function call |
| `movq` to/from heap addresses | Memory operations |
| Tight loop without calls | Well-optimized inner loop |
| SIMD instructions (`vaddpd`, `vmulps`) | Vectorization succeeded |

### Useful Options

```julia
# Remove debug info for cleaner output
@code_llvm debuginfo=:none f(args...)
@code_native debuginfo=:none f(args...)

# Show raw output (no syntax highlighting)
@code_llvm raw=true f(args...)

# Dump to file for analysis
open("output.ll", "w") do io
    code_llvm(io, f, (ArgTypes,); debuginfo=:none)
end
```

---

## 6. Base.infer_effects

The `Base.infer_effects` function allows you to query the compiler's effect analysis for any method. There is also a convenient `@infer_effects` macro for interactive use:

```julia
julia> @infer_effects sin(1.0)
(+c,+e,+n,+t,+s,+m,+u,+o,+r)
```

### Reading Effect Strings

```julia
julia> Base.infer_effects(sin, (Float64,))
(+c,+e,+n,+t,+s,+m,+u,+o,+r)

julia> Base.infer_effects(println, (String,))
(-c,-e,-n,+t,-s,-m,+u,+o,+r)
```

### Effect Symbol Reference

| Symbol | Effect | `+` (Good) | `-` (Bad) | `?` (Conditional) |
|--------|--------|------------|-----------|-------------------|
| `c` | consistent | Same inputs -> same outputs | May vary | Depends on escape |
| `e` | effect_free | No side effects | Has side effects | Conditionally pure |
| `n` | nothrow | Never throws | May throw | - |
| `t` | terminates | Always terminates | May loop forever | - |
| `s` | notaskstate | No task-local state | Uses task state | - |
| `m` | inaccessiblememonly | Only local memory | External memory | Arg memory only |
| `u` | noub | No undefined behavior | May have UB | Safe if bounds checked |
| `o` | nonoverlayed | No method overlays | Uses overlays | Consistent overlays |
| `r` | nortcall | No return_type calls | Calls return_type | - |

### What Each Effect Means for Performance

| Effect | When Missing (-) | Performance Impact |
|--------|------------------|-------------------|
| `consistent` | Function may return different results | Cannot cache or CSE |
| `effect_free` | Has observable side effects | Cannot eliminate unused calls |
| `nothrow` | May throw exceptions | Cannot simplify exception handling |
| `terminates` | May not terminate | Cannot evaluate at compile time |
| `noub` | May have undefined behavior | Limits optimization scope |

### Practical Examples

```julia
# Check why constant folding fails
julia> Base.infer_effects(factorial, (Int,))
(+c,+e,-n,-t,+s,+m,+u,+o,+r)
#          ^^-^^ -- may throw, may not terminate

# Check if function can be eliminated if unused
julia> using Core.Compiler: is_removable_if_unused
julia> effects = Base.infer_effects(+, (Int, Int))
julia> is_removable_if_unused(effects)
true

# Check if function can be constant-folded
julia> using Core.Compiler: is_foldable
julia> is_foldable(Base.infer_effects(sin, (Float64,)))
true
```

---

## 7. Cthulhu.jl

### Installation and Basic Usage

```julia
using Pkg
Pkg.add("Cthulhu")
using Cthulhu
```

### Interactive Descent Through Call Tree

```julia
julia> function outer(x)
           y = inner(x)
           return y * 2
       end

julia> inner(x) = x + 1

julia> @descend outer(5)
```

This opens an interactive session:

```
outer(x) @ Main REPL[1]:1
│ ─ %-1  = invoke outer(::Int64)::Int64
│    ─── ↓ show_ir

Body::Int64
1 ─ %1 = invoke inner(x::Int64)::Int64
│   %2 = Base.mul_int(%1, 2)::Int64
└──      return %2

Select a call to descend into or ↩ to ascend.
 • %1 = invoke inner(::Int64)::Int64
   ↩
```

### Key Commands

| Key | Action |
|-----|--------|
| `Enter` | Descend into selected call |
| `Backspace` | Ascend to caller |
| `↑`/`↓` | Navigate between calls |
| `Space` | Toggle branch-folding |
| `b` | Toggle bookmarks |
| `o` | Toggle optimization (`optimize=true/false`) |
| `t` | Toggle typed/untyped view |
| `w` | Toggle warn mode (like `@code_warntype`) |
| `q` | Quit |
| `?` | Show help |

### Useful Workflows

**Finding the source of type instability:**

```julia
@descend_code_warntype problematic_function(args...)
```

Then press `Enter` to descend into red-highlighted calls until you find the root cause.

**Comparing optimized vs unoptimized:**

1. Run `@descend f(args...)`
2. Press `o` to toggle optimization
3. Compare the IR before and after

**Checking inlining decisions:**

1. Run `@descend f(args...)`
2. With `optimize=true`, inlined calls disappear
3. Non-inlined calls remain as `invoke`

### ascend: Tracing Back from a Function

```julia
# Find all callers of a function
@ascend inner(5)
```

This shows the call stack and lets you navigate upward.

---

## 8. SnoopCompile

### Installation

```julia
using Pkg
Pkg.add("SnoopCompile")
using SnoopCompile
```

**Note**: SnoopCompile API has evolved. For Julia 1.6+, the preferred macros are:
- `@snoop_invalidations` (formerly `@snoopr`)
- `@snoop_inference` (formerly `@snoopi_deep`)

### Finding Invalidations

Invalidations occur when method definitions cause previously compiled code to become invalid.

```julia
# Record invalidations
using SnoopCompileCore
invalidations = @snoop_invalidations begin
    # Code that might cause invalidations
    using SomePackage
end

# Analyze invalidations
using SnoopCompile
trees = invalidation_trees(invalidations)

# Show the most impactful invalidations
show(trees[end])
```

### Understanding Invalidation Output

```
inserting f(::Int) @ Main invalidated:
   backedges: 1: superseding f(::Any) @ Main with MethodInstance for g(::Any)
              2: superseding f(::Any) @ Main with MethodInstance for h(::Float64)
```

This means:
- Adding `f(::Int)` invalidated code that called `f(::Any)`
- Functions `g` and `h` had compiled code that now needs recompilation

### Identifying Inference Triggers

```julia
using SnoopCompileCore
tinf = @snoop_inference begin
    # Code to analyze
    my_function(args...)
end

using SnoopCompile
# Find inference triggers
itrigs = inference_triggers(tinf)

# Filter to runtime dispatches
runtime_dispatches = filter(itrigs) do itrig
    itrig.callerframes[1].linfo.def.module == Main
end

# Show the triggers
for itrig in runtime_dispatches
    println(itrig)
end
```

### Flamegraph Visualization

```julia
using SnoopCompile, ProfileView

tinf = @snoop_inference my_function(args...)

# Generate flamegraph
fg = flamegraph(tinf)

# View it (requires ProfileView or similar)
ProfileView.view(fg)
```

### Precompilation Workflow

```julia
# 1. Record what gets compiled
tinf = @snoop_inference begin
    include("test/runtests.jl")
end

# 2. Generate precompile statements
pc = SnoopCompile.parcel(tinf)

# 3. Write to a file
SnoopCompile.write("precompile.jl", pc)
```

---

## 9. Cheat Sheet

### Quick Diagnosis Commands

```julia
# Is there type instability?
@code_warntype f(args...)

# What types does inference compute?
@code_typed optimize=false f(args...)

# What effects does this function have?
Base.infer_effects(f, (ArgTypes,))

# Is this function being boxed?
@code_llvm debuginfo=:none f(args...)

# Deep dive into call tree
using Cthulhu; @descend f(args...)
```

### Type Instability Checklist

| Check | Command | Look For |
|-------|---------|----------|
| Return type | `@code_warntype` | Red `Body::Union{...}` |
| Intermediate values | `@code_typed` | `::Any` or `::Union{...}` |
| Field access | `@code_warntype` | Red `getproperty` results |
| Container elements | `@code_typed` | `getindex` returning `::Any` |
| Globals | `@code_warntype` | Red variable names |

### Effects Quick Reference

| Want To... | Effect Needed | Check With |
|------------|---------------|------------|
| Constant fold | `+c+e+t` and (`+u` or `?u`) | `is_foldable(effects)` |
| DCE unused calls | `+e+n+t` | `is_removable_if_unused(effects)` |
| Cache results | `+c` | `is_consistent(effects)` |
| Inline finalizer | `+n+s` | `is_finalizer_inlineable(effects)` |

**Note**: For foldability, `?u` (NOUB_IF_NOINBOUNDS) is also acceptable, not just `+u`. This allows constant folding when bounds checking ensures no undefined behavior.

### Common Fixes

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| Slow loop | `@code_warntype` shows red in loop | Type-stabilize loop variable |
| Allocation in hot path | `@code_llvm` shows `jl_box_*` | Use concrete types |
| Dynamic dispatch | `@code_llvm` shows `jl_apply_generic` | Add type annotations |
| Cannot constant fold | `infer_effects` shows `-t` | Add `@assume_effects :terminates_globally` |
| Invalidation storm | `@snoop_invalidations` shows many trees | Narrow method signatures |

### Tool Selection Guide

```
Need to...                              Use...
-----------------------------------------------
Quick type check                        @code_warntype
Detailed type analysis                  @code_typed optimize=false
Check optimization results              @code_typed optimize=true
Investigate boxing/allocation           @code_llvm
See generated assembly                  @code_native
Interactive exploration                 Cthulhu.jl @descend
Find invalidations                      SnoopCompile @snoop_invalidations
Profile compilation                     SnoopCompile @snoop_inference
```

### Useful One-Liners

```julia
# Check if function is type-stable
is_stable(f, types) = Base.return_types(f, types)[1] != Any

# Get return type
return_type(f, types) = only(Base.return_types(f, types))

# Check for concrete return
is_concrete_return(f, types) = isconcretetype(return_type(f, types))

# Count methods for a function
num_methods(f) = length(methods(f))

# Find which method would be called
which_method(f, args...) = which(f, typeof.(args))
```

---

## Further Reading

- [Type Inference Deep Dive](./01-type-inference.md) - Understanding how Julia infers types
- [SSA IR Representation](./04-ssa-ir.md) - Reading the intermediate representation
- [Effects System](./07-effects.md) - Complete effects documentation
- [Cthulhu.jl Documentation](https://github.com/JuliaDebug/Cthulhu.jl)
- [SnoopCompile Documentation](https://github.com/timholy/SnoopCompile.jl)

Next: [12-method-dispatch.md](./12-method-dispatch.md)
