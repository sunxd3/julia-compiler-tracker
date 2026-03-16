# julia-compiler — Claude Code Plugin

A Claude Code plugin that helps developers of Julia compiler-dependent packages migrate between Julia versions.

## What it does

Analyzes breaking changes in Julia compiler internals — struct layouts, function signatures, inference behavior, IR shape — and produces actionable migration guides for packages that depend on compiler internals.

## Install

```bash
# Local development
claude --plugin-dir ./julia-compiler-tracker

# Or use the skill directly
/julia-compiler:julia-migration
```

## Structure

```
├── .claude-plugin/
│   └── plugin.json                     # Plugin manifest
├── skills/
│   └── julia-migration/
│       ├── SKILL.md                    # Skill definition
│       └── references/
│           └── compiler-internals.md   # Compiler subsystem reference
```
