#!/usr/bin/env bash
# Shared Azure DevOps API helpers for fivepoints plugin
# Sources PAT from env, client config, or git remote; provides authenticated curl wrapper

# Globals (set by ado_init)
_ADO_ORG=""
_ADO_PROJECT=""
_ADO_REPO=""
_ADO_BASE_URL=""
_ADO_AUTH_HEADER=""
_ADO_LOCAL_PATH=""
_ADO_DEV_BRANCH=""

# Detect the active client name.
# Priority: CLAIRE_CLIENT env var > match ado.org from git remote against client configs.
# Outputs the client name (e.g. "fivepoints") to stdout, or returns 1 if not found.
_ado_detect_client() {
    if [[ -n "${CLAIRE_CLIENT:-}" ]]; then
        echo "$CLAIRE_CLIENT"
        return 0
    fi

    local remote_url
    remote_url=$(git remote get-url origin 2>/dev/null || echo "")

    local remote_org=""
    if [[ "$remote_url" =~ dev\.azure\.com/([^/]+)/ ]]; then
        remote_org="${BASH_REMATCH[1]}"
    elif [[ "$remote_url" =~ ([^/.]+)\.visualstudio\.com/ ]]; then
        remote_org="${BASH_REMATCH[1]}"
    fi

    if [[ -z "$remote_org" ]]; then
        return 1
    fi

    local clients_dir="$HOME/.config/claire/clients"
    [[ -d "$clients_dir" ]] || return 1

    for config in "$clients_dir"/*/config.yaml; do
        [[ -f "$config" ]] || continue
        local config_org
        config_org=$(yq eval '.ado.org // ""' "$config" 2>/dev/null)
        if [[ "$config_org" == "$remote_org" ]]; then
            basename "$(dirname "$config")"
            return 0
        fi
    done

    return 1
}

# Read a value from a client config file using yq.
# Usage: _ado_client_config_get <client> <yq_path>
# Example: _ado_client_config_get fivepoints .ado.pat
_ado_client_config_get() {
    local client="$1"
    local yq_path="$2"
    local config="$HOME/.config/claire/clients/${client}/config.yaml"
    [[ -f "$config" ]] || return 1
    yq eval "${yq_path} // \"\"" "$config" 2>/dev/null
}

# Read a KEY=VALUE pair from a shell-sourceable .env file.
# Tolerates an optional `export ` prefix and strips matched surrounding
# single/double quotes, matching what `source <file>` would produce.
# Usage: _ado_env_get <file> <key>
# Prints the value on stdout (empty if not found).
_ado_env_get() {
    local file="$1"
    local key="$2"
    [[ -f "$file" ]] || return 0
    local line
    line=$(grep -E "^(export[[:space:]]+)?${key}=" "$file" 2>/dev/null | head -1 || true)
    [[ -z "$line" ]] && return 0
    local value="${line#*=}"
    # Trim leading/trailing whitespace, then strip matched surrounding quotes
    # (mirrors _read_env_file in ado_client.py so both parsers share one contract).
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" =~ ^\"(.*)\"$ ]] || [[ "$value" =~ ^\'(.*)\'$ ]]; then
        value="${BASH_REMATCH[1]}"
    fi
    printf '%s\n' "$value"
}

# Initialize Azure DevOps connection.
# PAT priority:
#   0. AZURE_DEVOPS_WRITE_PAT env var (write access, for ado-push)
#   1. AZURE_DEVOPS_DEV_PAT env var
#   2. ~/.config/claire/clients/{client}/config.yaml (ado.pat)
#   3. ~/.config/claire/.env (AZURE_DEVOPS_WRITE_PAT, AZURE_DEVOPS_DEV_PAT, AZURE_DEVOPS_PAT)
#   4. Git remote embedded PAT
# Org/Project/Repo: parsed from git remote URL, then client config as fallback.
ado_init() {
    if [[ -n "$_ADO_ORG" ]]; then
        return 0
    fi

    local remote_url
    remote_url=$(git remote get-url origin 2>/dev/null || echo "")

    # Detect client for config-based lookups
    local client
    client=$(_ado_detect_client 2>/dev/null || echo "")

    # --- PAT discovery ---
    local effective_pat=""
    local config_env="$HOME/.config/claire/.env"

    # 0. AZURE_DEVOPS_WRITE_PAT env var (write access, set by --ask-pat or pre-exported)
    if [[ -n "${AZURE_DEVOPS_WRITE_PAT:-}" ]]; then
        effective_pat="$AZURE_DEVOPS_WRITE_PAT"
    fi

    # 0b. AZURE_DEVOPS_WRITE_PAT from ~/.config/claire/.env
    if [[ -z "$effective_pat" && -f "$config_env" ]]; then
        local write_pat
        write_pat=$(_ado_env_get "$config_env" AZURE_DEVOPS_WRITE_PAT)
        if [[ -n "$write_pat" ]]; then
            effective_pat="$write_pat"
            export AZURE_DEVOPS_WRITE_PAT="$write_pat"
        fi
    fi

    # 1. AZURE_DEVOPS_DEV_PAT env var
    if [[ -z "$effective_pat" && -n "${AZURE_DEVOPS_DEV_PAT:-}" ]]; then
        effective_pat="$AZURE_DEVOPS_DEV_PAT"
    fi

    # 2. Client config: ado.pat
    if [[ -z "$effective_pat" && -n "$client" ]]; then
        local client_pat
        client_pat=$(_ado_client_config_get "$client" '.ado.pat')
        if [[ -n "$client_pat" ]]; then
            effective_pat="$client_pat"
        fi
    fi

    # 3. ~/.config/claire/.env (AZURE_DEVOPS_DEV_PAT, then AZURE_DEVOPS_PAT)
    if [[ -z "$effective_pat" && -f "$config_env" ]]; then
        local dev_pat
        dev_pat=$(_ado_env_get "$config_env" AZURE_DEVOPS_DEV_PAT)
        if [[ -n "$dev_pat" ]]; then
            effective_pat="$dev_pat"
            export AZURE_DEVOPS_DEV_PAT="$dev_pat"
        fi
    fi

    if [[ -z "$effective_pat" && -n "${AZURE_DEVOPS_PAT:-}" ]]; then
        effective_pat="$AZURE_DEVOPS_PAT"
    fi

    if [[ -z "$effective_pat" && -f "$config_env" ]]; then
        local config_pat
        config_pat=$(_ado_env_get "$config_env" AZURE_DEVOPS_PAT)
        if [[ -n "$config_pat" ]]; then
            effective_pat="$config_pat"
            export AZURE_DEVOPS_PAT="$config_pat"
        fi
    fi

    # 4. Git remote embedded PAT
    if [[ -z "$effective_pat" && -n "$remote_url" ]]; then
        local embedded_pat
        embedded_pat=$(echo "$remote_url" | sed -n 's|https://[^:]*:\([^@]*\)@.*\(dev\.azure\.com\|visualstudio\.com\).*|\1|p')
        if [[ -n "$embedded_pat" ]]; then
            effective_pat="$embedded_pat"
        fi
    fi

    if [[ -z "$effective_pat" ]]; then
        echo "ERROR: No Azure DevOps PAT found" >&2
        echo "Set AZURE_DEVOPS_DEV_PAT in env, or add ado.pat to ~/.config/claire/clients/{client}/config.yaml" >&2
        return 1
    fi

    export AZURE_DEVOPS_PAT="$effective_pat"

    # --- Org/Project/Repo discovery ---
    local parsed=false

    if [[ -n "$remote_url" ]]; then
        if [[ "$remote_url" =~ dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+) ]]; then
            _ADO_ORG="${BASH_REMATCH[1]}"
            _ADO_PROJECT="${BASH_REMATCH[2]}"
            _ADO_REPO="${BASH_REMATCH[3]}"
            parsed=true
        elif [[ "$remote_url" =~ ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/([^/]+) ]]; then
            _ADO_ORG="${BASH_REMATCH[1]}"
            _ADO_PROJECT="${BASH_REMATCH[2]}"
            _ADO_REPO="${BASH_REMATCH[3]}"
            parsed=true
        elif [[ "$remote_url" =~ ([^/.]+)\.visualstudio\.com/([^/]+)/_git/([^/]+) ]]; then
            _ADO_ORG="${BASH_REMATCH[1]}"
            _ADO_PROJECT="${BASH_REMATCH[2]}"
            _ADO_REPO="${BASH_REMATCH[3]}"
            parsed=true
        fi
    fi

    # Fallback: read org/project/repo from client config
    if [[ "$parsed" == false && -n "$client" ]]; then
        local cfg_org cfg_project cfg_repo
        cfg_org=$(_ado_client_config_get "$client" '.ado.org')
        cfg_project=$(_ado_client_config_get "$client" '.ado.project')
        cfg_repo=$(_ado_client_config_get "$client" '.ado.repo')
        if [[ -n "$cfg_org" && -n "$cfg_project" && -n "$cfg_repo" ]]; then
            _ADO_ORG="$cfg_org"
            _ADO_PROJECT="$cfg_project"
            _ADO_REPO="$cfg_repo"
            parsed=true
        fi
    fi

    if [[ "$parsed" == false ]]; then
        echo "ERROR: Could not determine Azure DevOps org/project/repo" >&2
        echo "Expected git remote: https://dev.azure.com/{org}/{project}/_git/{repo}" >&2
        echo "Or set CLAIRE_CLIENT and add ado.org/project/repo to client config" >&2
        return 1
    fi

    _ADO_REPO="${_ADO_REPO%.git}"
    _ADO_BASE_URL="https://dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_apis"

    local encoded
    encoded=$(echo -n ":${AZURE_DEVOPS_PAT}" | base64)
    _ADO_AUTH_HEADER="Authorization: Basic ${encoded}"

    # Populate local_path and dev_branch from client config if available
    if [[ -n "$client" ]]; then
        _ADO_LOCAL_PATH=$(_ado_client_config_get "$client" '.ado.local_path')
        _ADO_DEV_BRANCH=$(_ado_client_config_get "$client" '.ado.dev_branch')
    fi

    return 0
}

# GET request to Azure DevOps API
# Usage: ado_get "/git/repositories/{repo}/pullrequests/{id}?api-version=7.1"
ado_get() {
    local endpoint="$1"
    local url

    if [[ "$endpoint" == https://* ]]; then
        url="$endpoint"
    else
        url="${_ADO_BASE_URL}${endpoint}"
    fi

    curl -s \
        -H "$_ADO_AUTH_HEADER" \
        -H "Content-Type: application/json; charset=utf-8" \
        "$url"
}

# POST request to Azure DevOps API
# Usage: ado_post "/endpoint" '{"key": "value"}'
ado_post() {
    local endpoint="$1"
    local data="$2"
    local url

    if [[ "$endpoint" == https://* ]]; then
        url="$endpoint"
    else
        url="${_ADO_BASE_URL}${endpoint}"
    fi

    curl -s \
        -X POST \
        -H "$_ADO_AUTH_HEADER" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "$data" \
        "$url"
}

# PUT request to Azure DevOps API
# Usage: ado_put "/endpoint" '{"key": "value"}'
ado_put() {
    local endpoint="$1"
    local data="$2"
    local url

    if [[ "$endpoint" == https://* ]]; then
        url="$endpoint"
    else
        url="${_ADO_BASE_URL}${endpoint}"
    fi

    curl -s \
        -X PUT \
        -H "$_ADO_AUTH_HEADER" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "$data" \
        "$url"
}

# Get the current authenticated user's Azure DevOps identity ID
# Returns the UUID string, or empty on failure
ado_get_current_user_id() {
    local response
    response=$(curl -s \
        -H "$_ADO_AUTH_HEADER" \
        "https://dev.azure.com/${_ADO_ORG}/_apis/connectionData")
    echo "$response" | jq -r '.authenticatedUser.id // empty'
}

# Strip non-ASCII characters from text (Azure DevOps rejects emoji)
ado_sanitize_text() {
    local text="$1"
    # Remove non-ASCII characters
    echo "$text" | LC_ALL=C sed 's/[^[:print:][:space:]]//g'
}

# Print connection info
ado_print_info() {
    echo "Org:     ${_ADO_ORG}"
    echo "Project: ${_ADO_PROJECT}"
    echo "Repo:    ${_ADO_REPO}"
}

# Resolve the GitHub repo for proof-gate operations.
# Single source of truth for both ado-push and ado-transition so they always
# verify proof against the same issue tracker (PR #78 review point 1).
#
# Priority:
#   1. CLAIRE_WAIT_REPO env var
#   2. `gh repo view` autodetect from current directory
#   3. caller-supplied default (e.g. "CLAIRE-Fivepoints/fivepoints-test")
#
# Returns 0 + prints repo on stdout, or 1 if no repo can be resolved.
resolve_gh_repo() {
    local default_repo="${1:-}"
    if [[ -n "${CLAIRE_WAIT_REPO:-}" ]]; then
        printf '%s\n' "$CLAIRE_WAIT_REPO"
        return 0
    fi
    local detected
    detected=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || echo "")
    if [[ -n "$detected" ]]; then
        printf '%s\n' "$detected"
        return 0
    fi
    if [[ -n "$default_repo" ]]; then
        printf '%s\n' "$default_repo"
        return 0
    fi
    return 1
}

# Verify dev-pipeline proof gates: MP4 ([8/11]) and FDS Verification ([9/11])
# posted as comments on the GitHub issue. Reads issue comments via gh CLI.
#
# Usage: check_proof_gate <issue_number> <github_repo>
#   issue_number: e.g. 123
#   github_repo:  e.g. CLAIRE-Fivepoints/claire-plugin
#
# Returns 0 if both gates pass, 1 otherwise. Rejection text names the
# specific skipped checklist step (per issue #74) and references the
# Discord Ping Protocol so the dev does not invent a static-analysis fallback.
#
# Matchers:
#   MP4: line starting with `MP4:` / `Proof:` / `Recording:` / `Video:`
#        (case-insensitive, multiline) followed by content ending in `.mp4`.
#        Tighter than `contains(".mp4")` to avoid false positives from
#        discussion comments that mention `.mp4` in prose (PR #78 review point 2).
#   FDS: comment whose body STARTS with `**FDS Verification (screenshot + AI)**`
#        (per the dev checklist's documented heredoc format).
#
# Both gates are evaluated in a single `gh issue view` call (PR #78 review point 3).
check_proof_gate() {
    local issue_number="$1"
    local gh_repo="$2"

    if [[ -z "$issue_number" || -z "$gh_repo" ]]; then
        echo "ERROR: check_proof_gate requires <issue_number> <github_repo>" >&2
        return 2
    fi

    local result_json
    result_json=$(gh issue view "$issue_number" --repo "$gh_repo" --json comments \
        --jq '{
            mp4: any(.comments[].body; test("(?im)^(MP4|Proof|Recording|Video)[: ].*\\.mp4")),
            fds: any(.comments[].body; startswith("**FDS Verification (screenshot + AI)**"))
        }' \
        2>/dev/null || echo '{"mp4":false,"fds":false}')

    local mp4_found fds_found
    mp4_found=$(jq -r '.mp4' <<<"$result_json" 2>/dev/null || echo "false")
    fds_found=$(jq -r '.fds' <<<"$result_json" 2>/dev/null || echo "false")

    if [[ "$mp4_found" == "true" && "$fds_found" == "true" ]]; then
        echo "✅ Proof gate: MP4 ([8/11]) + FDS Verification ([9/11]) both posted on issue #${issue_number}"
        return 0
    fi

    {
        echo ""
        echo "❌ Proof gate failed for issue #${issue_number} (${gh_repo}):"
        if [[ "$mp4_found" != "true" ]]; then
            echo "   ❌ [8/11] MP4 missing: no 'MP4 URL/path' line found on issue #${issue_number}."
            echo "      Record an MP4 with Playwright (claire domain read video_proof technical PLAYWRIGHT_PATTERNS),"
            echo "      then post the path with one of the recognised prefixes (MP4:/Proof:/Recording:/Video:):"
            echo "        gh issue comment ${issue_number} --body 'MP4: /path/to/proof.mp4'"
        fi
        if [[ "$fds_found" != "true" ]]; then
            echo "   ❌ [9/11] FDS Verification missing: no '**FDS Verification (screenshot + AI)**' comment on issue #${issue_number}."
            echo "      Capture a final-state screenshot, AI-verify it against the FDS labels, then post:"
            echo "        gh issue comment ${issue_number} --body '**FDS Verification (screenshot + AI)**'..."
        fi
        echo ""
        echo "   These are HARD STOPs in the dev checklist. Static code analysis is NOT a substitute."
        echo "   If test-env cannot be brought up, escalate via the Discord Ping Protocol"
        echo "   (claire discord send + GitHub comment + claire wait) — do NOT skip these steps."
    } >&2

    return 1
}

# Verify the feature branch is fast-forward with ADO's target-branch tip.
#
# The GitHub mirror and ADO (TFIOneGit) have divergent histories — same
# content, different SHAs — caused by past "start fresh" resets. A dev who
# branches from github/dev and pushes to ADO without checking ends up with
# a PR containing dozens of unrelated commits (incident on issue #71: 65
# commits of divergent mirror history mixed with a 2-commit feature).
# `git push --force-with-lease` does NOT catch this — it only guards against
# overwriting someone else's push to the SAME ref.
#
# Invariant enforced: merge-base(branch, origin/target) == origin/target tip.
# When true, the branch contains only the dev's intended commits on top of
# ADO's target tip.
#
# Usage: verify_branch_synced_with_ado_dev <branch> <target_branch> <repo_path>
#   branch:        feature branch to push (e.g. feature/18839-client-face-sheet)
#   target_branch: ADO target (e.g. dev)
#   repo_path:     local clone of the ADO-origin repo (e.g. ~/TFIOneGit)
#
# Returns 0 when fast-forward, 1 when divergent, 2 on missing args or git error.
# Prints the resolution options (cherry-pick onto fresh branch, or reset +
# cherry-pick) on failure — the dev never has to guess how to recover.
verify_branch_synced_with_ado_dev() {
    local branch="$1"
    local target="$2"
    local repo_path="$3"

    if [[ -z "$branch" || -z "$target" || -z "$repo_path" ]]; then
        echo "ERROR: verify_branch_synced_with_ado_dev requires <branch> <target> <repo_path>" >&2
        return 2
    fi

    if [[ ! -d "$repo_path/.git" ]]; then
        echo "ERROR: $repo_path is not a git repository" >&2
        return 2
    fi

    pushd "$repo_path" > /dev/null || return 2

    if ! git rev-parse --verify "$branch" &>/dev/null; then
        echo "ERROR: branch '$branch' does not exist in $repo_path" >&2
        popd > /dev/null || true
        return 2
    fi

    if ! git fetch origin "$target" --quiet 2>/dev/null; then
        echo "ERROR: failed to fetch origin/$target from $repo_path" >&2
        popd > /dev/null || true
        return 2
    fi

    local ado_tip merge_base
    ado_tip=$(git rev-parse "origin/$target")
    # `git merge-base` returns exit=1 for disjoint histories. Without this
    # guard, an empty merge_base would resolve to HEAD in the log command
    # below, hiding the real problem behind a misleading "merge-base" line.
    if ! merge_base=$(git merge-base "$branch" "origin/$target" 2>/dev/null) \
        || [[ -z "$merge_base" ]]; then
        echo "ERROR: no common ancestor between '$branch' and 'origin/$target' (disjoint histories?)" >&2
        popd > /dev/null || true
        return 2
    fi

    if [[ "$merge_base" == "$ado_tip" ]]; then
        echo "✅ Branch is fast-forward with origin/$target (merge-base = ADO $target tip)"
        popd > /dev/null || true
        return 0
    fi

    local ahead behind ado_tip_line merge_base_line
    ahead=$(git rev-list --count "$ado_tip..$branch")
    behind=$(git rev-list --count "$branch..$ado_tip")
    ado_tip_line=$(git log --oneline -1 "origin/$target")
    merge_base_line=$(git log --oneline -1 "$merge_base")

    {
        echo ""
        echo "❌ Branch is not up-to-date with ADO $target."
        echo "    ADO $target tip:    $ado_tip_line"
        echo "    Branch merge-base:  $merge_base_line"
        echo "    Commits ahead:      $ahead   (your feature work + any divergent mirror history)"
        echo "    Commits behind:     $behind   (ADO $target commits your branch doesn't have)"
        echo ""
        echo "    Pushing this branch to ADO will create a chaotic PR with $ahead commits."
        echo ""
        echo "    RESOLVE by either:"
        echo "      (a) Cherry-pick your feature commits onto a fresh branch off ADO $target:"
        echo "          git fetch origin"
        echo "          git checkout -b ${branch}-ado origin/$target"
        echo "          git cherry-pick <your-commit-sha>..."
        echo "          # rerun 5 gates"
        echo "          git push ado ${branch}-ado:refs/heads/${branch} --force-with-lease"
        echo ""
        echo "      (b) Reset your existing branch to ADO $target + cherry-pick (rewrites GitHub PR history):"
        echo "          git fetch origin"
        echo "          git checkout ${branch}"
        echo "          git reset --hard origin/$target"
        echo "          git cherry-pick <your-commit-sha>..."
        echo "          # rerun 5 gates"
        echo "          git push github ${branch} --force-with-lease   # updates GitHub PR"
        echo "          # then rerun claire fivepoints ado-transition"
        echo ""
    } >&2

    popd > /dev/null || true
    return 1
}

# Attempt to auto-rebase a feature branch onto ADO $target, replaying only
# the dev's own commits (not the GitHub mirror's divergent history).
#
# The #71 scenario: branch carries N commits of mirror-only history mixed
# with a handful of real feature commits. A plain `git rebase origin/$target`
# would try to replay all N on ADO, producing spurious conflicts or
# duplicates. Instead we use:
#   git rebase --onto origin/$target  <mirror_base>  $branch
# where mirror_base = merge-base($branch, $mirror_remote/$target). Commits
# between mirror_base and the branch tip are, by construction, the dev's
# own work added after branching from the GitHub mirror — exactly what we
# want to replay onto ADO.
#
# Usage: attempt_auto_rebase_onto_ado <branch> <target> <repo_path> [<mirror_remote>]
#   branch:        feature branch to rebase (e.g. feature/18839-x)
#   target:        ADO target (e.g. dev)
#   repo_path:     local clone of the ADO-origin repo
#   mirror_remote: GitHub mirror remote name (default: github)
#
# Returns:
#   0 on clean rebase (branch now fast-forward with origin/$target)
#   1 on conflict (rebase aborted, branch left in pre-rebase state)
#   2 on setup failure (missing remotes, dirty worktree, unknown branch)
#
# Side effect on success: the branch in repo_path is moved. Caller MUST
# log the action so the dev sees what happened.
attempt_auto_rebase_onto_ado() {
    local branch="$1"
    local target="$2"
    local repo_path="$3"
    local mirror_remote="${4:-github}"

    if [[ -z "$branch" || -z "$target" || -z "$repo_path" ]]; then
        echo "ERROR: attempt_auto_rebase_onto_ado requires <branch> <target> <repo_path> [<mirror_remote>]" >&2
        return 2
    fi

    if [[ ! -d "$repo_path/.git" ]]; then
        echo "ERROR: $repo_path is not a git repository" >&2
        return 2
    fi

    pushd "$repo_path" > /dev/null || return 2

    # Refuse to rebase a dirty worktree — we'd risk losing uncommitted work.
    if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        echo "ERROR: worktree has uncommitted changes — auto-rebase refused" >&2
        echo "       commit or stash before retrying, or pass --no-auto-sync to skip" >&2
        popd > /dev/null || true
        return 2
    fi

    if ! git remote get-url "$mirror_remote" &>/dev/null; then
        echo "ERROR: mirror remote '$mirror_remote' not configured in $repo_path" >&2
        echo "       auto-rebase needs both origin (ADO) and $mirror_remote (GitHub) remotes" >&2
        popd > /dev/null || true
        return 2
    fi

    if ! git rev-parse --verify "$branch" &>/dev/null; then
        echo "ERROR: branch '$branch' does not exist in $repo_path" >&2
        popd > /dev/null || true
        return 2
    fi

    # Fetch both remotes quietly — fail loudly if either is unreachable.
    if ! git fetch origin "$target" --quiet 2>/dev/null; then
        echo "ERROR: failed to fetch origin/$target" >&2
        popd > /dev/null || true
        return 2
    fi
    if ! git fetch "$mirror_remote" "$target" --quiet 2>/dev/null; then
        echo "ERROR: failed to fetch $mirror_remote/$target" >&2
        popd > /dev/null || true
        return 2
    fi

    local mirror_base
    if ! mirror_base=$(git merge-base "$branch" "$mirror_remote/$target" 2>/dev/null) \
        || [[ -z "$mirror_base" ]]; then
        echo "ERROR: could not compute merge-base with $mirror_remote/$target" >&2
        popd > /dev/null || true
        return 2
    fi

    # Save pre-rebase HEAD for rollback signalling.
    local pre_head
    pre_head=$(git rev-parse "$branch")

    # Check out the branch (detached-head-safe) — `git rebase --onto` needs
    # the branch HEAD as the argument, and we want to operate on that branch.
    if ! git checkout -q "$branch" 2>/dev/null; then
        echo "ERROR: could not checkout $branch" >&2
        popd > /dev/null || true
        return 2
    fi

    echo "      auto-rebasing: git rebase --onto origin/$target ${mirror_base:0:7} $branch"

    if git rebase --onto "origin/$target" "$mirror_base" "$branch" 2>&1; then
        local new_head
        new_head=$(git rev-parse HEAD)
        if [[ "$new_head" == "$pre_head" ]]; then
            echo "✅ Auto-rebase: branch already on ADO $target — no commits moved"
        else
            echo "✅ Auto-rebase: branch replayed onto origin/$target"
            echo "      pre-rebase HEAD:  ${pre_head:0:12}"
            echo "      post-rebase HEAD: ${new_head:0:12}"
        fi
        popd > /dev/null || true
        return 0
    fi

    # Rebase failed — abort to leave the branch exactly where it was.
    echo "⚠️  Auto-rebase hit a conflict — aborting to leave the branch untouched"
    git rebase --abort 2>/dev/null || true
    popd > /dev/null || true
    return 1
}
