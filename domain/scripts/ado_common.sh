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
