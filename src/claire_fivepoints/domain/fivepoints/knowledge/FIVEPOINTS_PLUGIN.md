---
name: FIVEPOINTS_PLUGIN
domain: fivepoints
category: knowledge
title: Fivepoints Plugin — Overview
description: Plugin overview for claire-fivepoints — workflow registry, adapters, and ADO integration
keywords: [fivepoints, plugin, workflows, tfone, ado, azure-devops]
updated: 2026-05-16
---

# Fivepoints Plugin

The `claire-fivepoints` package registers fivepoints-specific workflows and adapters
into the Claire V2 pipeline.

---

## Registered Workflows

| Entry-point key | Function |
|-----------------|----------|
| `fivepoints.tfone.github` | `run_fivepoints_tfone_github_for_issue` — GitHub-only flow (analyst → dev → tester) |
| `fivepoints.tfone.full` | `run_fivepoints_tfone_full_for_issue` — Full flow including ADO sync |

### Dispatch examples

```bash
# GitHub-only flow for a single issue
claire dispatch --workflow fivepoints.tfone.github --issues 42

# Full flow (GitHub + ADO) for a milestone
claire dispatch --workflow fivepoints.tfone.full --milestone "Sprint 12"
```

---

## Adapters

| Class | Description |
|-------|-------------|
| `FivepointsGhAdapter` | GitHub adapter — wraps `GhProjectAdapter` with fivepoints-specific label logic |
| `FivepointsOsascriptTerminalAdapter` | macOS terminal adapter — spawns analyst/dev/tester sessions via osascript |
| `FivepointsAdoAdapter` | Azure DevOps adapter — syncs work items (requires `ADO_TOKEN`, `ADO_ORG`, `ADO_PROJECT`) |

---

## Required Environment Variables

| Variable | Required by | Description |
|----------|-------------|-------------|
| `GITHUB_TOKEN` | All flows | GitHub API access |
| `ADO_TOKEN` | `tfone.full` only | Azure DevOps personal access token |
| `ADO_ORG` | `tfone.full` only | ADO organization name (e.g. `fivepoints`) |
| `ADO_PROJECT` | `tfone.full` only | ADO project name (e.g. `TF-One`) |

---

## Workflow Labels

The fivepoints workflow uses GitHub labels to track stage transitions:

| Label | Meaning |
|-------|---------|
| `claire:analyst-done` | Analyst session completed; dev can start |
| `claire:dev-done` | Dev PR merged; tester can start |
| `claire:tester-done` | Tester session completed; issue resolved |
