# Adopting the model registry check

> **`OWNER` placeholder:** this repo's GitHub owner has not been decided yet.
> Every `OWNER` below (and in `action.yml`) is a literal placeholder — replace
> it with the real GitHub owner/org before referencing this action from any
> consumer repo. Referencing `OWNER/model-registry` as written will not work.

Add `.github/workflows/model-registry.yml` to your repo:

```yaml
name: Model Registry
on: pull_request

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the scan needs both sides of the diff
      - uses: OWNER/model-registry@v1
        with:
          block-unknown: 'false'   # start in warn mode
```

> **Trigger this on `pull_request` only.** The scan step (and the private-repo
> fallback below) reads `github.event.pull_request.base.sha` and `.head.sha`.
> On any other event type (e.g. `push`) those are empty, and `git diff "" ""`
> fails loudly. That's safe — it errors instead of silently scanning nothing —
> but wire this workflow to `pull_request` as shown, not to `push`.

## Rollout order

1. Land it with `block-unknown: 'false'`. Unregistered models warn; deprecated and
   banned models block immediately.
2. Watch a week of PRs. Every legitimate warning means a model missing from the
   registry — add it.
3. Flip to `block-unknown: 'true'` once the warnings stop.

## What the scan's exit code means

| Exit | Meaning |
|---|---|
| 0 | The diff was scanned. Nothing blocking. Warnings may still be printed on stderr. |
| 1 | A policy finding: the PR adds a `deprecated` or `banned` model (or an unknown one under `block-unknown: 'true'`). |
| 2 | The check did not run: stdin was not a unified diff, or `models.yaml` could not be loaded. **Not** a policy finding — fix the invocation. |

A broken invocation must never be reported as "this PR introduces a banned model", so 2
is deliberately distinct from 1. `model-registry drift` uses the same contract.

## Silencing a false positive

Append `# model-registry: ignore <reason>` to the line. Use it for strings that
merely look like model IDs, not to skip an approval.

That comment and the built-in exclusion list (`*.ipynb`, `accuracy/`, `docs/`,
`CHANGELOG*`, `*.lock`) are the only escape hatches. There is no per-repo config file in
v1; `block-unknown` is the only per-repo knob.

## If this repo is private

The action above requires `actions/checkout` to be able to read this repo, which
only works once it is public. If this repo stays private, replace the `uses:`
step with an explicit checkout, install, and `--registry` flag — mirroring
exactly what `action.yml` does for the public case:

```yaml
      - uses: actions/checkout@v4
        with:
          repository: OWNER/model-registry
          token: ${{ secrets.REGISTRY_TOKEN }}
          path: .model-registry
      - run: pip install ./.model-registry
      - run: |
          git diff "${{ github.event.pull_request.base.sha }}" "${{ github.event.pull_request.head.sha }}" \
            | model-registry scan --registry .model-registry/models.yaml
```

Do not `pip install` straight from a `git+https://...` URL and then run
`model-registry scan` with no `--registry` flag. `pip install` only installs
the `model_registry` Python package — `models.yaml` lives at the repo root,
is not packaged as package data, and never ends up on disk. With no
`--registry`, the CLI falls back to a path inside `site-packages` where
`models.yaml` does not exist, so the check fails with `registry invalid:
registry file not found: ...` on every single PR, without ever scanning a
line. Always give it an actual checkout to read `models.yaml` from, as above.
