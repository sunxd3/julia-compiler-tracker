# Julia Compiler Deep Dive: Codegen (SSA IR -> LLVM -> Native)

This tutorial gives a high-level tour of Julia's **code generation** pipeline: how optimized SSA IR becomes LLVM IR and finally native machine code.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

**Source anchors**: `julia/src/codegen.cpp` and LLVM pass files in `julia/src/`.

---

## Table of Contents

1. [Where Codegen Fits](#1-where-codegen-fits)
2. [From IRCode to LLVM IR](#2-from-ircode-to-llvm-ir)
3. [Runtime Helpers and GC Interaction](#3-runtime-helpers-and-gc-interaction)
4. [LLVM Optimization and Native Emission](#4-llvm-optimization-and-native-emission)
5. [Inspecting Codegen Output](#5-inspecting-codegen-output)
6. [Summary](#6-summary)

---

## 1. Where Codegen Fits

After inference and optimization, Julia has **typed SSA IR**. Codegen:

1. Lowers SSA IR to LLVM IR
2. Inserts runtime calls (GC, exceptions, boxing) where needed
3. Runs LLVM optimization passes
4. Emits native machine code

This is where the compiler becomes architecture-specific.

### 1.1 Entry Points in `codegen.cpp`

The main entry point for emitting LLVM is `jl_emit_codeinst`, which calls:

- `jl_emit_code` (per-method-instance emission)
- `emit_function` (core LLVM IR generation)

**Sources**:
- [`jl_emit_codeinst`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/codegen.cpp#L10193-L10215)
- [`jl_emit_code`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/codegen.cpp#L10127-L10169)

### 1.2 Supporting Source Files

Beyond `codegen.cpp`, several other files are essential to code generation:

- **`cgutils.cpp`** (~236KB): Essential utility procedures for boxing, unboxing, type checks, and pointer manipulation
- **`intrinsics.cpp`** (~80KB): Handles intrinsic lowering; see [`emit_intrinsic`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/intrinsics.cpp#L1335) for intrinsic emission
- **`ccall.cpp`**: Handles foreign function interface (FFI) and C call code generation
- **`jitlayers.cpp`** (~110KB): Handles JIT compilation pipeline using LLVM ORC
- **`aotcompile.cpp`**: Ahead-of-time compilation for system images and pkgimages

---

## 2. From IRCode to LLVM IR

Key responsibilities:

- Emit LLVM instructions for arithmetic, control flow, and calls
- Materialize boxes for `Any`/union values as needed
- Respect effect flags (`nothrow`, `effect_free`, etc.)

The main implementation lives in `julia/src/codegen.cpp`.

### 2.1 Specsig vs. Fptr Wrappers

Julia emits either a **specialized signature function** ("specsig") or a generic `jl_fptr_*` wrapper
depending on ABI and specialization details.

**Source**: [`jl_emit_codedecls`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/codegen.cpp#L10094-L10124)

### 2.2 Invoke and ABI Wrappers

Codegen also emits wrappers to bridge between generic calling conventions and specialized ABI:

- `emit_tojlinvoke` creates an entry point compatible with `jl_invoke`
- `emit_abi_dispatcher` and `emit_abi_converter` adapt between ABIs

**Sources**:
- [`emit_tojlinvoke`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/codegen.cpp#L7144-L7176)
- [`emit_abi_dispatcher`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/codegen.cpp#L7444-L7467)

---

## 3. Runtime Helpers and GC Interaction

Codegen must coordinate with the runtime for:

- **Garbage collection** (rooting, safepoints)
- **Exceptions** (throw paths and landing pads)
- **Boxing/unboxing** (heap-allocated values vs. raw bits)

### 3.1 Address Spaces for GC Tracking

Julia uses LLVM address spaces to track GC-managed pointers:

- **`AddressSpace::Tracked`**: Heap-allocated objects managed by the GC
- **`AddressSpace::Derived`**: Pointers derived from tracked objects (interior pointers)
- **`AddressSpace::Loaded`**: Pointers loaded from tracked objects

These address spaces enable the GC lowering passes to correctly identify and root GC-managed values.

### 3.2 LLVM Passes for GC and Optimization

Several Julia-specific LLVM passes in `julia/src/` handle GC lowering and optimization:

**GC passes**:
- `llvm-late-gc-lowering*.cpp` - Lowers GC intrinsics to runtime calls
- `llvm-final-gc-lowering.cpp` - Final GC lowering stage

**Optimization passes**:
- `llvm-alloc-opt.cpp` - Allocation optimization (escape analysis, stack allocation)
- `llvm-julia-licm.cpp` - Julia-specific loop-invariant code motion
- `llvm-multiversioning.cpp` - CPU feature dispatching for multiple code versions
- `llvm-simdloop.cpp` - SIMD optimization for vectorizable loops

These passes are critical to both correctness and performance.

### 3.3 Safepoints and GC Roots

Codegen inserts safepoints and GC root tracking so the runtime can move and reclaim objects safely.
This is one reason `Any`-typed code is slower: it needs more rooting and boxing machinery.

---

## 4. LLVM Optimization and Native Emission

After LLVM IR is built, Julia runs LLVM's optimization pipeline and emits native code for the target architecture.

This is why:

- Small typed functions inline aggressively
- Concrete types unlock vectorization and constant folding
- Abstract types cause boxing and inhibit LLVM optimization

---

## 5. Inspecting Codegen Output

Tools:

```julia
@code_llvm f(args...)
@code_native f(args...)
```

Use `optimize=false` when you want to see IR before LLVM's passes:

```julia
@code_llvm optimize=false f(args...)
```

---

## 6. Summary

- Codegen translates optimized SSA IR into LLVM IR and native code.
- GC, exceptions, and boxing are inserted here.
- LLVM optimization quality depends on earlier inference precision.

Next: [11 - Practical Debugging](11-practical-debugging.md) for inspection workflows.
