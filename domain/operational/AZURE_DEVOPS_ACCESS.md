---
domain: fivepoints
category: operational
name: AZURE_DEVOPS_ACCESS
title: "Five Points — Azure DevOps Repo Access"
keywords: [five-points, azure-devops, ado-api, git-remote, pat, authentication, rest-api, repo-access, "persona:fivepoints-dev"]
updated: 2026-03-25
---

# Five Points — Azure DevOps Repo Access

---

## Connection Details

| Field | Value |
|-------|-------|
| Organization | `FivePointsTechnology` |
| Project | `TFIOne` |
| Repository | `TFIOneGit` |
| Base URL | `https://dev.azure.com/FivePointsTechnology/TFIOne` |
| API version | `7.1` |

Local clone: `/Users/andreperez/TFIOneGit`

---

## Authentication

Azure DevOps uses HTTP Basic Auth with an empty username and a Personal Access Token (PAT) as password.

The PAT is embedded in the git remote URL of the local clone:

```
https://andre.perez:<PAT>@dev.azure.com/FivePointsTechnology/TFIOne/_git/TFIOneGit
```

No additional configuration needed for `andre.perez` on this machine.

---

## Connecting — Step by Step

**Step 1 — Extract the PAT from the git remote URL**

```bash
cd /Users/andreperez/TFIOneGit
PAT=$(git remote get-url origin | sed -n 's|https://[^:]*:\([^@]*\)@.*dev\.azure\.com.*|\1|p')
```

**Step 2 — Build the Basic Auth header**

```bash
AUTH=$(echo -n ":${PAT}" | base64)
```

**Step 3 — Call the REST API**

```bash
curl -s \
  -H "Authorization: Basic ${AUTH}" \
  -H "Content-Type: application/json" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/<endpoint>?api-version=7.1"
```

### One-liner

```bash
cd /Users/andreperez/TFIOneGit && \
PAT=$(git remote get-url origin | sed -n 's|https://[^:]*:\([^@]*\)@.*dev\.azure\.com.*|\1|p') && \
AUTH=$(echo -n ":${PAT}" | base64) && \
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/<endpoint>?api-version=7.1"
```

---

## Common API Endpoints

### List files in a directory

```bash
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/items?scopePath=/&recursionLevel=OneLevel&versionDescriptor.version=main&versionDescriptor.versionType=branch&api-version=7.1"
```

| Parameter | Description |
|-----------|-------------|
| `scopePath` | Directory path (e.g. `/`, `/com.tfione.api`) |
| `recursionLevel` | `None`, `OneLevel`, `Full` |
| `versionDescriptor.version` | Branch name (e.g. `feature/10399-education-gaps`) |
| `versionDescriptor.versionType` | `branch`, `tag`, or `commit` |

### Read a specific file

```bash
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/items?path=/com.tfione.api/appsettings.Development.json&versionDescriptor.version=main&versionDescriptor.versionType=branch&api-version=7.1"
```

### List branches

```bash
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/refs?filter=heads&api-version=7.1"
```

### List pull requests

```bash
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/pullrequests?searchCriteria.status=active&api-version=7.1"
```

---

## PAT Management

See `30_universe/domains/fivepoints/operational/TESTING.md` → `## Azure DevOps PAT` for the 3 ways to configure the PAT (git remote URL, claire config, env var).

PAT extraction logic: `30_universe/plugins/fivepoints/domain/scripts/ado_common.sh` — function `ado_init`.

---

## PAT Scopes and Limitations

### Current PAT — Read-Only Scope

The PAT embedded in the git remote URL has the following scopes:

| Scope | Access | Notes |
|-------|--------|-------|
| Code (Git) | Read + Write | Required for `git push` / PR creation |
| Work Items | **Read only** | Cannot create, update, or transition tasks |
| Pull Requests | Read + Write | Can create/comment on PRs |
| Build | Read | Can read pipeline status |

### Impact on Code Gen Workflow

Because work item scope is **read-only**, Claire cannot update ADO task state automatically.

When a Code Gen task is complete, the following steps require **manual action in ADO**:

1. Open the ADO board: `https://dev.azure.com/FivePointsTechnology/TFIOne/_boards/board/t/TFIOne Team/Stories`
2. Locate the PBI (e.g., "Adoptive Placement History — #13644")
3. Open the child task
4. Drag it from `To Do` → `In Progress` → `Done`

> **Cannot automate:** `PATCH /_apis/wit/workitems/{id}` requires `Work Items: Read & Write` scope.
> The current PAT was intentionally issued read-only for security.

### If Write Access Is Needed

To request a PAT with work item write scope:
1. Contact the Five Points team to issue a new token with `Work Items: Read & Write`
2. Update the git remote URL: `git remote set-url origin https://andre.perez:<NEW_PAT>@dev.azure.com/...`
3. Update `claire config` if PAT is stored there separately
