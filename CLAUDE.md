## Julia Compiler PR Analysis

Analyze Julia compiler PRs for deeper context on changes and their effects.

### Workflow

1. Checkout the PR merge commit in the `julia/` workspace
   ```bash
   cd julia && git fetch origin pull/{PR_NUMBER}/merge:pr-{PR_NUMBER} && git checkout pr-{PR_NUMBER}
   ```

2. Fetch PR metadata with `gh pr view {PR_NUMBER} --json title,body,labels,mergedAt,files`

3. Read the diff to understand surface-level changes

4. Read full file context around each change (not just the diff)

5. Trace call chains with `rg`:
   - Upstream: who calls the modified functions?
   - Downstream: what does the modified code call?

6. Identify behavior changes: semantic, performance, or API

7. Assess downstream package impact

### Compiler Pipeline

```
JuliaSyntax tokenizer/parser
  -> Macro expansion + hygiene
  -> Lowering + desugaring + scope analysis
  -> Closure conversion + linearization -> CodeInfo
  -> Abstract interpretation + type inference
  -> Effects + escape analysis
  -> Inlining + optimization passes
  -> Codegen / LLVM pipeline
  -> Interpreter fallback
```

### Key Questions

- What does the PR fix/improve?
- Which pipeline stage(s) are touched?
- Could user code behave differently?
- Does it change inference, inlining, or effects?
- Are there API/struct changes affecting downstream tools?

For downstream packages using compiler internals:
- Does it change struct fields they might read? (e.g., `CodeInfo`, `IRCode`, `InferenceState`)
- Does it add/remove/rename methods they might call or extend?
- Does it change IR shape or new node types they need to handle?
- Does it affect OpaqueClosure creation or inference?
- Does it change effect flags or escape analysis results they rely on?

### Guidelines

- Use actual code snippets, not descriptions
- Trace call chains with file:line locations
- Back claims with evidence from the code
- Include test examples showing behavior changes
- Search for all callers of modified functions with `rg`

### Output

Write YAML to `analyses/{version}/pr_{number}.yaml`:

```yaml
pr:
  number: int
  title: string
  merge_commit_sha: string
scope:
  files_touched: [string]
  pipeline_stages: [string]
analysis:
  summary: string
  changes:
    - description: string
      evidence: string
  downstream_impact: [string]
  risk: low|medium|high
```
