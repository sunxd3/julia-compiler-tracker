# Julia Compiler Tracker

Track and analyze compiler-related changes in Julia for downstream package maintainers.

## Structure

```
├── julia/                  # Julia repo workspace (checkout PRs here)
├── analyses/
│   ├── v1.13/             # PR analyses for Julia 1.13
│   └── v1.14/             # PR analyses for Julia 1.14
├── changelogs/            # Version changelogs
├── compiler-deep-dive/    # Julia compiler internals documentation
└── versions.yaml          # Version metadata (branch points, etc.)
```
