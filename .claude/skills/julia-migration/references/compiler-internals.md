# Julia Compiler Internals — Where to Look

Guide for navigating compiler source when investigating changes. Don't rely on details here — read the actual source files, as struct fields and APIs change between versions.

## Key source files

All paths below are relative to `Compiler/src/` in 1.12+, or `base/compiler/` in 1.11 and earlier.

### Module entrypoint
| File | What to look for |
|------|-----------------|
| `Compiler.jl` | Module entrypoint — include order, exports. Start here to see what files exist |

### Type inference
| File | What to look for |
|------|-----------------|
| `abstractinterpretation.jl` | Main inference loop, `abstract_call*` family, call resolution |
| `typeinfer.jl` | Inference driver, cycle handling, effect adjustment |
| `inferencestate.jl` | `InferenceState` struct — the per-frame inference context |
| `types.jl` | `InferenceResult`, `VarState`, `InferenceParams`, `CallInfo` abstract root |

### Type lattice
| File | What to look for |
|------|-----------------|
| `typelattice.jl` | Extended lattice elements: `Conditional`, `MustAlias`, `PartialTypeVar`, `LimitedAccuracy`. Lattice operations: `⊑`, `widenconst` |
| `typelimits.jl` | Widening: `tmerge`, `tuplemerge`, complexity limits |
| `abstractlattice.jl` | Lattice layer composition (`BaseInferenceLattice`, `IPOResultLattice`, etc.), `tmeet` |

### Type functions and effects
| File | What to look for |
|------|-----------------|
| `tfuncs.jl` | Builtin/intrinsic type functions (`getfield_tfunc`, etc.), effect classification lists |
| `effects.jl` | `Effects` struct, effect bit flags, predicates like `is_foldable`, `is_removable_if_unused` |
| `stmtinfo.jl` | `CallInfo` subtypes (`MethodMatchInfo`, `InvokeCallInfo`, etc.) — new subtypes added across versions |

### SSA IR
| File | What to look for |
|------|-----------------|
| `ssair/ir.jl` | `IRCode`, `InstructionStream`, `CFG`, `IncrementalCompact` |
| `ssair/basicblock.jl` | `BasicBlock` struct |
| `optimize.jl` | IR flags (`IR_FLAG_*`), optimization pass pipeline (`run_passes_ipo_safe`) |
| `ssair/inlining.jl` | Inlining analysis and execution |
| `ssair/passes.jl` | SROA, ADCE, other optimization passes |
| `ssair/EscapeAnalysis.jl` | Escape analysis — `EscapeInfo`, alias tracking |
| `ssair/verify.jl` | SSA IR verification |
| `validation.jl` | CodeInfo validation |

### Caching and invalidation
| File | What to look for |
|------|-----------------|
| `cicache.jl` | `CodeInstance` lookup, `WorldRange` |
| `reinfer.jl` | Precompile revalidation, backedge verification |

### Codegen (C++, paths relative to repo root)
| File | What to look for |
|------|-----------------|
| `src/codegen.cpp` | Entry point `jl_emit_codeinst`, function emission |
| `src/cgutils.cpp` | Load/store helpers, union handling, TBAA metadata |
| `src/intrinsics.cpp` | Intrinsic lowering to LLVM |
| `src/jitlayers.cpp` | JIT compilation, memory management |

### Bootstrap and compatibility (paths relative to repo root)
| File | What to look for |
|------|-----------------|
| `base/Base.jl` | `Core.Compiler = Base.Compiler` alias, JuliaSyntax/JuliaLowering activation |
| `base/boot.jl` | Core lattice types bootstrapped into `Core`: `Const`, `PartialStruct`, `InterConditional`, `PartialOpaque` |
| `base/coreir.jl` | Core IR and lattice object definitions |
| `base/flfrontend.jl` | Flisp parser/lowering entry points |

## What changes between versions

These are the surfaces most likely to break downstream packages. When investigating a version migration, read these structs/types in both the old and new version and diff them:

- **`InferenceState`** — fields added/removed/renamed across versions
- **`InferenceResult`** — fields evolve (e.g., `ci`/`ci_as_edge` are relatively new)
- **`Effects`** — new effect kinds added, conditional flag values change
- **`CallInfo` subtypes** — new subtypes appear per version
- **IR flags** — new flags added, bit positions shift
- **`IRCode` / `InstructionStream`** — field types evolve (e.g., `debuginfo` format, `new_nodes` type)
- **`CodeInstance`** — `edges` encoding and `inferred` type change
- **Lattice layer composition** — layer names and nesting change
- **Optimization pass order** — passes renamed, reordered, or added
