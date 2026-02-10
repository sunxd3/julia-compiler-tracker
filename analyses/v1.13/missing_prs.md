# Missing v1.13 Compiler PR Analyses

PRs identified as missing from the v1.13 analysis coverage.
Branch point: **2025-10-28** (commit `abd8457ca85370eefe3788cfa13a6233773ea16f`)
1.12 branch point: **2025-02-04** (commit `0c1e800dbdcf76b24cf3ab2bc9861a587e7c1fb5`)

**Coverage:** 67 of 269+ compiler-related PRs have YAML analyses (~25%).
258 PRs below were identified by file-path filtering and confirmed missing.

**Note:** The file-path filter (matching `Compiler/`, `src/codegen*`, `src/gc*`, etc.) may not catch every compiler-adjacent PR. 56 of the 67 existing analyses cover PRs not detected by the filter, suggesting additional missing PRs may exist beyond this list.

## Inference

| PR | Title |
|---|---|
| [#57222](https://github.com/JuliaLang/julia/pull/57222) | Inference: propagate struct initialization info on `setfield!` |
| [#57275](https://github.com/JuliaLang/julia/pull/57275) | Compiler: fix unsoundness of getfield_tfunc on Tuple Types |
| [#57293](https://github.com/JuliaLang/julia/pull/57293) | Fix getfield_tfunc when order or boundscheck is Vararg |
| [#57304](https://github.com/JuliaLang/julia/pull/57304) | Extend `PartialStruct` to represent non-contiguously defined fields |
| [#57541](https://github.com/JuliaLang/julia/pull/57541) | inference: allow `PartialStruct` to represent strict undef field |
| [#57545](https://github.com/JuliaLang/julia/pull/57545) | [Compiler] fix some cycle_fix_limited usage |
| [#57553](https://github.com/JuliaLang/julia/pull/57553) | Compiler: avoid type instability in access to `PartialStruct` field |
| [#57582](https://github.com/JuliaLang/julia/pull/57582) | Compiler: abstract calls: type assert to help stability |
| [#57653](https://github.com/JuliaLang/julia/pull/57653) | typeinfer: Add `force_enable_inference` to override Module-level inference settings |
| [#57684](https://github.com/JuliaLang/julia/pull/57684) | Compiler: `abstract_apply`: declare type of two closure captures |
| [#57720](https://github.com/JuliaLang/julia/pull/57720) | inference: avoid creating `PartialStruct` that never exists at runtime |
| [#57743](https://github.com/JuliaLang/julia/pull/57743) | inference: exclude uncached frames from callstack |
| [#57806](https://github.com/JuliaLang/julia/pull/57806) | effects: fix effects of atomic pointer operations |
| [#57849](https://github.com/JuliaLang/julia/pull/57849) | Fix `fargs` handling for `form_partially_defined_struct` |
| [#57856](https://github.com/JuliaLang/julia/pull/57856) | effects: give the most conservative effects to unhandled builtins |
| [#57860](https://github.com/JuliaLang/julia/pull/57860) | `Compiler`: `abstract_eval_invoke_inst`: type assert `Expr` |
| [#57896](https://github.com/JuliaLang/julia/pull/57896) | inference: fix exct modeling of `setglobal!` |
| [#57897](https://github.com/JuliaLang/julia/pull/57897) | overload lattice ops within `abstract_eval_isdefinedglobal` |
| [#57973](https://github.com/JuliaLang/julia/pull/57973) | inference: model `Core._svec_ref` |
| [#58026](https://github.com/JuliaLang/julia/pull/58026) | inference: simplify `abstract_eval_globalref` |
| [#58027](https://github.com/JuliaLang/julia/pull/58027) | inference: re-enable inference overload for basic statements |
| [#58154](https://github.com/JuliaLang/julia/pull/58154) | inference: minor refactoring on abstractinterpretation.jl |
| [#58165](https://github.com/JuliaLang/julia/pull/58165) | inference: allow specialization of `scan_specified_partitions` |
| [#58184](https://github.com/JuliaLang/julia/pull/58184) | fix performance regression introduced by #58027 |
| [#58220](https://github.com/JuliaLang/julia/pull/58220) | improve isdefined precision for 0 field types |
| [#58249](https://github.com/JuliaLang/julia/pull/58249) | inference: prevent nested slot wrappers in abstract_call_builtin |
| [#58273](https://github.com/JuliaLang/julia/pull/58273) | Prevent type infer hang of "simple" recursive functions |
| [#58325](https://github.com/JuliaLang/julia/pull/58325) | improve robustness of `Vararg` checks in newly added `abstract_eval_xxx` |
| [#58371](https://github.com/JuliaLang/julia/pull/58371) | Allow constant propagation of mutables with const fields |
| [#58582](https://github.com/JuliaLang/julia/pull/58582) | fix `@invokelatest` performance regression |
| [#58743](https://github.com/JuliaLang/julia/pull/58743) | inference: improve `isdefined_tfunc` accuracy for `MustAlias` |
| [#58872](https://github.com/JuliaLang/julia/pull/58872) | model ccall binding access in inference |
| [#59105](https://github.com/JuliaLang/julia/pull/59105) | inference: Make test independent of the `Complex` method table |
| [#59182](https://github.com/JuliaLang/julia/pull/59182) | inference: avoid `LimitedAccuracy` within slot wrappers |
| [#59187](https://github.com/JuliaLang/julia/pull/59187) | inference: propagate more `LimitedAccuracy` information |
| [#59320](https://github.com/JuliaLang/julia/pull/59320) | Make `haskey(::@Kwargs{item::Bool}, :item)` constant-fold |
| [#59525](https://github.com/JuliaLang/julia/pull/59525) | fix potential null deref in `merge_vararg_unions` |
| [#59706](https://github.com/JuliaLang/julia/pull/59706) | effects: improve nothrow modeling for `Core._svec_len` |
| [#59720](https://github.com/JuliaLang/julia/pull/59720) | Compiler: fix inferred nothrow effects for add_ptr and sub_ptr |
| [#59722](https://github.com/JuliaLang/julia/pull/59722) | do not specialize for `abstract_eval_nonlinearized_foreigncall_name` |

## Optimizer

| PR | Title |
|---|---|
| [#57208](https://github.com/JuliaLang/julia/pull/57208) | Teach alloc-opt to handle atomics a bit better |
| [#57633](https://github.com/JuliaLang/julia/pull/57633) | Compiler/ssair/passes: `_lift_svec_ref`: improve type stability |
| [#57859](https://github.com/JuliaLang/julia/pull/57859) | `Compiler`: `walk_to_defs`, `collect_leaves`: specialize for `predecessors` |
| [#57979](https://github.com/JuliaLang/julia/pull/57979) | Move inlinability determination into cache transform |
| [#58033](https://github.com/JuliaLang/julia/pull/58033) | verify that `optimize_until` is a valid pass |
| [#58035](https://github.com/JuliaLang/julia/pull/58035) | optimizer: fix various `optimize_until` misuses |
| [#58070](https://github.com/JuliaLang/julia/pull/58070) | fix called-argument analysis for calls with splat |
| [#58182](https://github.com/JuliaLang/julia/pull/58182) | Revert #57979 (and following #58083 #58082) |
| [#58203](https://github.com/JuliaLang/julia/pull/58203) | Reland #57979 (and following #58083 #58082) |
| [#58328](https://github.com/JuliaLang/julia/pull/58328) | Use getsplit interface for InvokeCallInfo |
| [#58662](https://github.com/JuliaLang/julia/pull/58662) | add support for storing just the inferred inlining_cost in CodeInstance |
| [#58683](https://github.com/JuliaLang/julia/pull/58683) | Add 0 predecessor to entry basic block and handle it in inlining |
| [#59018](https://github.com/JuliaLang/julia/pull/59018) | Don't inline generated functions if we can't invoke their generator |
| [#59601](https://github.com/JuliaLang/julia/pull/59601) | optimizations: improve `Core._apply_iterate` call conversion in #59548 |

## Lowering

| PR | Title |
|---|---|
| [#57299](https://github.com/JuliaLang/julia/pull/57299) | Add missing latestworld after parameterized type alias |
| [#57346](https://github.com/JuliaLang/julia/pull/57346) | lowering: Only try to define the method once |
| [#57416](https://github.com/JuliaLang/julia/pull/57416) | lowering: Don't mutate lambda in `linearize` |
| [#57480](https://github.com/JuliaLang/julia/pull/57480) | lowering: Handle malformed `...` expressions |
| [#57554](https://github.com/JuliaLang/julia/pull/57554) | lowering: Allow chaining of `>:` in `where` |
| [#57562](https://github.com/JuliaLang/julia/pull/57562) | Make no-body `function` declaration implicitly `global` |
| [#57626](https://github.com/JuliaLang/julia/pull/57626) | Disallow non-lhs all-underscore variable names |
| [#57648](https://github.com/JuliaLang/julia/pull/57648) | lowering: Fix captured vars shadowed by an inner global declaration |
| [#57774](https://github.com/JuliaLang/julia/pull/57774) | lowering: Don't closure-convert in `import` or `using` |
| [#57928](https://github.com/JuliaLang/julia/pull/57928) | fix opaque_closure sparam capture |
| [#58076](https://github.com/JuliaLang/julia/pull/58076) | Align `:method` Expr return value between interpreter and codegen |
| [#58187](https://github.com/JuliaLang/julia/pull/58187) | Lower `const x = ...` to new builtin `Core.setconst!` |
| [#58279](https://github.com/JuliaLang/julia/pull/58279) | Remove :globaldecl and :global lowered forms; add Core.declare_global |
| [#58307](https://github.com/JuliaLang/julia/pull/58307) | Fix lowering failure with type parameter in opaque closure |
| [#58426](https://github.com/JuliaLang/julia/pull/58426) | Don't create a type parameter in the closure for captured @nospecialize arguments |
| [#58611](https://github.com/JuliaLang/julia/pull/58611) | Fix `linearize` of global with complex type |
| [#58803](https://github.com/JuliaLang/julia/pull/58803) | Allow underscore (unused) args in presence of kwargs |
| [#58940](https://github.com/JuliaLang/julia/pull/58940) | add `@__FUNCTION__` and `Expr(:thisfunction)` as generic function self-reference |
| [#58964](https://github.com/JuliaLang/julia/pull/58964) | remove comment from julia-syntax that is no longer true |
| [#59155](https://github.com/JuliaLang/julia/pull/59155) | Fix desugaring of `const x::T = y` for complex `y` |
| [#59205](https://github.com/JuliaLang/julia/pull/59205) | fix identification of argument occurrences in optional arg defaults |
| [#59276](https://github.com/JuliaLang/julia/pull/59276) | add `macroexpand!` function and add `legacyscope` kwarg |
| [#59703](https://github.com/JuliaLang/julia/pull/59703) | lowering: increment world age after toplevel expressions |

## Codegen/LLVM

| PR | Title |
|---|---|
| [#55864](https://github.com/JuliaLang/julia/pull/55864) | Fix late gc lowering pass for vector intrinsics |
| [#56130](https://github.com/JuliaLang/julia/pull/56130) | Bump LLVM to v19.1.7+1 |
| [#56890](https://github.com/JuliaLang/julia/pull/56890) | Enable getting non-boxed LLVM type from Julia Type |
| [#57209](https://github.com/JuliaLang/julia/pull/57209) | Always add the frame-pointer=all attribute |
| [#57226](https://github.com/JuliaLang/julia/pull/57226) | cfunction: reimplement, as originally planned, for reliable performance |
| [#57272](https://github.com/JuliaLang/julia/pull/57272) | Support adding `CodeInstance`s to JIT for interpreters defining a codegen cache |
| [#57308](https://github.com/JuliaLang/julia/pull/57308) | Emit enter handler during codegen instead of after optimization |
| [#57352](https://github.com/JuliaLang/julia/pull/57352) | Initial support for LLVM 20 |
| [#57380](https://github.com/JuliaLang/julia/pull/57380) | Make late_gc_lowering more robust |
| [#57386](https://github.com/JuliaLang/julia/pull/57386) | Only strip invariant.load from special pointers |
| [#57392](https://github.com/JuliaLang/julia/pull/57392) | [LateLowerGCFrame] fix PlaceGCFrameReset for returns_twice |
| [#57398](https://github.com/JuliaLang/julia/pull/57398) | Make remaining float intrinsics require float arguments |
| [#57410](https://github.com/JuliaLang/julia/pull/57410) | codegen: cleanup gcstack call frames somewhat earlier |
| [#57432](https://github.com/JuliaLang/julia/pull/57432) | test: Compiler: relax flaky codegen test |
| [#57453](https://github.com/JuliaLang/julia/pull/57453) | Revert "Make emitted egal code more loopy (#54121)" |
| [#57741](https://github.com/JuliaLang/julia/pull/57741) | [LateLowerGC] Fix typo sret handling so we properly handle selects in the worklist |
| [#57793](https://github.com/JuliaLang/julia/pull/57793) | Adapt some more code for LLVM 20 |
| [#57845](https://github.com/JuliaLang/julia/pull/57845) | codegen: fix alignment of source in typed_load from a unsafe_load |
| [#57889](https://github.com/JuliaLang/julia/pull/57889) | Fix typo in codegen for `isdefinedglobal` |
| [#58142](https://github.com/JuliaLang/julia/pull/58142) | Bump LLVM to v20 |
| [#58238](https://github.com/JuliaLang/julia/pull/58238) | Rename `_aligned_msize` to prevent conflict with mingw64 definition |
| [#58322](https://github.com/JuliaLang/julia/pull/58322) | Fix removal of globals with addrspaces in removeAddrspaces |
| [#58344](https://github.com/JuliaLang/julia/pull/58344) | [deps] enable zstd support |
| [#58356](https://github.com/JuliaLang/julia/pull/58356) | codegen: remove readonly from abstract type calling convention |
| [#58365](https://github.com/JuliaLang/julia/pull/58365) | Apply debug_compile_units hack also in remove-addrspaces |
| [#58423](https://github.com/JuliaLang/julia/pull/58423) | Expose native_code's jl_sysimg_gvars |
| [#58429](https://github.com/JuliaLang/julia/pull/58429) | codegen: Unify printing of and add some more internal IR validity errors |
| [#58437](https://github.com/JuliaLang/julia/pull/58437) | [Compiler] Add more tests for non-power-of-two primitive types |
| [#58483](https://github.com/JuliaLang/julia/pull/58483) | Fix tbaa usage when storing into heap allocated immutable structs |
| [#58631](https://github.com/JuliaLang/julia/pull/58631) | codegen: More robustness for invalid :invoke IR |
| [#58637](https://github.com/JuliaLang/julia/pull/58637) | Make late gc lower handle insertelement of alloca use |
| [#58684](https://github.com/JuliaLang/julia/pull/58684) | cfunction: store `fptr` / `world` contiguously |
| [#58697](https://github.com/JuliaLang/julia/pull/58697) | [NFC] codegen: introduce `jl_abi_t` type for ABI adapter API |
| [#58768](https://github.com/JuliaLang/julia/pull/58768) | expand memoryrefnew capabilities |
| [#58792](https://github.com/JuliaLang/julia/pull/58792) | codegen: gc wb for atomic FCA stores |
| [#58794](https://github.com/JuliaLang/julia/pull/58794) | codegen: slightly optimize gc-frame allocation |
| [#58804](https://github.com/JuliaLang/julia/pull/58804) | codegen: ensure safepoint functions can read the pgcstack |
| [#58812](https://github.com/JuliaLang/julia/pull/58812) | Add `cfunction` support for `--trim` |
| [#58828](https://github.com/JuliaLang/julia/pull/58828) | codegen: relaxed jl_tls_states_t.safepoint load |
| [#58950](https://github.com/JuliaLang/julia/pull/58950) | Fix LLVM TaskDispatcher implementation issues |
| [#59003](https://github.com/JuliaLang/julia/pull/59003) | Roll up msys2/clang/windows build fixes |
| [#59059](https://github.com/JuliaLang/julia/pull/59059) | Use a dedicated parameter attribute to identify the gstack arg |
| [#59225](https://github.com/JuliaLang/julia/pull/59225) | [LLVM] Bump LLVM to 20.1.8 |
| [#59266](https://github.com/JuliaLang/julia/pull/59266) | Avoid depending on Julia-patched libunwind ABI |
| [#59492](https://github.com/JuliaLang/julia/pull/59492) | Revert "Enable getting non-boxed LLVM type from Julia Type" |
| [#59559](https://github.com/JuliaLang/julia/pull/59559) | codegen: mark write barrier field load as volatile |
| [#59634](https://github.com/JuliaLang/julia/pull/59634) | Fix several Windows build warnings |
| [#59636](https://github.com/JuliaLang/julia/pull/59636) | Fix compiler warning / use of non-standard C |
| [#59638](https://github.com/JuliaLang/julia/pull/59638) | Fix clang 21 warnings |
| [#59649](https://github.com/JuliaLang/julia/pull/59649) | Work around debug_compile_units skipping nodebug CUs |
| [#59972](https://github.com/JuliaLang/julia/pull/59972) | Get rid of all PointerType::get call with element type |

## GC/Runtime

| PR | Title |
|---|---|
| [#49933](https://github.com/JuliaLang/julia/pull/49933) | Allow for :foreigncall to transition to GC safe automatically |
| [#56334](https://github.com/JuliaLang/julia/pull/56334) | Add hook to initialize Julia on-the-fly during thread adoption |
| [#57237](https://github.com/JuliaLang/julia/pull/57237) | Refactoring code that is specific to stock GC write barriers |
| [#57252](https://github.com/JuliaLang/julia/pull/57252) | Refactoring write barrier for copying generic memory |
| [#57310](https://github.com/JuliaLang/julia/pull/57310) | Make ptls allocations at least 128 byte aligned |
| [#57454](https://github.com/JuliaLang/julia/pull/57454) | If the user explicitly asked for 1 thread don't add an interactive one |
| [#57523](https://github.com/JuliaLang/julia/pull/57523) | Remove usages of weak symbols |
| [#57561](https://github.com/JuliaLang/julia/pull/57561) | Remove `jl_init__threading` and `jl_init_with_image__threading` |
| [#57761](https://github.com/JuliaLang/julia/pull/57761) | Use faster PRNG in the allocations profiler |
| [#57907](https://github.com/JuliaLang/julia/pull/57907) | only update fragmentation data for pages that are not lazily freed |
| [#57934](https://github.com/JuliaLang/julia/pull/57934) | Be more careful about iterator invalidation during recursive invalidation |
| [#57961](https://github.com/JuliaLang/julia/pull/57961) | Add set to temporary roots to avoid O(N) check |
| [#58452](https://github.com/JuliaLang/julia/pull/58452) | avoid deadlock if crashing inside profile_wr_lock |
| [#58487](https://github.com/JuliaLang/julia/pull/58487) | Introduce a few GC controls to limit the heap size when running benchmarks |
| [#58590](https://github.com/JuliaLang/julia/pull/58590) | make _jl_gc_collect jl_notsafepoint |
| [#58599](https://github.com/JuliaLang/julia/pull/58599) | Revert "Introduce a few GC controls to limit the heap size" |
| [#58600](https://github.com/JuliaLang/julia/pull/58600) | reland: hard heap limit flag |
| [#58659](https://github.com/JuliaLang/julia/pull/58659) | Make pool allocator stats from gc_page_fragmentation_stats more visible |
| [#58713](https://github.com/JuliaLang/julia/pull/58713) | GC Always Full Flag |
| [#58939](https://github.com/JuliaLang/julia/pull/58939) | Use relaxed atomics to load/update jl_lineno and jl_filename |
| [#58997](https://github.com/JuliaLang/julia/pull/58997) | add array element mutex offset in print and gc |
| [#59034](https://github.com/JuliaLang/julia/pull/59034) | Add ThreadSanitizer hooks for jl_mutex_t |
| [#59362](https://github.com/JuliaLang/julia/pull/59362) | init: pre-allocate shared runtime types |
| [#59400](https://github.com/JuliaLang/julia/pull/59400) | begin to encapsulate global state variables |
| [#59408](https://github.com/JuliaLang/julia/pull/59408) | fix a couple static variable data-races |
| [#59482](https://github.com/JuliaLang/julia/pull/59482) | convert more recursive algorithms from stack to heap space (iterative) |
| [#59517](https://github.com/JuliaLang/julia/pull/59517) | Add lock around coverage operations |
| [#59644](https://github.com/JuliaLang/julia/pull/59644) | Add `fprint` variants of `jl_gc_debug_*` for MMTK |

## Binding Partitions

| PR | Title |
|---|---|
| [#57253](https://github.com/JuliaLang/julia/pull/57253) | bpart: Fully switch to partitioned semantics |
| [#57302](https://github.com/JuliaLang/julia/pull/57302) | Add explicit imports for types and fix bugs |
| [#57311](https://github.com/JuliaLang/julia/pull/57311) | Add a warning for auto-import of types |
| [#57357](https://github.com/JuliaLang/julia/pull/57357) | Only implicitly `using` Base, not Core |
| [#57385](https://github.com/JuliaLang/julia/pull/57385) | bpart: Move kind enum into its intended place |
| [#57405](https://github.com/JuliaLang/julia/pull/57405) | bpart: Also partition the export flag |
| [#57433](https://github.com/JuliaLang/julia/pull/57433) | bpart: Track whether any binding replacement has happened in image modules |
| [#57449](https://github.com/JuliaLang/julia/pull/57449) | bpart: Also partition ->deprecated |
| [#57602](https://github.com/JuliaLang/julia/pull/57602) | bpart: Allow inference/codegen to merge multiple partitions |
| [#57614](https://github.com/JuliaLang/julia/pull/57614) | bpart: Rename partition flags, turn binding flags atomic |
| [#57755](https://github.com/JuliaLang/julia/pull/57755) | bpart: Redesign representation of implicit imports |
| [#57965](https://github.com/JuliaLang/julia/pull/57965) | Add builtin functions Core._import, Core._using; implement import/using logic in Julia |
| [#57995](https://github.com/JuliaLang/julia/pull/57995) | Merge adjacent implicit binding partitions |
| [#58261](https://github.com/JuliaLang/julia/pull/58261) | fix isconst definition/accessor issues with binding partitions |
| [#58271](https://github.com/JuliaLang/julia/pull/58271) | bpart: Fix a hang in a particular corner case |
| [#58540](https://github.com/JuliaLang/julia/pull/58540) | fix breakage with `jl_get_global` |
| [#58809](https://github.com/JuliaLang/julia/pull/58809) | use more canonical way to check binding existence |
| [#58830](https://github.com/JuliaLang/julia/pull/58830) | bpart: Properly track methods with invalidated source after require_world |
| [#59368](https://github.com/JuliaLang/julia/pull/59368) | bpart: Fix reresolution logic on export value changes |

## Compilation Infrastructure

| PR | Title |
|---|---|
| [#56987](https://github.com/JuliaLang/julia/pull/56987) | staticdata: remove `reinit_ccallable` |
| [#57074](https://github.com/JuliaLang/julia/pull/57074) | [internals] add time metrics for every CodeInstance |
| [#57193](https://github.com/JuliaLang/julia/pull/57193) | CompilerDevTools: add proof of concept for caching runtime calls |
| [#57248](https://github.com/JuliaLang/julia/pull/57248) | improve concurrency safety for `Compiler.finish!` |
| [#57342](https://github.com/JuliaLang/julia/pull/57342) | trimming: make sure to fail / warn on `Expr(:call, ...)` |
| [#57375](https://github.com/JuliaLang/julia/pull/57375) | Sink CodeInfo transformation into `transform_result_for_cache`, continued |
| [#57520](https://github.com/JuliaLang/julia/pull/57520) | move to a simpler versioning policy for the Compiler.jl stdlib |
| [#57530](https://github.com/JuliaLang/julia/pull/57530) | [Compiler] begin new approach to verify --trim output |
| [#57542](https://github.com/JuliaLang/julia/pull/57542) | staticdata: Refactor sysimage loading |
| [#57640](https://github.com/JuliaLang/julia/pull/57640) | CompilerDevTools: use `transform_result_for_cache` instead of `optimize` |
| [#57650](https://github.com/JuliaLang/julia/pull/57650) | Compiler: Fix pre-compilation as separate package |
| [#57657](https://github.com/JuliaLang/julia/pull/57657) | trimming: improve output on failure |
| [#57987](https://github.com/JuliaLang/julia/pull/57987) | Run Compiler tests in parallel for `Pkg.test`, continued |
| [#57988](https://github.com/JuliaLang/julia/pull/57988) | much faster code-coverage for packages |
| [#58069](https://github.com/JuliaLang/julia/pull/58069) | [CompilerDevTools] Use `with_new_compiler` directly |
| [#58074](https://github.com/JuliaLang/julia/pull/58074) | [CompilerDevTools] Properly handle builtins in with_new_compiler |
| [#58082](https://github.com/JuliaLang/julia/pull/58082) | Drop sources for constabi results in local cache |
| [#58083](https://github.com/JuliaLang/julia/pull/58083) | Always set `result.src` to the result of transform_result_for_cache |
| [#58106](https://github.com/JuliaLang/julia/pull/58106) | gf.c: Fix backedge de-duplication bug |
| [#58131](https://github.com/JuliaLang/julia/pull/58131) | make just one MethodTable |
| [#58141](https://github.com/JuliaLang/julia/pull/58141) | Make trimmed binaries initialize on first call |
| [#58150](https://github.com/JuliaLang/julia/pull/58150) | Revert "remove some more serialized junk from the sysimg" |
| [#58166](https://github.com/JuliaLang/julia/pull/58166) | staticdata: fix many mistakes in staticdata stripping |
| [#58167](https://github.com/JuliaLang/julia/pull/58167) | gf: make dispatch heuristic representation explicit |
| [#58213](https://github.com/JuliaLang/julia/pull/58213) | transition @zone in Core.Compiler to directly use jl_timing |
| [#58291](https://github.com/JuliaLang/julia/pull/58291) | replace incorrect Method.deleted_world with more useful Method.dispatch_status enum |
| [#58343](https://github.com/JuliaLang/julia/pull/58343) | Defer global caching of `CodeInstance` to post-optimization step |
| [#58390](https://github.com/JuliaLang/julia/pull/58390) | Fix signedness typo in world range update |
| [#58394](https://github.com/JuliaLang/julia/pull/58394) | Use `get_ci_mi` in `store_backedges` |
| [#58420](https://github.com/JuliaLang/julia/pull/58420) | change the Compiler.jl stdlib version to 0.1.0 |
| [#58510](https://github.com/JuliaLang/julia/pull/58510) | Don't filter `Core` methods from newly-inferred list |
| [#58636](https://github.com/JuliaLang/julia/pull/58636) | better handling of missing backedges |
| [#58661](https://github.com/JuliaLang/julia/pull/58661) | refine IR model queries |
| [#58744](https://github.com/JuliaLang/julia/pull/58744) | bump Compiler.jl version to 0.1.1 |
| [#58817](https://github.com/JuliaLang/julia/pull/58817) | Add `trim_mode` parameter to JIT type-inference entrypoint |
| [#58825](https://github.com/JuliaLang/julia/pull/58825) | add METHOD_SIG_LATEST_ONLY optimization to MethodInstance too |
| [#58860](https://github.com/JuliaLang/julia/pull/58860) | Re-add old function name for backward compatibility in init |
| [#58948](https://github.com/JuliaLang/julia/pull/58948) | stored method interference graph |
| [#59234](https://github.com/JuliaLang/julia/pull/59234) | Drop sysimage caches for --code-coverage=all |
| [#59238](https://github.com/JuliaLang/julia/pull/59238) | compiler: consolidate staticdata.jl and invalidations.jl into Compiler proper [NFCI] |
| [#59342](https://github.com/JuliaLang/julia/pull/59342) | coverage: handle cases where `di.def` is `nothing` |
| [#59361](https://github.com/JuliaLang/julia/pull/59361) | precompile: move precompile_utils logic from C to julia |
| [#59520](https://github.com/JuliaLang/julia/pull/59520) | Use invokelatest for exiting because exit doesn't exist in the compiler |
| [#59631](https://github.com/JuliaLang/julia/pull/59631) | Set world bounds on `CodeInfo` created for `OpaqueClosure(::IRCode)` |
| [#59672](https://github.com/JuliaLang/julia/pull/59672) | [Compiler] fix stdout/stderr to point to Core |

## IR/Verification

| PR | Title |
|---|---|
| [#57420](https://github.com/JuliaLang/julia/pull/57420) | Compiler: Fix check for IRShow definedness |
| [#58327](https://github.com/JuliaLang/julia/pull/58327) | use `src.nargs` for `validate_code!` |
| [#58425](https://github.com/JuliaLang/julia/pull/58425) | Fix MethodError in IR validator |
| [#58443](https://github.com/JuliaLang/julia/pull/58443) | ir/verify: Give more correct errors in two places |
| [#58467](https://github.com/JuliaLang/julia/pull/58467) | ir: Consider Argument a useref |
| [#58477](https://github.com/JuliaLang/julia/pull/58477) | ir: Don't fail if :invoke has zero arguments |
| [#58642](https://github.com/JuliaLang/julia/pull/58642) | Support `debuginfo` context option in IRShow for `IRCode`/`IncrementalCompact` |
| [#58893](https://github.com/JuliaLang/julia/pull/58893) | IRShow: Print arg0 type when necessary to disambiguate `invoke` |
| [#59455](https://github.com/JuliaLang/julia/pull/59455) | `Compiler.IRShow`: prevent a closure capture boxing with the usual workaround |
| [#59671](https://github.com/JuliaLang/julia/pull/59671) | Minor fixes for IRInterp in presence of ABI overrides |

## Other

| PR | Title |
|---|---|
| [#49675](https://github.com/JuliaLang/julia/pull/49675) | transition `@timeit` in `Core.Compiler` to use tracy instead |
| [#54835](https://github.com/JuliaLang/julia/pull/54835) | NFC: Add `fprint` variants of internal print functions |
| [#57012](https://github.com/JuliaLang/julia/pull/57012) | Replace -> with :: where appropriate in docstrings |
| [#57214](https://github.com/JuliaLang/julia/pull/57214) | Refactoring code in `mk_symbol` to remove stock specific code |
| [#57532](https://github.com/JuliaLang/julia/pull/57532) | cleanup old builtins |
| [#57551](https://github.com/JuliaLang/julia/pull/57551) | Fix uninitialized variable warning |
| [#57588](https://github.com/JuliaLang/julia/pull/57588) | use `@main` for juliac executable entry point |
| [#57681](https://github.com/JuliaLang/julia/pull/57681) | Fix unused variable warnings |
| [#57757](https://github.com/JuliaLang/julia/pull/57757) | Fix documentation of `jl_gc_collect` |
| [#57822](https://github.com/JuliaLang/julia/pull/57822) | Mark UInt8 field as UInt8 in CodeInstance |
| [#57837](https://github.com/JuliaLang/julia/pull/57837) | restore method count after redefinition to hide old definition |
| [#58118](https://github.com/JuliaLang/julia/pull/58118) | Fix some typos in comments and tests |
| [#58205](https://github.com/JuliaLang/julia/pull/58205) | reduce places where Builtins are listed |
| [#58254](https://github.com/JuliaLang/julia/pull/58254) | Strengthen language around `@assume_effects` :consistent |
| [#58289](https://github.com/JuliaLang/julia/pull/58289) | Revert code changes from "strengthen assume_effects doc" PR |
| [#58349](https://github.com/JuliaLang/julia/pull/58349) | InteractiveUtils: Fully support broadcasting expressions for code introspection macros |
| [#58411](https://github.com/JuliaLang/julia/pull/58411) | reflection: Label "dynamic invoke" in `code_typed` |
| [#58430](https://github.com/JuliaLang/julia/pull/58430) | stacktraces: Add an extension point for printing custom-owner CIs |
| [#58815](https://github.com/JuliaLang/julia/pull/58815) | jl_dlfind: do not find symbols in library dependencies |
| [#58877](https://github.com/JuliaLang/julia/pull/58877) | Add missing module qualifier |
| [#58891](https://github.com/JuliaLang/julia/pull/58891) | Support "functors" for code reflection utilities |
| [#58926](https://github.com/JuliaLang/julia/pull/58926) | Economy mode REPL: run the event loop with jl_uv_flush |
| [#58955](https://github.com/JuliaLang/julia/pull/58955) | chore: remove redundant words in comment |
| [#59158](https://github.com/JuliaLang/julia/pull/59158) | rename `GlobalMethods` to `methodtable` |
| [#59202](https://github.com/JuliaLang/julia/pull/59202) | compiler: eliminate most of unused variables in the compiler |
| [#59216](https://github.com/JuliaLang/julia/pull/59216) | remove jl_function_t typealias |
| [#59635](https://github.com/JuliaLang/julia/pull/59635) | Change delayed delete mechanism to prevent cross-drive mv failure for in-use DLL |
| [#59910](https://github.com/JuliaLang/julia/pull/59910) | Use libuv in absrealpath to fix Korean path names on Windows |

## Summary

| Category | Missing | Analyzed | Total |
|---|---|---|---|
| Inference | 40 | ~15 | ~55 |
| Optimizer | 14 | ~8 | ~22 |
| Lowering | 23 | ~5 | ~28 |
| Codegen/LLVM | 51 | ~5 | ~56 |
| GC/Runtime | 28 | ~5 | ~33 |
| Binding Partitions | 19 | ~3 | ~22 |
| Compilation Infrastructure | 45 | ~15 | ~60 |
| IR/Verification | 10 | ~5 | ~15 |
| Other | 28 | ~6 | ~34 |
| **Total** | **258** | **67** | **~325** |
