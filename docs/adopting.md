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

## Rollout order

1. Land it with `block-unknown: 'false'`. Unregistered models warn; deprecated and
   banned models block immediately.
2. Watch a week of PRs. Every legitimate warning means a model missing from the
   registry — add it.
3. Flip to `block-unknown: 'true'` once the warnings stop.

## Silencing a false positive

Append `# model-registry: ignore <reason>` to the line. Use it for strings that
merely look like model IDs, not to skip an approval.

## If this repo is private

The action above requires `actions/checkout` to be able to read this repo, which
only works once it is public. If this repo stays private, replace the `uses:`
step with a direct install:

```yaml
      - run: pip install "git+https://x-access-token:${{ secrets.REGISTRY_TOKEN }}@github.com/OWNER/model-registry.git"
      - run: git diff ${{ github.event.pull_request.base.sha }} ${{ github.event.pull_request.head.sha }} | model-registry scan
```
