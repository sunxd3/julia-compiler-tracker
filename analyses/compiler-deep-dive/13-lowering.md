# Julia Compiler Deep Dive: Lowering (AST -> CodeInfo)

This tutorial explains Julia's **lowering** phase: how parsed syntax and macros become a lowered `CodeInfo` object that the compiler can analyze.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

**Source anchors**: `julia/src/ast.c`, `julia/src/ast.scm`, `julia/src/julia-syntax.scm`, `julia/src/jlfrontend.scm`, and `julia/src/macroexpand.scm`.

---

## Table of Contents

1. [From Surface Syntax to Lowered Code](#1-from-surface-syntax-to-lowered-code)
2. [What Lowering Produces: CodeInfo](#2-what-lowering-produces-codeinfo)
3. [Key Lowering Transformations](#3-key-lowering-transformations)
4. [How to Inspect Lowered Code](#4-how-to-inspect-lowered-code)
5. [Why Lowering Matters for Performance](#5-why-lowering-matters-for-performance)
6. [Summary](#6-summary)

---

## 1. From Surface Syntax to Lowered Code

Julia compilation begins with:

1. **Parsing** into an AST (expressions like `Expr(:call, ...)`)
2. **Macro expansion** (`@foo` -> rewritten AST)
3. **Scope resolution** (determining soft scope vs hard scope for variable bindings)
4. **Lowering**, which rewrites syntax into a smaller core language and constructs `CodeInfo`

Lowering is the point where:

- syntactic sugar is removed
- control flow is normalized (e.g., `for` -> `while`)
- property access (`x.f`) becomes calls to `getproperty`
- keyword arguments become explicit `Core.kwcall` calls

### 1.1 Entry Points (C and Core)

The main C entry point is `jl_lower`, which delegates to `jl_fl_lower` during bootstrap
or to `Core._lower` when available.

**Sources**:
- [`jl_lower`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/ast.c#L1247-L1276)
- [`jl_fl_lower`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/ast.c#L1196-L1243)

Macro expansion happens in `jl_expand_macros` before lowering proper:

- [`jl_expand_macros`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/ast.c#L1088-L1188)

Macro hygiene (gensym handling, module context) is implemented in `macroexpand.scm`.

The main flisp entry points for lowering are in `jlfrontend.scm`:
- `jl-lower-to-thunk` wraps lowered code in a thunk for evaluation
- `lower-toplevel-expr` handles top-level expression lowering

---

## 2. What Lowering Produces: CodeInfo

The output of lowering is a `CodeInfo` object, a compact representation of a function:

```julia
julia> @code_lowered f(1, 2)
CodeInfo(
1 - %1 = ...
|   ...
+-- return %n
)
```

`CodeInfo` includes:

- a flat list of statements
- slot (local variable) information
- control flow structure
- placeholder fields that inference will later fill

### 2.1 The "lower-to-thunk" step

During bootstrap, `jl_fl_lower` calls into the flisp lowering pipeline (`jl-lower-to-thunk`),
which returns a lowered representation wrapped in a thunk object.

**Source**: [`jl_fl_lower`](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/src/ast.c#L1196-L1243)

---

## 3. Key Lowering Transformations

Some common rewrites:

| Surface syntax | Lowered form |
|---------------|--------------|
| `x.y` | `getproperty(x, :y)` |
| `x.y = v` | `setproperty!(x, :y, v)` |
| `for i in itr` | `while iterate(...)` |
| `x^2` | `Base.literal_pow(^, x, Val(2))` |
| keyword args | `Core.kwcall(kw, f, args...)` |

These rewrites explain why compiler internals often talk in terms of `getfield`, `getproperty`, `invoke`, and `kwcall`.

### 3.1 Walkthrough: `for` loop lowering

```julia
function demo(xs)
    s = 0
    for x in xs
        s += x
    end
    return s
end
```

```julia
@code_lowered demo([1,2,3])
```

You will see:

- `iterate(xs)` calls
- `nothing` checks for loop exit
- explicit `goto`-based control flow

This is why the compiler's internal IR looks like explicit state machines.

---

## 4. How to Inspect Lowered Code

Use these tools:

```julia
@code_lowered f(args...)
```

and for programmatic access:

```julia
ci = first(code_lowered(f, Tuple{ArgTypes...}))
```

Lowered code is **not typed** yet. It is structural.

---

## 5. Why Lowering Matters for Performance

Lowering shapes how inference sees your code:

- Generated control flow influences type merges (`tmerge`)
- `getproperty` / `setproperty!` vs. `getfield` determines whether tfuncs can reason precisely
- Keyword argument lowering can introduce allocations if not optimized away

Understanding lowering helps you interpret `@code_lowered`, `@code_typed`, and `@code_warntype` output.

---

## 6. Summary

- Lowering converts high-level syntax into a small core language.
- The output is `CodeInfo`, the input to inference.
- Many performance questions begin with "what did this lower to?"

Next: [14-codegen.md](./14-codegen.md)
