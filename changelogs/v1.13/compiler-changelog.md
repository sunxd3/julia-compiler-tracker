# Julia v1.13 Compiler Release Notes

## Frontend and Lowering

* Binding partitions now define module/global binding semantics directly via partitioned semantics,
  removing timing-dependent "resolvedness" behavior and making weak-vs-strong global handling more
  predictable ([#57253]).
* The distinction between pointer and name in `ccall` is now a syntactic distinction via tuple syntax.
  Name-based `ccall` is no longer inferred from runtime values; lowering normalizes name-based calls
  into tuple syntax, and the compiler/codegen path treats tuple syntax as the canonical representation
  for named foreign calls. Tools must stop assuming the first `foreigncall` argument is a `QuoteNode`
  or `Symbol` ([#59165]).
* Assignment (`=`) and `const` declarations are now toplevel-preserving syntax, fixing closure
  conversion behavior and ensuring that certain toplevel declarations are preserved and hoisted
  correctly ([#59784]).
* Lowered IR no longer uses `:global` and `:globaldecl` as the operative forms for global declarations.
  Declaration effects are now routed through `Core.declare_global`, with additional machinery to suppress
  those effects in generated-function contexts where needed ([#58279]).

## Type Inference and Effects

* Fixed def-use map population by passing the statement (not `Instruction` wrapper) to `userefs()`,
  preventing early scan exits that left def-use counts incomplete. This ensures correct type refinement
  propagation in the IR interpreter ([#56201]).
* `PartialStruct` is now a fixed-shape representation that can encode field-by-field definedness,
  including strict-undef state, instead of a loose variable-length approximation. This changes
  how partially initialized objects are represented during abstract interpretation ([#57541]).
* Unhandled builtins now fall back to the most conservative effect summary (`Effects()`) instead of
  quietly assigning narrower effects. This reduces the chance of accidentally unsound builtin-effect
  assumptions ([#57856]).
* Fixed an inference unsoundness in `getfield_tfunc` on tuple types by making the analysis more
  conservative instead of incorrectly constant-folding ([#57275]).
* Inference now avoids caching certain `LimitedAccuracy` intermediates that could recursively trigger
  more compilation work, fixing a real non-termination class ([#58273]).
* Type assertion added to `isfinite(::AbstractFloat)` to return `::Bool`, fixing an inference weakness
  that was causing invalidations to spread into downstream packages. `isinf(::Real)` and related call
  chains now infer as `Bool` instead of `Any` ([#59888]).
* The abstract interpreter now allows ad-hoc cancellation of concrete evaluation: returning `nothing`
  from `concrete_eval_call` means "cancel and fall back to regular abstract interpretation /
  const-prop." Custom `AbstractInterpreter` implementations can now decline concrete evaluation on a
  per-call basis ([#59908]).
* Fixed type setting for boxed variables in `abstract_eval_nonlinearized_foreigncall_name`, improving
  inference correctness for foreign function calls ([#59921]).

## Custom Interpreters and Tooling Extensions

* Custom `AbstractInterpreter`s can now expose a `codegen_cache`, allowing Julia to push their
  `CodeInstance`s into the JIT so they become legal `invoke` targets instead of staying trapped
  inside a private analysis pipeline ([#57272]).
* `Base._which` now resolves the compiler module from the actual `MethodTableView` type instead
  of assuming Base's compiler module, fixing reflection for custom compiler modules and overlay
  method tables ([#59915]).

## Dispatch and Compiler Infrastructure

* Method lookup now centers on one global `MethodTable` plus explicit external-table membership,
  changing how compiler internals and reflection reason about method ownership ([#58131]).
* Dispatch lifecycle metadata is now an explicit `dispatch_status` contract on `Method` and
  `MethodInstance`, affecting invalidation, staticdata, and reinference code ([#58291]).

## Optimizer and IR

* The entry basic block now always has virtual predecessor `0`. Downstream inlining logic must
  interpret this sentinel correctly rather than treating it like an ordinary predecessor ([#58683]).
* If Julia cannot safely invoke a generated function's generator during compilation, it now refuses
  to inline the fallback body and leaves runtime dispatch in place instead of speculating through
  the wrong path ([#59018]).
* Optimizer work now uses a temporary cache and delays global `CodeInstance` publication until
  finishing, preventing partially initialized compiler artifacts from escaping early ([#58343]).
* `CodeInstance.inferred` can now store encoded inlining-cost information instead of retained IR
  in some cases, changing part of Julia's cache/serialization representation ([#58662]).

## Codegen and LLVM

* Julia 1.13 moves the backend toolchain to LLVM 20 ([#58142]).
* `gc_safe` foreign calls now lower through explicit unsafe->safe->unsafe GC transitions instead
  of relying on a looser calling convention ([#49933]).

## Runtime and GC

* Aligned interpreter and codegen error behavior for `setglobal!` and related global-assignment
  builtins, ensuring consistent semantics across execution modes. `TypeError.context` now carries
  meaningful global-binding context ([#59766]).
* Skips method instance normalization for opaque closure methods, improving runtime correctness
  for opaque closures ([#59772]).
* Fixed a missing GC root in `jl_type_error_global`: the function now protects `JL_MAYBE_UNROOTED`
  arguments with `JL_GC_PUSH2` before calling allocation functions. Also corrects
  `jl_module_globalref` annotation from `JL_GLOBALLY_ROOTED` to `JL_PROPAGATES_ROOT` ([#59785]).

<!--- generated by julia-compiler-tracker: -->
[#49933]: https://github.com/JuliaLang/julia/issues/49933
[#56201]: https://github.com/JuliaLang/julia/issues/56201
[#57253]: https://github.com/JuliaLang/julia/issues/57253
[#57272]: https://github.com/JuliaLang/julia/issues/57272
[#57275]: https://github.com/JuliaLang/julia/issues/57275
[#57541]: https://github.com/JuliaLang/julia/issues/57541
[#57856]: https://github.com/JuliaLang/julia/issues/57856
[#58131]: https://github.com/JuliaLang/julia/issues/58131
[#58142]: https://github.com/JuliaLang/julia/issues/58142
[#58273]: https://github.com/JuliaLang/julia/issues/58273
[#58279]: https://github.com/JuliaLang/julia/issues/58279
[#58291]: https://github.com/JuliaLang/julia/issues/58291
[#58343]: https://github.com/JuliaLang/julia/issues/58343
[#58662]: https://github.com/JuliaLang/julia/issues/58662
[#58683]: https://github.com/JuliaLang/julia/issues/58683
[#59018]: https://github.com/JuliaLang/julia/issues/59018
[#59165]: https://github.com/JuliaLang/julia/issues/59165
[#59766]: https://github.com/JuliaLang/julia/issues/59766
[#59772]: https://github.com/JuliaLang/julia/issues/59772
[#59784]: https://github.com/JuliaLang/julia/issues/59784
[#59785]: https://github.com/JuliaLang/julia/issues/59785
[#59888]: https://github.com/JuliaLang/julia/issues/59888
[#59908]: https://github.com/JuliaLang/julia/issues/59908
[#59915]: https://github.com/JuliaLang/julia/issues/59915
[#59921]: https://github.com/JuliaLang/julia/issues/59921
