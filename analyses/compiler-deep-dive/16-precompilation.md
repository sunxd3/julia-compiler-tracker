# Julia Compiler Deep Dive: Precompilation and Latency

This tutorial explains how Julia reduces latency using precompilation, sysimages, and cached code.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [What Precompilation Is (and Isn't)](#1-what-precompilation-is-and-isnt)
2. [Cache File Formats](#2-cache-file-formats)
3. [Precompile Statements](#3-precompile-statements)
4. [PrecompileTools.jl and @compile_workload](#4-precompiletoolsjl-and-compile_workload)
5. [Sysimages and Package Images](#5-sysimages-and-package-images)
6. [Invalidation and Recompilation](#6-invalidation-and-recompilation)
7. [Practical Workflow](#7-practical-workflow)
8. [Summary](#8-summary)

---

## 1. What Precompilation Is (and Isn't)

Precompilation caches **inference results** and sometimes **compiled code** so that later calls avoid cold-start latency.

It does **not** guarantee zero runtime compilation:

- new argument types still trigger specialization
- invalidations can discard cached results

### 1.1 Types of Cached Artifacts

Julia uses three distinct types of cached artifacts:

- **System images** (`sys.ji` + `sys.so`/`sys.dll`/`sys.dylib`): Contains Base and stdlibs. The `.ji` file holds serialized Julia IR, while the shared library (`.so`/`.dll`/`.dylib`) contains native compiled code. Loaded at Julia startup.

- **Package images** (`.ji` + optional `.so`/`.dll`/`.dylib`): Per-package caches that can include both inference results and native code. When native code is included, a shared library is generated alongside the `.ji` file.

- **Precompile cache files** (`.ji` only): Contains only inference results (serialized Julia IR) without native code. Faster to generate but requires JIT compilation at load time.

---

## 2. Cache File Formats

Julia stores cached compilation results in specific file formats:

- **`.ji` files**: Serialized Julia IR containing inference results, type information, and method tables. This is the standard extension for all precompile caches.

- **`.so` / `.dll` / `.dylib` files**: Platform-specific shared libraries containing native compiled code. Used by system images and package images when native code caching is enabled.

The separation allows Julia to store inference results (which are portable) separately from native code (which is platform-specific).

---

## 3. Precompile Statements

You can ask Julia to precompile specific call signatures:

```julia
precompile(f, (Int, Float64))
```

This helps if you know your hot call signatures ahead of time.

**Source**: [`precompile`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/loading.jl#L4524-L4540)

### 3.1 Checking if a Call Is Precompilable

```julia
isprecompilable(f, (Int, Float64))
```

**Source**: [`isprecompilable`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/loading.jl#L4510-L4522)

---

## 4. PrecompileTools.jl and @compile_workload

The modern standard for package precompilation is `PrecompileTools.jl` (formerly `SnoopCompileCore`). This package provides the `@compile_workload` macro for declarative precompilation.

### 4.1 Basic Usage

```julia
using PrecompileTools

@compile_workload begin
    # Code here will be executed during precompilation
    # All methods called will be precompiled
    my_function(1, 2.0)
    another_function("hello")
end
```

### 4.2 How It Works

The `@compile_workload` macro:

1. Executes the workload code during package precompilation
2. Automatically captures all method invocations
3. Generates appropriate `precompile` directives for discovered signatures
4. Handles edge cases like generated functions and closures

This is more robust than manual `precompile` statements because it:

- Discovers all transitive call signatures automatically
- Handles dynamic dispatch correctly
- Adapts to code changes without manual updates

### 4.3 Conditional Workloads

For version-specific or conditional precompilation:

```julia
@compile_workload begin
    # Always precompile
    core_function(x)
end

@static if VERSION >= v"1.9"
    @compile_workload begin
        # Only on Julia 1.9+
        new_feature()
    end
end
```

**Note**: `@compile_workload` is provided by `PrecompileTools.jl`, not Base Julia. Add it as a dependency to use it.

---

## 5. Sysimages and Package Images

Sysimages bundle compiled code into a shared binary loaded at startup. Package images extend this idea to package-specific caches.

These approaches reduce:

- time to first plot / first solve / first compile
- repeated inference work across sessions

### 5.1 Loading Cached Precompile Artifacts

When a module or package is loaded, Julia attempts to reuse cached precompile artifacts:

- `maybe_loaded_precompile` handles lookup and loading

**Source**: [`maybe_loaded_precompile`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/loading.jl#L2742-L2755)

### 5.2 Parallel Package Precompilation

The `precompilepkgs` function is the main entry point for parallel package precompilation. It coordinates precompilation of multiple packages simultaneously, respecting dependency ordering and utilizing available CPU cores.

**Source**: [`precompilepkgs`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/base/precompilation.jl#L474-L561)

### 5.3 PackageCompiler.jl

For creating custom sysimages, `PackageCompiler.jl` is the standard tool recommended in Julia's documentation. It provides:

- `create_sysimage()`: Build a custom sysimage with selected packages
- `create_app()`: Create standalone applications
- `create_library()`: Build shared libraries callable from C

Example usage:

```julia
using PackageCompiler

create_sysimage(
    [:MyPackage, :OtherPackage];
    sysimage_path="custom_sysimage.so",
    precompile_execution_file="workload.jl"
)
```

This is particularly useful for deployment scenarios where startup latency is critical.

---

## 6. Invalidation and Recompilation

Precompiled code is only valid within a **world age range**. When methods are redefined:

- backedges mark cached code as stale
- inference and codegen re-run as needed

See [08 - Caching](08-caching.md) for invalidation details.

### 6.1 Precompile Worklist and Emission

During precompilation, Julia builds a worklist of method instances to compile:

- `enqueue_specializations!` walks new methods and their specializations
- `enqueue_specialization!` decides which instances are worth compiling

**Source**: [`precompile.jl`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/precompile.jl#L277-L338)

### 6.2 Native Code Emission

Native artifact emission involves both Julia and runtime components:

On the Julia side, `compile_and_emit_native` handles the compilation pipeline:

- Processes the worklist of method instances
- Invokes codegen for each method
- Prepares native code for serialization

**Source**: [`compile_and_emit_native`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/precompile.jl#L341-L426)

On the runtime side, `jl_write_compiler_output` writes the actual binary output:

- Serializes compiled code to disk
- Handles platform-specific shared library formats

**Source**: [`jl_write_compiler_output`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/precompile.c#L98-L149)

---

## 7. Practical Workflow

1. Use `PrecompileTools.jl` with `@compile_workload` for automatic signature discovery
2. Use `SnoopCompile.jl` to analyze and identify hot call signatures
3. Add targeted `precompile` statements for edge cases
4. Consider `PackageCompiler.jl` for sysimage creation in latency-critical apps

### 7.1 Quick Sanity Check

If a `precompile` statement is inactive, you can enable warnings:

```julia
Base.ENABLE_PRECOMPILE_WARNINGS[] = true
```

This helps ensure your precompile statements are actually used.

---

## 8. Summary

- Precompilation reduces latency but doesn't eliminate specialization.
- Cache files use `.ji` for IR and `.so`/`.dll`/`.dylib` for native code.
- System images, package images, and precompile caches serve different purposes.
- Use `PrecompileTools.jl` with `@compile_workload` for modern package precompilation.
- Use `PackageCompiler.jl` for custom sysimage creation.
- Invalidation can erase cached results.
- Combining workload-based precompilation with sysimages yields the best results.
