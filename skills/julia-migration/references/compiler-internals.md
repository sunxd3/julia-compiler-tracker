# Julia Compiler Internals Reference

Condensed reference for Julia's compiler pipeline. Snapshot: `Compiler/src/` in JuliaLang/julia, 1.14-DEV.

## Pipeline

```
Source -> Lowering (ast.c, julia-syntax.scm) -> CodeInfo
  -> Type Inference (abstractinterpretation.jl, typeinfer.jl)
  -> Caching (cicache.jl, reinfer.jl) -> CodeInstance
  -> SSA Construction (ssair/slot2ssa.jl, optimize.jl) -> IRCode
  -> Optimization: INLINING -> SROA -> ADCE (ssair/inlining.jl, ssair/passes.jl)
  -> LLVM Codegen (src/codegen.cpp, cgutils.cpp, intrinsics.cpp, jitlayers.cpp)
```

## Key Structs

### InferenceState (inferencestate.jl)
`linfo::MethodInstance`, `ip::BitSet` (worklist), `ssavaluetypes::Vector{Any}`, `bestguess` (return type), `exc_bestguess`, `ipo_effects::Effects`, `edges::Vector{Any}`, `stmt_info::Vector{CallInfo}`, `cycleid::Int`, `tasks::Vector{WorkThunk}`.

### InferenceResult (types.jl)
`linfo`, `argtypes`, `result` (lattice element), `src` (CodeInfo/IRCode/OptimizationState), `ipo_effects::Effects`, `effects::Effects`, `ci::CodeInstance`, `ci_as_edge::CodeInstance`.

### IRCode (ssair/ir.jl)
`stmts::InstructionStream`, `argtypes::Vector{Any}`, `sptypes::Vector{VarState}`, `cfg::CFG`, `new_nodes::NewNodeStream`, `meta::Vector{Expr}`, `valid_worlds::WorldRange`.

### InstructionStream (ir.jl)
Parallel arrays: `stmt::Vector{Any}`, `type::Vector{Any}`, `info::Vector{CallInfo}`, `line::Vector{Int32}`, `flag::Vector{UInt32}`.

### CFG / BasicBlock (ir.jl, basicblock.jl)
`CFG`: `blocks::Vector{BasicBlock}`, `index::Vector{Int}`. `BasicBlock`: `stmts::StmtRange`, `preds::Vector{Int}`, `succs::Vector{Int}`.

### VarState (types.jl)
`typ`, `ssadef::Int` (reaching definition: 0=argument, >0=SSA pc, <0=virtual phi-block), `undef::Bool`.

### Effects (effects.jl)
9 fields: `consistent::UInt8`, `effect_free::UInt8`, `nothrow::Bool`, `terminates::Bool`, `notaskstate::Bool`, `inaccessiblememonly::UInt8`, `noub::UInt8`, `nonoverlayed::UInt8`, `nortcall::Bool`.

Multi-state flags: `ALWAYS_TRUE=0x00`, `ALWAYS_FALSE=0x01`, conditional variants (`CONSISTENT_IF_NOTRETURNED=0x02`, `EFFECT_FREE_IF_INACCESSIBLEMEMONLY=0x02`, etc.).

Key predicates: `is_foldable` (consistent + effect_free + terminates + noub), `is_removable_if_unused` (effect_free + nothrow + terminates).

### CodeInstance (key fields)
`rettype`, `exctype`, `inferred`, `min_world`, `max_world`, `edges` (dependencies), `ipo_purity_bits`.

## Type Lattice

### Lattice Tower (bottom to top)
`JLTypeLattice` -> `ConstsLattice` -> `PartialsLattice` -> `ConditionalsLattice` / `MustAliasesLattice` -> `InferenceLattice`

Standard compositions: `BaseInferenceLattice` (local), `IPOResultLattice` (inter-procedural/caching), `InferenceLattice` (full with LimitedAccuracy). Defined in abstractlattice.jl.

### Extended Lattice Elements

| Type | File | Key Fields |
|------|------|------------|
| `Const` | boot.jl | `val` |
| `PartialStruct` | boot.jl | `typ`, `undefs`, `fields` |
| `Conditional` | typelattice.jl | `slot::Int`, `ssadef::Int`, `thentype`, `elsetype`, `isdefined::Bool` |
| `InterConditional` | boot.jl | `slot::Int`, `thentype`, `elsetype` (no ssadef — for IPO cache) |
| `MustAlias` | typelattice.jl | `slot`, `ssadef`, `vartyp`, `fldidx::Int`, `fldtyp` |
| `InterMustAlias` | typelattice.jl | `slot`, `vartyp`, `fldidx`, `fldtyp` (no ssadef) |
| `PartialOpaque` | boot.jl | `typ`, `env`, `parent`, `source` |
| `PartialTypeVar` | typelattice.jl | `tv::TypeVar`, `lb_certain::Bool`, `ub_certain::Bool` |
| `LimitedAccuracy` | typelattice.jl | `typ`, `causes::IdSet{InferenceState}` |

### Core Operations
- `tmerge(L, a, b)` — join at merge. Not associative; applies widening. (typelimits.jl)
- `tmeet(L, a, b)` — greatest lower bound. (abstractlattice.jl)
- `widenconst(t)` — strip extended lattice to native Julia types. (typelattice.jl)

