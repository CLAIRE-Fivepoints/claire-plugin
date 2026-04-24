# TFI One — PR Body Checklist

This checklist is the plugin-side substitute for the ADO
`.azuredevops/pull_request_template.md` originally proposed in issue #119.
Per the #119 decision, no files are committed to the ADO-tracked repo —
instead, the dev agent embeds this block verbatim in
`gh pr create --body "…"` at step `[5/11]` of `CHECKLIST_DEV_PIPELINE`.

Copy everything inside the fenced block below into the PR body, filling
each `[ ]` as it passes.

```markdown
## PR Checklist (plugin-rendered — issue #119)

- [ ] Follows patterns in `docs/27-FIVEPOINTS-CODE-PATTERNS.md`
- [ ] Uses `rqProvider.GetRestrictedQuery<T>()` for entity queries
- [ ] Uses `labelToken` / `labelDefault` on Tfio* components
- [ ] Validators connected via the `fluentValidationResolver` pipeline
- [ ] All tests pass (`dotnet build -c Gate`, `dotnet test`, `npm run lint`, `npm run build-gate`)
- [ ] Pre-commit + pre-push hooks installed for this clone (`claire fivepoints install-hooks`)
```

## Why this lives in the plugin and not in TFIOneGit

The original issue asked for `.azuredevops/pull_request_template.md`, but
shipping it would have required a commit against the ADO-tracked TFIOneGit
repository — which issue #119 explicitly rules out. Keeping the checklist
in the plugin has three advantages:

1. **No ADO-origin changes.** No `.azuredevops/` diff to review, no
   `master` commit, no ADO build trigger.
2. **Evolves with the plugin.** Updating the checklist only needs a PR to
   `CLAIRE-Fivepoints/claire-plugin`, which Steven Reviewer gates
   automatically — no coordination with the ADO release train.
3. **Agent-driven enforcement.** `CHECKLIST_DEV_PIPELINE` step `[5/11]`
   tells the dev agent to embed this block on every PR; Steven Reviewer
   rejects PRs that open without it.

## Related

- `claire domain read fivepoints operational GIT_HOOKS` — the pre-commit /
  pre-push gates that back up this checklist with automation.
- `claire domain read fivepoints operational CHECKLIST_DEV_PIPELINE` —
  step `[5/11]` is where this template is consumed.
