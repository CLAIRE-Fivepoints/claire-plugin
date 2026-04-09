---
domain: five_points
category: operational
name: ADO_PAT_GUIDE
title: "FivePoints — ADO PAT Guide (read vs write)"
keywords: [five-points, ado, azure-devops, PAT, AZURE_DEVOPS_PAT, AZURE_DEVOPS_DEV_PAT, AZURE_DEVOPS_WRITE_PAT, token, credential, git-push, 401, scope]
updated: 2026-04-08
pr: "#18"
---

# FivePoints — ADO PAT Guide

> **L4 fix:** During issue #146 (2026-04-08), a session burned ~2h before discovering
> that a separate write-scoped PAT is required for `git push` and PR attachment uploads.
> This document defines both PATs so the next session doesn't repeat that.

---

## Two PATs, Two Scopes

| Variable | Scope | Used for |
|----------|-------|----------|
| `AZURE_DEVOPS_PAT` | `code:read` (read-only) | PR queries, build logs, comments, `pr-status`, `pr-comments`, `build-log`, `wait`, `ado-watch` |
| `AZURE_DEVOPS_DEV_PAT` | `code:read` + `code:write` | `git push`, PR creation, PR attachment upload |

> **Alias:** `AZURE_DEVOPS_WRITE_PAT` is the preferred name in new code.
> `AZURE_DEVOPS_DEV_PAT` is the legacy name used in older sessions.
> Both refer to the same write-capable token. `ado_common.sh` checks both:
> `AZURE_DEVOPS_WRITE_PAT` → `AZURE_DEVOPS_DEV_PAT` → `AZURE_DEVOPS_PAT` (fallback).

---

## Where to Store

Both PATs live in `~/.config/claire/.env`:

```bash
# ~/.config/claire/.env
AZURE_DEVOPS_PAT=<read-only-pat>          # PR queries, comments, watch
AZURE_DEVOPS_DEV_PAT=<read-write-pat>     # git push, PR create, attachment upload
```

> **Note:** `AZURE_DEVOPS_DEV_PAT` is named for the developer role — it is André's
> personal write PAT, not a service account token. A dedicated `MYCLAIRE_ADO_PAT`
> (service account) is planned in claire issue #2100.

---

## Scope Requirements by Operation

| Operation | Required scope | Which PAT |
|-----------|---------------|-----------|
| `git push ado feature/...` | `code:write` | `AZURE_DEVOPS_DEV_PAT` |
| `gh pr create` (ADO REST) | `code:write` | `AZURE_DEVOPS_DEV_PAT` |
| Upload attachment to PR thread | `code:write` | `AZURE_DEVOPS_DEV_PAT` |
| Read PR status, comments, votes | `code:read` | `AZURE_DEVOPS_PAT` |
| Fetch build logs | `build:read` | `AZURE_DEVOPS_PAT` |
| `claire fivepoints ado-watch` | `code:read` | `AZURE_DEVOPS_PAT` |
| `claire fivepoints ado-push` | `code:read` + `code:write` | Both (handled automatically) |

---

## Symptom: Wrong PAT Used

### `git push` returns HTTP 401

```
fatal: could not read Password for 'https://dev.azure.com': No such device or address
# OR:
error: The requested URL returned error: 401 Unauthorized
```

**Cause:** `git remote` URL contains an expired or read-only PAT.

**Fix:**
```bash
# Never push via embedded remote URL — always inject PAT via header:
git -c "http.extraHeader=Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_DEV_PAT" | base64)" \
    push https://dev.azure.com/FivePointsTechnology/TFIOne/_git/TFIOneGit \
    feature/XXXXX-your-branch:refs/heads/feature/XXXXX-your-branch

# Or use the plugin (handles PAT injection automatically):
claire fivepoints rebase-no-force --branch feature/XXXXX-your-branch --target dev
claire fivepoints ado-push --issue N --branch feature/XXXXX-your-branch
```

### Stale PAT embedded in `git remote ado` URL

```bash
# Detect: does the remote URL contain a PAT?
git remote get-url ado | grep -q '@dev.azure.com' && echo "PAT embedded — may be stale"

# Fix: strip it and let the plugin inject the current PAT at push time
git remote set-url ado "https://dev.azure.com/FivePointsTechnology/TFIOne/_git/TFIOneGit"
```

The plugin commands (`ado-push`, `rebase-no-force`, `land`) always update the ado remote
URL to use the current PAT value — so embedded stale credentials are overwritten on next use.

---

## Session-Start PAT Verification

If you're starting a "finish existing PR" session, verify both PATs are available before
doing any work:

```bash
# Check read PAT
curl -s -u ":${AZURE_DEVOPS_PAT}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories?api-version=7.1" \
  | jq -r '.value | length' | grep -q '^[0-9]' \
  && echo "✅ AZURE_DEVOPS_PAT valid" || echo "❌ AZURE_DEVOPS_PAT invalid or missing"

# Check write PAT (try a harmless API call with write-scoped token)
_WRITE_PAT="${AZURE_DEVOPS_DEV_PAT:-${AZURE_DEVOPS_WRITE_PAT:-}}"
if [[ -n "$_WRITE_PAT" ]]; then
    curl -s -u ":${_WRITE_PAT}" \
      "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories?api-version=7.1" \
      | jq -r '.value | length' | grep -q '^[0-9]' \
      && echo "✅ AZURE_DEVOPS_DEV_PAT valid" || echo "❌ AZURE_DEVOPS_DEV_PAT invalid or missing"
else
    echo "⚠️  AZURE_DEVOPS_DEV_PAT not set — git push will fail"
fi
```

> **L12 (planned):** A `claire fivepoints pat-check` command will do this automatically
> at session start. Until then, run the commands above manually.

---

## How `ado_common.sh` Resolves PATs

Priority chain (first found wins):

```
1. AZURE_DEVOPS_WRITE_PAT env var
2. AZURE_DEVOPS_DEV_PAT env var
3. ~/.config/claire/clients/{client}/config.yaml → ado.pat
4. ~/.config/claire/.env → AZURE_DEVOPS_WRITE_PAT, AZURE_DEVOPS_DEV_PAT, AZURE_DEVOPS_PAT
5. Git remote URL (embedded PAT — may be stale)
```

For **read-only** operations (API calls), the lowest-priority `AZURE_DEVOPS_PAT` is sufficient.
For **write** operations (`git push`, PR create), you need step 1 or 2.

---

## Creating or Rotating PATs

1. Go to: https://dev.azure.com/FivePointsTechnology → User Settings → Personal Access Tokens
2. Create two tokens:
   - **claire-read** — scope: `Code: Read` → assign to `AZURE_DEVOPS_PAT`
   - **claire-write** — scope: `Code: Read & Write` → assign to `AZURE_DEVOPS_DEV_PAT`
3. Store in `~/.config/claire/.env`
4. Rotate annually or when a session reports 401

---

## Related

- `claire domain read claire operational TOKEN_ROLE_MAPPING` — GitHub token mapping (separate from ADO)
- `claire domain read fivepoints operational NO_FORCE_PUSH_STRATEGY` — push strategy when ForcePush is denied
- `claire fivepoints ado-push --agent-help` — automated ADO push workflow
- Issue #146 — incident where missing write PAT was discovered mid-session after 2h of work