### Widening Limits
`MAX_TYPEUNION_COMPLEXITY = 3`, `MAX_TYPEUNION_LENGTH = 3`. `tuplemerge` collapses different-length tuples to `Vararg`.

## Type Functions (tfuncs.jl)

Registration: `add_tfunc(f, minarg, maxarg, tfunc, cost)`. Two tables: `T_IFUNC` (intrinsics by ID), `T_FFUNC_*` (builtins, parallel arrays).

Effects: `builtin_effects` (tfuncs.jl), `intrinsic_effects`. Classification lists: `_PURE_BUILTINS`, `_CONSISTENT_BUILTINS`, `_EFFECT_FREE_BUILTINS`.

## CallInfo Hierarchy (stmtinfo.jl)

`NoCallInfo`, `MethodMatchInfo`, `UnionSplitInfo`, `InvokeCallInfo`, `ApplyCallInfo`, `OpaqueClosureCallInfo`, `GlobalAccessInfo`, `ModifyOpInfo`, etc.

## SSA IR Details

**Statement types**: `Expr(:call,...)`, `Expr(:invoke, mi, f, args...)`, `Expr(:new,...)`, `GotoNode`, `GotoIfNot`, `ReturnNode`, `PhiNode`, `PiNode`, `UpsilonNode`, `PhiCNode`.

**IR Flags** (optimize.jl): `IR_FLAG_INBOUNDS(1<<0)`, `IR_FLAG_INLINE(1<<1)`, `IR_FLAG_NOINLINE(1<<2)`, `IR_FLAG_CONSISTENT(1<<3)`, `IR_FLAG_EFFECT_FREE(1<<4)`, `IR_FLAG_NOTHROW(1<<5)`, `IR_FLAG_TERMINATES(1<<6)`, `IR_FLAG_NOUB(1<<10)`, `IR_FLAG_NORTCALL(1<<13)`, `IR_FLAG_REFINED(1<<16)`, `IR_FLAG_UNUSED(1<<17)`.

**IncrementalCompact** (ir.jl): Mutable iterator for on-the-fly IR modification with SSA renumbering and use-counting for DCE.

## Optimization Passes

Pipeline (`run_passes_ipo_safe`, optimize.jl):
```
CONVERT -> SLOT2REG -> COMPACT_1 -> INLINING -> COMPACT_2 -> SROA -> ADCE -> [COMPACT_3 if changed]
```

**Inlining** (ssair/inlining.jl): `assemble_inline_todo!` (analysis) then `batch_inline!` (execution). Cost threshold: 100. Union splitting via `UnionSplit`.

**SROA** (ssair/passes.jl): `collect_leaves` -> `lift_leaves` -> `perform_lifting!`. Mutable structs via `sroa_mutables!` using escape analysis + iterated dominance frontier.

**ADCE** (ssair/passes.jl): Removes unused statements with `IR_FLAGS_REMOVABLE`.

## Escape Analysis (ssair/EscapeAnalysis.jl)

Backward dataflow, fixed-point. `EscapeInfo`: `Analyzed`, `ReturnEscape`, `ThrownEscape::BitSet`, `AliasInfo`, `Liveness::BitSet`. Field-sensitive alias tracking via union-find. Consumers: SROA, finalizer inlining, effect refinement.

## Caching & Invalidation

Hierarchy: `Method` -> `MethodInstance` -> `CodeInstance` (linked list per world range).

World age: monotonic counter, increments on method/type definition. Backedges: method instance, binding, method table. Invalidation cascades through backedges.

Precompile revalidation: `insert_backedges` (reinfer.jl) uses Tarjan's SCC. `verify_call` checks dispatch edges.

## Codegen (src/)

Entry: `jl_emit_codeinst` (codegen.cpp) -> `emit_function`. GC address spaces: Tracked, Derived, Loaded. Julia LLVM passes: `llvm-late-gc-lowering`, `llvm-final-gc-lowering`, `llvm-alloc-opt`, `llvm-julia-licm`, `llvm-multiversioning`.

## InferenceParams Defaults (types.jl)

`max_methods` (from BuildSettings), `max_union_splitting=4`, `max_apply_union_enum=8`, `max_tuple_splat=32`, `tuple_complexity_limit_depth=3`.

## Version-Sensitive Surfaces (Migration Hazards)

| Area | What changes between versions |
|------|-------------------------------|
| `InferenceState` fields | Fields added/removed/renamed |
| `InferenceResult` fields | `ci`/`ci_as_edge` are relatively new |
| `Effects` struct / bit values | New effects added; conditional flag values change |
| `CallInfo` subtypes | New subtypes added per version |
| IR flags | New flags, bit positions shift |
| `IRCode` / `InstructionStream` fields | `debuginfo` format changed; `new_nodes` type evolved |
| `CodeInstance` fields | `edges` encoding changed; `inferred` type changed |
| Optimization pass names/order | Passes renamed, reordered, or added |
| Lowering output | `getproperty` vs `getfield`, kwarg lowering |
| `PartialStruct` fields | `undefs` field added for definedness tracking |
| Lattice layer composition types | Layer names/nesting changes |
| Precompile revalidation | `reinfer.jl` rewrite with Tarjan SCC is recent |
