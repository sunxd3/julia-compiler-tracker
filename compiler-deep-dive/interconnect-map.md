# Julia Compiler Interconnection Map

How compiler subsystems connect: shared data structures, data flow, and integration points.

---

## Table of Contents

1. [Subsystem Dependency Graph](#1-subsystem-dependency-graph)
2. [Shared Data Structures](#2-shared-data-structures)
3. [Data Flow Between Subsystems](#3-data-flow-between-subsystems)
4. [Cross-Reference Summary by Subsystem](#4-cross-reference-summary-by-subsystem)
5. [Key Functions Crossing Subsystem Boundaries](#5-key-functions-crossing-subsystem-boundaries)
6. [Architectural Patterns](#6-architectural-patterns)
7. [File-Level Dependencies](#7-file-level-dependencies)
8. [Summary Table](#8-summary-table)

---

## 1. Subsystem Dependency Graph

```
                            ┌─────────────────────┐
                            │   Core Runtime (C)  │
                            │  (CodeInstance,     │
                            │   MethodInstance,   │
                            │   world age)        │
                            └──────────┬──────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
       ▼                               ▼                               ▼
┌─────────────┐              ┌─────────────────┐              ┌─────────────┐
│ T2: Type    │◄─────────────│ T1: Type        │─────────────►│ T8: Caching │
│ Lattice     │              │ Inference       │              │ & Invalidate│
│ (foundation)│              │ (core engine)   │              │             │
└──────┬──────┘              └────────┬────────┘              └──────┬──────┘
       │                              │                               │
       │  lattice types               │ inference                     │ cache
       │  & operations                │ results                       │ lookup/store
       │                              │                               │
       ▼                              ▼                               │
┌─────────────┐              ┌─────────────────┐                      │
│ T3: tfuncs  │              │ T7: Effects     │◄─────────────────────┘
│ (builtin    │─────────────►│ System          │
│ type funcs) │  effects     │                 │
└─────────────┘              └────────┬────────┘
                                      │
                                      │ effect info
                                      ▼
                            ┌─────────────────┐
                            │ T4: SSA IR      │
                            │ (representation)│
                            └────────┬────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│ T5: Optimization│        │ T6: Escape      │        │ (LLVM Codegen)  │
│ Passes          │◄──────►│ Analysis        │        │                 │
│                 │        │                 │        │                 │
└─────────────────┘        └─────────────────┘        └─────────────────┘
```

---

## 2. Shared Data Structures

### 2.1 Core Runtime Types (defined in C/Core)

| Structure | Used By | Purpose |
|-----------|---------|---------|
| `MethodInstance` | T1, T5, T8, T16 | Specialized method for type signature |
| `CodeInstance` | T1, T8, T14, T16 | Compiled code with world age validity |
| `CodeInfo` / `jl_code_info_t` | T1, T4, T5, T13 | Lowered IR before optimization (lowered AST) |
| `Method` | T1, T8, T12 | Generic function definition |
| `InferenceParams` | T1, T15 | Compilation budgets and limits |
| `MethodLookupResult` | T1, T12 | Method search results with world-range |

### 2.2 Lattice Types (T2 → all)

| Type | Defined In | Used By |
|------|------------|---------|
| `Const` | Core (boot.jl) | T1, T2, T3, T5 |
| `PartialStruct` | Core (boot.jl) | T1, T2, T3, T5 |
| `Conditional` | T2 (typelattice.jl) | T1, T3 |
| `MustAlias` | T2 (typelattice.jl) | T1, T3 |
| `LimitedAccuracy` | T2 (typelattice.jl) | T1 |
| `VarState` | T2 (typelattice.jl) | T1, T4 |

### 2.3 Effects Types (T7 → T1, T3, T5)

| Type | Defined In | Used By |
|------|------------|---------|
| `Effects` | T7 (effects.jl) | T1, T3, T5, T8 |
| `IR_FLAG_*` | T5 (optimize.jl) | T5, T6, T7 |

### 2.4 IR Types (T4 → T5, T6)

| Type | Defined In | Used By |
|------|------------|---------|
| `IRCode` | T4 (ssair/ir.jl) | T1, T5, T6 |
| `CFG` | T4 (ssair/ir.jl) | T4, T5 |
| `IncrementalCompact` | T4 (ssair/ir.jl) | T5 |
| `SSAValue` | Core | T4, T5, T6 |

### 2.5 Inference State Types (T1 → T5, T8)

| Type | Defined In | Used By |
|------|------------|---------|
| `InferenceState` | T1 (inferencestate.jl) | T1, T2 |
| `InferenceResult` | T1 (inferenceresult.jl) | T1, T5, T8 |
| `CallInfo` | T1 (stmtinfo.jl) | T1, T5 |
| `OptimizationState` | T5 (optimize.jl) | T1, T5 |

---

## 3. Data Flow Between Subsystems

### 3.1 Type Inference Pipeline

```
Source Code
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ T1: Type Inference                                                   │
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │ T2: Lattice  │───►│ T3: tfuncs   │───►│ T7: Effects  │          │
│  │ (tmerge,     │    │ (return type │    │ (merge_      │          │
│  │  tmeet, ⊑)   │    │  of builtins)│    │  effects)    │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                                       │                    │
│         └───────────────────┬───────────────────┘                   │
│                             ▼                                        │
│                    InferenceResult                                   │
│                    (return type + effects)                           │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ T8: Caching                                                          │
│  - Store in CodeInstance                                             │
│  - Register backedges for invalidation                               │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ T4: SSA IR Construction                                              │
│  - inflate_ir! (CodeInfo → IRCode)                                   │
│  - construct_ssa! (slots → SSA)                                      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ T5: Optimization Passes                                              │
│                                                                      │
│  CONVERT → SLOT2REG → COMPACT → INLINING → COMPACT → SROA → ADCE   │
│                          │                    │                      │
│                          │                    ▼                      │
│                          │           ┌──────────────┐               │
│                          └──────────►│ T6: Escape   │               │
│                                      │ Analysis     │               │
│                                      └──────────────┘               │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
                    Optimized IRCode
                              │
                              ▼
                    LLVM Codegen (C)
```

### 3.2 Key Integration Points

| From | To | Integration Point | Data Exchanged |
|------|----|--------------------|----------------|
| T1 → T2 | Type Inference → Lattice | `tmerge`, `tmeet`, `⊑` | Lattice elements |
| T1 → T3 | Type Inference → tfuncs | `builtin_tfunction` | Return types for builtins |
| T1 → T7 | Type Inference → Effects | `merge_effects!` | Effect bits |
| T1 → T8 | Type Inference → Caching | `finish!`, `promotecache!` | CodeInstance |
| T3 → T7 | tfuncs → Effects | `builtin_effects` | Effect classification |
| T4 → T5 | SSA IR → Optimization | `IRCode`, `IncrementalCompact` | IR representation |
| T5 → T6 | Optimization → Escape | `analyze_escapes` | Escape state |
| T6 → T5 | Escape → Optimization | `has_no_escape`, `getaliases` | Escape predicates |
| T7 → T5 | Effects → Optimization | `flags_for_effects` | IR flags |

---

## 4. Cross-Reference Summary by Subsystem

### T1: Type Inference Engine
**Depends on**: T2 (lattice), T3 (tfuncs), T7 (effects), T8 (caching)
**Provides to**: T4 (types), T5 (inference results), T8 (CodeInstance)

### T2: Type Lattice
**Depends on**: Core types
**Provides to**: T1 (lattice operations), T3 (lattice types)
**Note**: Foundational - no compiler dependencies

### T3: Type Functions (tfuncs)
**Depends on**: T2 (lattice types), T7 (effect classifications)
**Provides to**: T1 (return types for builtins)

### T4: SSA IR
**Depends on**: Core IR types
**Provides to**: T5 (IRCode, IncrementalCompact), T6 (IR for analysis)
**Note**: Foundational for optimization

### T5: Optimization Passes
**Depends on**: T1 (inference results), T4 (IR), T6 (escape info), T7 (effects)
**Provides to**: Codegen (optimized IR)

### T6: Escape Analysis
**Depends on**: T4 (IR), T7 (effect flags)
**Provides to**: T5 (escape predicates for SROA, finalizers)

### T7: Effects System
**Depends on**: Core effect definitions
**Provides to**: T1 (effect tracking), T3 (builtin effects), T5 (IR flags)

### T8: Caching & Invalidation
**Depends on**: T1 (inference results), Core runtime
**Provides to**: T1 (cached results), Runtime (compiled code), T16 (CodeInstance)

### T12: Method Dispatch
**Depends on**: Core runtime (gf.c), T1
**Provides to**: T1 (method lookup), T8 (cache keying)
**Key Files**: gf.c, methodtable.jl

### T13: Lowering
**Depends on**: Parser (AST), macroexpand.scm
**Provides to**: T1 (CodeInfo input), T4
**Key Files**: ast.c, julia-syntax.scm, jlfrontend.scm

### T14: Codegen
**Depends on**: T4 (optimized IR), T5
**Provides to**: Native code
**Key Files**: codegen.cpp, cgutils.cpp, intrinsics.cpp, jitlayers.cpp

### T15: Specialization Limits
**Depends on**: T1 (InferenceParams)
**Provides to**: T1 (budgets), T12
**Key Files**: types.jl, typelimits.jl

### T16: Precompilation
**Depends on**: T8 (CodeInstance), T14
**Provides to**: Startup latency reduction
**Key Files**: precompile.jl, precompile.c, loading.jl

---

## 5. Key Functions Crossing Subsystem Boundaries

### T1 ↔ T2 (Inference ↔ Lattice)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `tmerge(𝕃, a, b)` | T1 | T2 | Join types at control flow merge |
| `tmeet(𝕃, a, b)` | T1 | T2 | Intersect types for refinement |
| `⊑(𝕃, a, b)` | T1 | T2 | Check lattice ordering |
| `widenconst(t)` | T1 | T2 | Convert to Julia type |
| `typeinf_lattice(interp)` | T1 | T2 | Get lattice for interpreter |

### T1 ↔ T3 (Inference ↔ tfuncs)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `builtin_tfunction(...)` | T1 | T3 | Get return type of builtin |
| `getfield_tfunc(...)` | T1 | T3 | Type of field access |
| `apply_type_tfunc(...)` | T1 | T3 | Type of type application |

### T1 ↔ T7 (Inference ↔ Effects)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `merge_effects!(...)` | T1 | T7 | Accumulate effects during inference |
| `builtin_effects(...)` | T1 | T7 | Get effects of builtin |
| `is_foldable(effects)` | T1 | T7 | Check if can constant fold |

### T5 ↔ T6 (Optimization ↔ Escape)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `analyze_escapes(ir, ...)` | T5 | T6 | Run escape analysis |
| `has_no_escape(info)` | T5 | T6 | Check if value doesn't escape |
| `getaliases(ssa, estate)` | T5 | T6 | Get aliased values |

### T5 ↔ T7 (Optimization ↔ Effects)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `flags_for_effects(e)` | T5 | T7 | Convert Effects to IR flags |
| `stmt_effect_flags(...)` | T5 | T7 | Compute per-statement effects |

### T1 ↔ T12 (Inference ↔ Method Dispatch)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `find_method_matches(...)` | T1 | T12 | Find matching methods for call signature |
| `findall(...)` | T1 | T12 | Search method table for all matches |

### T1 ↔ T15 (Inference ↔ Specialization Limits)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `get_max_methods(...)` | T1 | T15 | Get maximum methods limit for union splitting |
| `unionsplitcost(...)` | T1 | T15 | Compute cost of union splitting |

### T13 ↔ T1 (Lowering ↔ Inference)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `jl_lower(...)` | T13 | T1 | Lower AST to CodeInfo for inference input |

### T5 ↔ T14 (Optimization ↔ Codegen)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `jl_emit_codeinst(...)` | T5 | T14 | Emit native code from optimized IR |

### T8 ↔ T16 (Caching ↔ Precompilation)

| Function | Source | Target | Purpose |
|----------|--------|--------|---------|
| `enqueue_specializations!(...)` | T8 | T16 | Queue specializations for precompilation |

---

## 6. Architectural Patterns

### 6.1 Lattice-Based Analysis
The type lattice (T2) provides a mathematical framework used throughout:
- **T1** uses lattice for type inference (worklist algorithm)
- **T6** uses a separate escape lattice with similar operations
- **T7** effects form an implicit lattice (join = merge_effects)

### 6.2 Two-Phase Compilation
1. **Analysis Phase**: T1 (inference) + T7 (effects) → InferenceResult
2. **Optimization Phase**: T4 (IR) + T5 (passes) + T6 (escape) → Optimized IR

### 6.3 Incremental Modification
`IncrementalCompact` (T4) enables on-the-fly IR modification used by:
- Inlining (T5)
- SROA (T5)
- DCE (T5)

### 6.4 Caching with Invalidation
T8 provides:
- Cache by (MethodInstance, world_age)
- Backedge tracking for dependencies
- Lazy revalidation on load

---

## 7. File-Level Dependencies

```
                   Core (boot.jl, coreir.jl)
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
    types.jl          typelattice.jl      effects.jl
         │                  │                  │
         └──────────────────┼──────────────────┘
                            │
                            ▼
                    abstractlattice.jl
                            │
                            ▼
                       tfuncs.jl
                            │
                            ▼
    ┌───────────────────────┼───────────────────────┐
    │                       │                       │
    ▼                       ▼                       ▼
inferencestate.jl    inferenceresult.jl      stmtinfo.jl
    │                       │                       │
    └───────────────────────┼───────────────────────┘
                            │
                            ▼
               abstractinterpretation.jl
                            │
                            ▼
                      typeinfer.jl
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
    cicache.jl         ssair/*.jl         optimize.jl
         │                  │                  │
         ▼                  │                  ▼
    reinfer.jl              │            passes.jl
         │                  │                  │
         │                  │                  ▼
         │                  │            inlining.jl
         │                  │                  │
         │                  └──────────────────┘
         │                           │
         ▼                           ▼
bindinginvalidations.jl      EscapeAnalysis.jl
```

---

## 8. Summary Table

| Subsystem | Files | Lines | Key Exports |
|-----------|-------|-------|-------------|
| T1: Type Inference | 5 | ~8,400 | `typeinf`, `abstract_call` |
| T2: Type Lattice | 4 | ~2,400 | `tmerge`, `tmeet`, `⊑`, lattice types |
| T3: tfuncs | 1 | ~3,300 | `builtin_tfunction`, `*_tfunc` |
| T4: SSA IR | 6 | ~5,100 | `IRCode`, `CFG`, `IncrementalCompact` |
| T5: Optimization | 3 | ~6,100 | `optimize`, `ssa_inlining_pass!`, `sroa_pass!` |
| T6: Escape Analysis | 1 | ~1,400 | `analyze_escapes`, `has_no_escape` |
| T7: Effects | 1 | ~370 | `Effects`, `merge_effects`, `is_foldable` |
| T8: Caching | 4 | ~1,100 | `WorldRange`, `InternalCodeCache` |
| T12: Method Dispatch | 2 | ~3,000 | `find_method_matches`, `findall` |
| T13: Lowering | 3 | ~4,500 | `jl_lower`, CodeInfo construction |
| T14: Codegen | 4 | ~15,000 | `jl_emit_codeinst`, LLVM IR generation |
| T15: Specialization Limits | 2 | ~800 | `get_max_methods`, `unionsplitcost` |
| T16: Precompilation | 3 | ~2,500 | `enqueue_specializations!`, cache serialization |

**Total**: ~28,000 lines of Julia code in the Compiler package (T1-T8), plus additional C/C++ code for T12-T14, T16.
