# Julia Compiler Deep Dive: SSA IR Representation

**Target audience**: Julia developers familiar with the language who want to understand how code is represented during optimization.

**Source commit**: [`4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c`](https://github.com/JuliaLang/julia/tree/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c)

---

## Table of Contents

1. [What is SSA Form?](#1-what-is-ssa-form)
2. [IRCode: The Central Data Structure](#2-ircode-the-central-data-structure)
3. [Control Flow Graphs](#3-control-flow-graphs)
4. [Dominator Trees](#4-dominator-trees)
5. [IncrementalCompact: Efficient IR Modification](#5-incrementalcompact-efficient-ir-modification)
6. [Reading @code_typed Output](#6-reading-code_typed-output)
7. [Cross-Reference to Optimization Passes](#7-cross-reference-to-optimization-passes)
8. [Summary](#8-summary)

---

## 1. What is SSA Form?

### 1.1 The Problem with Mutable Variables

Consider this simple Julia function:

```julia
function example(x)
    y = x + 1
    if x > 0
        y = y * 2
    end
    return y
end
```

In this code, `y` is assigned twice. When the compiler tries to reason about what value `y` holds at the `return` statement, it faces a challenge: `y` could be either `x + 1` or `(x + 1) * 2` depending on the branch taken.

Traditional compilers that allow mutable variables must perform complex **dataflow analysis** to track all possible values a variable might hold at each point in the program. This analysis is expensive and error-prone.

### 1.2 The SSA Solution

**Static Single Assignment (SSA) form** solves this problem with a simple rule:

> **Every variable is assigned exactly once.**

In SSA form, our example becomes:

```
%1 = x + 1           # original y = x + 1
if x > 0 goto bb2 else bb3

bb2:
  %2 = %1 * 2        # y = y * 2, but with new name
  goto bb3

bb3:
  %3 = phi(%1, %2)   # merge point: which value?
  return %3
```

Notice what changed:
- Each assignment creates a **new SSA value** (`%1`, `%2`, `%3`)
- Values are **never reassigned**
- At merge points, we use **phi nodes** to select between values

### 1.3 Why SSA Makes Optimization Easier

With SSA form, optimizations become dramatically simpler:

| Without SSA | With SSA |
|-------------|----------|
| "What value could `y` have here?" requires dataflow analysis | Just look at the definition of `%3` |
| "Is this assignment dead?" requires liveness analysis | If `%2` has no uses, it is dead |
| "Can I move this computation?" requires alias analysis | SSA values are immutable, move freely |

The Julia compiler converts lowered code (with mutable slot variables) into SSA form before running any optimization passes.

### 1.4 SSA Value Types in Julia

Julia's compiler uses several types to represent SSA values:

```julia
# Core SSA reference - defined in Core
struct SSAValue
    id::Int  # Index into the statement array
end

# Function arguments are also SSA values
struct Argument
    n::Int   # Argument position (1-indexed)
end
```

During IR transformation, two additional types track values across renumbering:

- **`OldSSAValue`** ([ir.jl:226-228](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L226-L228)): References a pre-compaction SSA value
- **`NewSSAValue`** ([ir.jl:248-250](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L248-L250)): References a newly inserted node

---

## 2. IRCode: The Central Data Structure

### 2.1 The IRCode Structure

`IRCode` is the primary container for Julia's SSA IR. Every optimization pass works with this structure.

**Source**: [ssair/ir.jl:427-455](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L427-L455)

```julia
struct IRCode
    stmts::InstructionStream      # The statements (instructions)
    argtypes::Vector{Any}         # Types of function arguments
    sptypes::Vector{VarState}     # Static parameter types
    debuginfo::DebugInfoStream    # Source location information
    cfg::CFG                      # Control Flow Graph
    new_nodes::NewNodeStream      # Pending inserted nodes (lazy insertion)
    meta::Vector{Expr}            # Metadata expressions
    valid_worlds::WorldRange      # World age validity range
end
```

Let us examine each component.

### 2.2 InstructionStream: The Statement Array

The `InstructionStream` holds all statements in parallel arrays for cache efficiency:

**Source**: [ssair/ir.jl:255-274](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L255-L274)

```julia
struct InstructionStream
    stmt::Vector{Any}        # The actual statements (Expr, GotoNode, etc.)
    type::Vector{Any}        # Inferred type of each statement's result
    info::Vector{CallInfo}   # Call site information (for inlining decisions)
    line::Vector{Int32}      # Line number info (3 entries per statement)
    flag::Vector{UInt32}     # IR flags (effects, inlining hints, etc.)
end
```

Each SSA value `%i` corresponds to `stmts[i]`. The type of `%i` is `type[i]`.

### 2.3 Visualizing IRCode Structure

```
                        IRCode
    +--------------------------------------------------+
    |                                                  |
    |  argtypes: [Int64, Float64]   (argument types)   |
    |                                                  |
    |  stmts: InstructionStream                        |
    |    +------------------------------------------+  |
    |    | stmt[1]: %1 = arg1 + 1                   |  |
    |    | type[1]: Int64                           |  |
    |    | flag[1]: NOTHROW | EFFECT_FREE           |  |
    |    +------------------------------------------+  |
    |    | stmt[2]: %2 = %1 * arg2                  |  |
    |    | type[2]: Float64                         |  |
    |    | flag[2]: NOTHROW | EFFECT_FREE           |  |
    |    +------------------------------------------+  |
    |    | stmt[3]: return %2                       |  |
    |    | type[3]: Nothing                         |  |
    |    +------------------------------------------+  |
    |                                                  |
    |  cfg: CFG (see Section 3)                        |
    |                                                  |
    |  new_nodes: [] (empty until insertion)           |
    |                                                  |
    +--------------------------------------------------+
```

### 2.4 Statement Types

Statements in SSA IR can be:

| Statement Type | Description | Example |
|---------------|-------------|---------|
| `Expr(:call, ...)` | Function call | `Expr(:call, +, %1, %2)` |
| `Expr(:invoke, ...)` | Direct method call | `Expr(:invoke, mi, f, args...)` |
| `Expr(:new, ...)` | Struct allocation | `Expr(:new, Point, %1, %2)` |
| `GotoNode(label)` | Unconditional jump | `GotoNode(3)` |
| `GotoIfNot(cond, dest)` | Conditional branch | `GotoIfNot(%5, 4)` |
| `ReturnNode(val)` | Function return | `ReturnNode(%3)` |
| `PhiNode(edges, values)` | SSA merge | `PhiNode([2, 3], [%1, %2])` |
| `PiNode(val, typ)` | Type assertion | `PiNode(%1, Int64)` |
| `UpsilonNode(val)` | Catch variable def | `UpsilonNode(%2)` |
| `PhiCNode(values)` | Catch phi node | `PhiCNode([%3, %4])` |

### 2.5 IR Flags

Each statement has associated flags that encode effect information. This is a **subset** of the full list:

**Source**: [optimize.jl:18-62](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L18-L62)

```julia
const IR_FLAG_INBOUNDS    = 1 << 0   # @inbounds annotation
const IR_FLAG_INLINE      = 1 << 1   # @inline annotation
const IR_FLAG_NOINLINE    = 1 << 2   # @noinline annotation
const IR_FLAG_CONSISTENT  = 1 << 3   # Same inputs -> same output
const IR_FLAG_EFFECT_FREE = 1 << 4   # No observable side effects
const IR_FLAG_NOTHROW     = 1 << 5   # Cannot throw an exception
const IR_FLAG_TERMINATES  = 1 << 6   # Always terminates
const IR_FLAG_NOUB        = 1 << 10  # No undefined behavior
const IR_FLAG_NORTCALL    = 1 << 13  # No runtime return_type call
const IR_FLAG_REFINED     = 1 << 16  # Refinement info available
const IR_FLAG_UNUSED      = 1 << 17  # Statement result unused
```

These flags enable dead code elimination: if a statement is `EFFECT_FREE`, `NOTHROW`, and `TERMINATES`, and its result is unused, the statement can be safely removed. See `optimize.jl` for the full flag list (including `INACCESSIBLEMEM`-related flags).

---

## 3. Control Flow Graphs

### 3.1 What is a CFG?

A **Control Flow Graph (CFG)** represents the possible execution paths through a function. It consists of:

- **Basic blocks**: Sequences of instructions with no internal branching
- **Edges**: Connections between blocks representing possible control flow

### 3.2 CFG Structure

**Source**: [ssair/ir.jl:6-10](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L6-L10)

```julia
struct CFG
    blocks::Vector{BasicBlock}
    index::Vector{Int}  # Map from instruction index to block number
end
```

### 3.3 BasicBlock Structure

**Source**: [ssair/basicblock.jl:18-22](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/basicblock.jl#L18-L22)

```julia
struct BasicBlock
    stmts::StmtRange      # Range of statement indices (e.g., 1:3)
    preds::Vector{Int}    # Predecessor block indices
    succs::Vector{Int}    # Successor block indices
end

# StmtRange is simply:
struct StmtRange
    start::Int
    stop::Int
end
```

### 3.4 CFG Example

Consider this function:

```julia
function abs_val(x)
    if x < 0
        return -x
    else
        return x
    end
end
```

Its CFG looks like:

```
         +----------------+
         |  BB #1 (entry) |
         |  %1 = x < 0    |
         |  if %1 goto 2  |
         |  else goto 3   |
         +-------+--------+
                 |
        +--------+--------+
        |                 |
        v                 v
+---------------+  +---------------+
|    BB #2      |  |    BB #3      |
|  %2 = -x      |  |  return x     |
|  return %2    |  |               |
+---------------+  +---------------+

Block relationships:
  BB #1: preds=[], succs=[2, 3]
  BB #2: preds=[1], succs=[]
  BB #3: preds=[1], succs=[]
```

### 3.5 Computing Basic Blocks

**Source**: [ssair/ir.jl:94-150](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L94-L150)

The `compute_basic_blocks` function:

1. **Identifies block boundaries**: Entry point, jump targets, fall-through after branches
2. **Creates BasicBlock objects**: With statement ranges
3. **Computes edges**: Predecessors and successors based on branch instructions

```julia
# Key logic for finding block starts (simplified)
for (idx, stmt) in enumerate(stmts)
    if isa(stmt, GotoNode)
        push!(jump_dests, stmt.label)
    elseif isa(stmt, GotoIfNot)
        push!(jump_dests, stmt.dest)
        push!(jump_dests, idx + 1)  # fall-through
    end
end
```

### 3.6 CFG Manipulation Functions

| Function | Source | Purpose |
|----------|--------|---------|
| `cfg_insert_edge!` | [ir.jl:14-18](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L14-L18) | Add an edge between blocks |
| `cfg_delete_edge!` | [ir.jl:21-28](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L21-L28) | Remove an edge between blocks |
| `block_for_inst` | [ir.jl:36-44](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L36-L44) | Find which block contains an instruction (O(log n)) |

---

## 4. Dominator Trees

### 4.1 What is Dominance?

A block A **dominates** block B if every path from the function entry to B must go through A.

The **immediate dominator** of B is the closest block that dominates B.

**Why dominance matters for SSA:**
- Phi nodes are only needed where control flow merges
- Specifically, at points in the **iterated dominance frontier**
- Dominance also determines where values are "visible" (usable)

### 4.2 Dominator Tree Example

```
CFG:                          Dominator Tree:
    +---+                           +---+
    | 1 |                           | 1 |
    +---+                           +---+
    /   \                          /  |  \
   v     v                        v   v   v
+---+   +---+                  +---+ +---+ +---+
| 2 |   | 3 |                  | 2 | | 3 | | 4 |
+---+   +---+                  +---+ +---+ +---+
   \     /
    v   v
    +---+
    | 4 |
    +---+

Dominance relationships:
  - Block 1 dominates all blocks (it is the entry)
  - Block 4 is dominated by 1 only (2 and 3 are not on ALL paths to 4)
```

### 4.3 The Semi-NCA Algorithm

Julia uses the **Semi-NCA (SNCA)** algorithm from Georgiadis' PhD thesis, the same algorithm used by LLVM.

**Source**: [ssair/domtree.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl)

Key data structures:

```julia
# DFS Tree: captures traversal order
struct DFSTree
    to_pre::Vector{Int}     # Block number -> preorder number
    from_pre::Vector{Int}   # Preorder number -> block number
    to_parent_pre::Vector{Int}  # Preorder -> parent's preorder
    to_post::Vector{Int}    # Block -> postorder number
    from_post::Vector{Int}  # Postorder -> block number
end

# Per-block data for SNCA
struct SNCAData
    semi::Int     # Semidominator (preorder number)
    label::Int    # For path compression
end

# Dominator tree node
struct DomTreeNode
    level::Int              # Depth in domtree
    children::Vector{Int}   # Children block numbers
end

# Complete dominator tree
struct GenericDomTree{IsPostDom}
    dfs_tree::DFSTree
    idoms_bb::Vector{Int}       # Immediate dominator for each block
    nodes::Vector{DomTreeNode}  # Tree structure
end
# Note: PostDomTree is available via GenericDomTree{true} parameterization (line 235)
```

### 4.4 Key Dominator Functions

| Function | Source | Purpose |
|----------|--------|---------|
| `construct_domtree` | [domtree.jl:241-243](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L241-L243) | Build dominator tree from CFG |
| `DFS!` | [domtree.jl:123-198](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L123-L198) | Depth-first search for pre/post order |
| `SNCA!` | [domtree.jl:307-405](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L307-L405) | Main Semi-NCA algorithm |
| `dominates` | [domtree.jl:605-606](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L605-L606) | Check if block A dominates block B |
| `nearest_common_dominator` | [domtree.jl:659-679](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L659-L679) | Find lowest common ancestor in domtree |

### 4.5 Dynamic Dominator Updates

Julia supports **incremental dominator tree updates** using Dynamic SNCA:

**Source**: [domtree.jl:450-501](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl#L450-L501)

```julia
# When an edge is added to the CFG
domtree_insert_edge!(domtree, cfg, from_bb, to_bb)  # domtree.jl:450-473

# When an edge is removed
domtree_delete_edge!(domtree, cfg, from_bb, to_bb)  # domtree.jl:476-501
```

This avoids rebuilding the entire dominator tree when the CFG changes during optimization.

### 4.6 Iterated Dominance Frontier

The **Iterated Dominance Frontier (IDF)** determines where phi nodes must be placed during SSA construction.

**Source**: [ssair/slot2ssa.jl:231-287](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/slot2ssa.jl#L231-L287)

```julia
# Simplified IDF algorithm
function iterated_dominance_frontier(cfg, liveness, domtree)
    phi_locations = Set{Int}()
    worklist = copy(liveness.def_bbs)  # Blocks that define the variable

    while !isempty(worklist)
        block = pop!(worklist)
        for frontier_block in dominance_frontier(block, domtree)
            if frontier_block in liveness.live_in_bbs
                if frontier_block not in phi_locations
                    push!(phi_locations, frontier_block)
                    push!(worklist, frontier_block)  # Iterate!
                end
            end
        end
    end
    return phi_locations
end
```

---

## 5. IncrementalCompact: Efficient IR Modification

### 5.1 The Challenge of IR Modification

Optimization passes need to:
- Insert new instructions
- Delete dead code
- Replace instructions with simpler versions
- Modify control flow

Naive approaches require expensive renumbering of all SSA values after each change.

### 5.2 IncrementalCompact Solution

`IncrementalCompact` is a **mutable iterator** that processes IR statements one at a time, enabling on-the-fly modifications without expensive renumbering.

**Source**: [ssair/ir.jl:745-804](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L745-L804)

```julia
mutable struct IncrementalCompact
    ir::IRCode
    result::InstructionStream       # New compacted IR
    result_bbs::Vector{BasicBlock}  # New basic blocks

    # Renumbering state
    ssa_rename::Vector{Any}         # old SSA -> new SSA mapping
    used_ssas::Vector{Int}          # Use count for each new SSA

    # Iteration state
    idx::Int                        # Current position in old IR
    result_idx::Int                 # Current position in new IR

    # ... additional bookkeeping fields
end
```

*Note: Simplified - see source for complete field list (actual struct has 17 fields).*

### 5.3 How IncrementalCompact Works

```
Before compaction:          During compaction:           After compaction:
+------------------+        +------------------+        +------------------+
| %1 = a + b       |   -->  | %1 = a + b       |   -->  | %1 = a + b       |
| %2 = %1 * 2      |        | (processing...)  |        | %2 = %1 * 2      |
| %3 = unused_call |        |                  |        | return %2        |
| return %2        |        |                  |        +------------------+
+------------------+        +------------------+        (dead code removed)

Key insight: As we iterate, we:
1. Copy live statements to result
2. Track SSA renumbering (old %n -> new %m)
3. Count uses (unused = dead)
4. Insert new nodes at current position
```

### 5.4 Key IncrementalCompact Operations

| Function | Source | Purpose |
|----------|--------|---------|
| `IncrementalCompact(ir)` | [ir.jl:769-787](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L769-L787) | Create compaction iterator |
| `iterate_compact` | [ir.jl:1877-1963](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L1877-L1963) | Core iteration logic |
| `process_node!` | [ir.jl:1459-1698](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L1459-L1698) | Process single instruction |
| `insert_node!` | [ir.jl:975-1032](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L975-L1032) | Insert new instruction |
| `insert_node_here!` | [ir.jl:1050-1067](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L1050-L1067) | Insert at current position |
| `CFGTransformState` | [ir.jl:678-693](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L678-L693) | Tracks CFG transformations during compaction |
| `finish` | [ir.jl:2117-2121](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L2117-L2121) | Complete compaction with DCE |
| `compact!` | [ir.jl:2145-2150](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L2145-L2150) | One-shot full compaction |

### 5.5 Using IncrementalCompact in an Optimization Pass

Here is a simplified pattern used by optimization passes:

```julia
function my_optimization_pass!(ir::IRCode)
    compact = IncrementalCompact(ir)

    for ((old_idx, idx), stmt) in compact
        # old_idx: position in original IR
        # idx: position in compacted IR
        # stmt: the statement being processed

        if should_replace(stmt)
            # Replace statement with a simpler version
            compact[idx] = simplified_stmt
        elseif should_delete(stmt)
            # Mark as dead (will be removed if no uses)
            compact[idx] = nothing
        elseif should_insert_before(stmt)
            # Insert a new instruction before current
            new_ssa = insert_node_here!(compact, new_stmt, new_type, flags)
            # new_ssa can be used in subsequent statements
        end
    end

    # Finalize: removes dead code, renumbers SSA values
    return finish(compact)
end
```

### 5.6 Automatic Dead Code Elimination

`IncrementalCompact` tracks use counts for each SSA value in `used_ssas`. When `finish` is called:

**Source**: [ssair/ir.jl:2088-2100](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl#L2088-L2100)

```julia
function simple_dce!(compact::IncrementalCompact)
    for idx in 1:length(compact.result)
        if compact.used_ssas[idx] == 0  # No uses!
            stmt = compact.result[idx]
            if is_removable(stmt)  # Effect-free, no throw, terminates
                compact.result[idx] = nothing  # Remove it
            end
        end
    end
end
```

This means passes do not need to explicitly track dead code - it is removed automatically.

---

## 6. Reading @code_typed Output

### 6.1 Accessing the IR

Julia provides introspection macros to view compiler IR:

```julia
# View the IR with inferred types
@code_typed optimize=true f(args...)

# Get as data structure for programmatic access
code_typed(f, (ArgType1, ArgType2); optimize=true)
```

### 6.2 Example: Reading IR Output

```julia
julia> function example(x::Int)
           y = x + 1
           if y > 10
               return y * 2
           else
               return y
           end
       end

julia> @code_typed example(5)
CodeInfo(
1 - %1 = Base.add_int(x, 1)::Int64
|   %2 = Base.slt_int(10, %1)::Bool
+-- goto #3 if not %2
2 - %3 = Base.mul_int(%1, 2)::Int64
|   return %3
3 - return %1
) => Int64
```

### 6.3 Understanding the Output

Let us break down each element:

```
1 - %1 = Base.add_int(x, 1)::Int64
^   ^    ^                   ^
|   |    |                   +-- Inferred return type
|   |    +-- Statement (intrinsic call)
|   +-- SSA value number
+-- Basic block number
```

**Block markers:**
- `1 -` : Block 1, dash indicates block start
- `|` : Continuation of current block
- `+--` : Control flow instruction (branch/jump)

**Control flow:**
- `goto #3 if not %2` : `GotoIfNot(%2, 3)` - jump to block 3 if `%2` is false
- `return %3` : `ReturnNode(%3)`

### 6.4 Viewing Raw IRCode

For more detail, use the lower-level API:

```julia
julia> using Core.Compiler: IRCode

julia> # Get the IRCode structure
julia> _, ir = only(code_typed(example, (Int,); optimize=true));

julia> # Examine the CFG
julia> ir.cfg
CFG with 3 blocks:
  bb 1: preds=[], succs=[2, 3]
  bb 2: preds=[1], succs=[]
  bb 3: preds=[1], succs=[]

julia> # Examine statement types
julia> ir.stmts.type
4-element Vector{Any}:
 Int64
 Bool
 Int64
 Int64
```

### 6.5 Viewing IR at Different Optimization Stages

```julia
# Before optimization (after type inference)
@code_typed optimize=false f(args...)

# After full optimization
@code_typed optimize=true f(args...)

# At a specific pass (Julia 1.9+)
# Use undocumented internal API (may change across versions):
# code_typed(f, types; optimize=true, optimize_until="CC: INLINING")
```

---

## 7. Cross-Reference to Optimization Passes

The SSA IR is the foundation for all optimization passes. Here is how each pass uses it:

### 7.1 Pass Pipeline

**Source**: [optimize.jl:1044-1076](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/optimize.jl#L1044-L1076)

```
CodeInfo (lowered IR)
    |
    v
[CONVERT] convert_to_ircode() --> IRCode
    |
    v
[SLOT2REG] slot2reg() --> SSA form
    |
    v
[COMPACT_1] compact!() --> Clean IR
    |
    v
[INLINING] ssa_inlining_pass!() --> Inlined IR
    |
    v
[COMPACT_2] compact!() --> Clean IR
    |
    v
[SROA] sroa_pass!() --> Scalar replacement
    |
    v
[ADCE] adce_pass!() --> Dead code removed
    |
    v
[COMPACT_3] compact!() (if needed)
    |
    v
Optimized IRCode
```

### 7.2 How Passes Use SSA IR

| Pass | SSA IR Usage |
|------|--------------|
| **Inlining** | Creates child `IncrementalCompact`, splices inlined IR, manages CFG changes |
| **SROA** | Walks def-use chains via SSA references, uses dominator tree for phi placement |
| **ADCE** | Uses `used_ssas` tracking, simplifies phi nodes, removes dead branches |
| **Constant Propagation** | Replaces SSA values with `Const` types, folds branches |

### 7.3 Example: How SROA Uses the IR

SROA (Scalar Replacement of Aggregates) optimizes struct allocations by tracking field accesses:

```julia
# Before SROA
%1 = new(Point, x, y)  # Allocate Point struct
%2 = getfield(%1, :x)  # Access x field
return %2

# After SROA
return x  # Struct allocation eliminated!
```

SROA achieves this by:
1. Using `collect_leaves` to find allocation sites through phi nodes
2. Using the dominator tree to place phi nodes for lifted field values
3. Using `IncrementalCompact` to replace `getfield` with lifted values

See [ssair/passes.jl:1264-1579](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/passes.jl#L1264-L1579).

### 7.4 Example: How Inlining Uses the IR

The inlining pass operates in two phases:

1. **Analysis** (`assemble_inline_todo!`): Examines call sites, computes costs
2. **Execution** (`batch_inline!`): Splices callee IR into caller

For multi-block inlinees, it:
- Renumbers callee SSA values to avoid conflicts
- Updates CFG with new blocks
- Creates phi nodes to merge return values

See [ssair/inlining.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/inlining.jl).

---

## 8. Summary

### 8.1 Key Concepts

| Concept | Description |
|---------|-------------|
| **SSA Form** | Each variable assigned exactly once; enables simpler analysis |
| **IRCode** | Central container holding statements, types, CFG, and metadata |
| **CFG** | Basic blocks with predecessor/successor edges |
| **Dominator Tree** | Captures "must pass through" relationships for phi placement |
| **IncrementalCompact** | Efficient on-the-fly IR modification with automatic DCE |

### 8.2 Key Files

| File | Lines | Purpose |
|------|-------|---------|
| [ssair/ir.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/ir.jl) | ~2181 | IRCode, CFG, IncrementalCompact |
| [ssair/basicblock.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/basicblock.jl) | ~32 | BasicBlock, StmtRange |
| [ssair/domtree.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/domtree.jl) | ~728 | Dominator tree (SNCA algorithm) |
| [ssair/slot2ssa.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/slot2ssa.jl) | ~896 | Slot-to-SSA conversion |
| [ssair/legacy.jl](https://github.com/JuliaLang/julia/blob/4d04bb6b3b1b879f4dbb918d194c5c939a1e7f3c/Compiler/src/ssair/legacy.jl) | ~106 | IRCode to/from CodeInfo |

### 8.3 Key Functions Quick Reference

| Function | Purpose |
|----------|---------|
| `compute_basic_blocks` | Build CFG from statements |
| `construct_domtree` | Build dominator tree |
| `dominates(domtree, a, b)` | Check if block `a` dominates `b` |
| `construct_ssa!` | Convert slots to SSA form |
| `IncrementalCompact(ir)` | Create compaction iterator |
| `insert_node!` / `insert_node_here!` | Insert new IR nodes |
| `compact!(ir)` | Full IR compaction |
| `block_for_inst(cfg, idx)` | Find block containing instruction |

### 8.4 Design Principles

1. **Immutability of SSA values**: Once defined, values never change
2. **Lazy insertion**: `new_nodes` stream allows inserting without immediate reindexing
3. **Use counting**: Automatic dead code elimination without separate analysis
4. **Incremental updates**: Dynamic dominator tree updates avoid full recomputation
5. **Parallel arrays**: `InstructionStream` uses separate arrays for cache efficiency

---

## Further Reading

- **Type Inference**: How types flow into the IR (see exploration-T1-type-inference.md)
- **Optimization Passes**: How passes transform the IR (see exploration-T5-optimization.md)
- **Escape Analysis**: How escape information guides optimization (see exploration-T6-escape-analysis.md)
- **Effects System**: How effect flags enable dead code elimination (see exploration-T7-effects.md)
