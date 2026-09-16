# Model Registry — Design

Date: 2026-09-16
Status: approved, pending implementation plan

## Problem

Nesto serves bank clients whose contracts restrict which AI models may process their
data (Canadian residency, or open-weight models we self-host on GCP), while we also
want current frontier models for everything else. Today nothing records which model is
allowed for which client segment.

The observable symptom: seven distinct Gemini model IDs are hardcoded across
`documents-extractor` and `maestro-graphs` (`gemini-2.5-pro`, `gemini-2.5-flash`,
`gemini-3.1-pro-preview`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`,
`gemini-3.5-flash-lite`, `gemini-3.6-flash`). Model choice propagates by copy-paste
from the nearest existing call.

The driving pain is **developers asking "which model can I use here?"**. The
answer currently comes from asking one person. Compliance evidence for client
security reviews is a secondary benefit, not the driver.

## Non-goals

- **Model selection.** Which model is *best* for OCR or embeddings is an evaluation
  question, answered by `documents-extractor/accuracy/reports/` against our own
  bilingual mortgage documents. Public leaderboards (HF/MTEB) are linked as reference
  material only; they are not polled, scraped, or alerted on. Nesto's domain is
  French/English Canadian mortgage paperwork, where leaderboard rank transfers poorly.
- **Upstream release watching.** We do not poll provider APIs for new model launches.
- **Gateway configuration ownership.** The registry does not deploy or configure the
  LiteLLM gateway in v1. The schema is shaped so it could later (see Future).

## Design principles

1. **Answer at the moment of decision.** A registry developers must remember to open
   will rot. The primary consumer is a PR-time check, not a document.
2. **Facts, not verdicts.** Each model records verifiable properties. Eligibility is
   derived from those facts by a policy function, so "why is this approved" is
   answerable from the artifact rather than from PR discussion.
3. **The registry is executed, not published.** Every artifact (README table, CI
   verdict, drift report) is generated from `models.yaml`; none is hand-maintained.

## Architecture

New standalone repo `model-registry`. Standalone because the audit trail (every
approval is a reviewed PR) is the artifact client security reviews ask for, and because
it should not inherit a Python package's release cadence.

```
model-registry/
  models.yaml              # source of truth, hand-edited via PR
  model_registry/
    schema.py              # pydantic models, strict validation
    policy.py              # facts -> tiers derivation
    loader.py              # load + validate + derive
    render.py              # models.yaml -> README table
    scan.py                # find model IDs in source, compare to registry
    drift.py               # gateway /model/info vs registry
    cli.py                 # validate | render | scan | drift
  action.yml               # composite GitHub Action for consumer repos
  tests/
  README.md                # generated table; never hand-edited below marker
```

Stack mirrors `llm-kit`: uv, ruff, mypy strict, pytest, Makefile with `make check`.
`from __future__ import annotations` in every module; absolute imports only.

### Schema

```yaml
- id: gemini-2.5-flash            # canonical ID as called through the gateway
  display_name: Gemini 2.5 Flash
  provider: google                # google | openai | anthropic | community
  hosting: vertex                 # vertex | saas | self-hosted
  region: northamerica-northeast1
  residency: canada               # canada | us | multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]                # ocr | embedding | general | reranking
  status: approved                # approved | trial | deprecated | banned
  approved_on: 2026-09-16
  approval_ref: https://github.com/nesto/model-registry/pull/1
  review_by: 2027-09-16
  notes: DPA covers Montreal region; no training on inference data.
  replacement: null               # required when status == deprecated
  gateway:                        # unused in v1; shaped for the Future section
    model_name: gemini-2.5-flash
    api_base: null
```

### Policy derivation

`policy.py` derives `tiers` from facts. Initial rules:

- `standard` — `status` in {`approved`, `trial`}.
- `bank` — `status == approved` **and** `trains_on_customer_data == false` **and**
  (`residency == canada` **or** (`open_weights == true` **and** `hosting == self-hosted`)).

A model whose recorded facts cannot justify a claimed status fails validation. Tiers are
never written by hand in `models.yaml`; they are computed on load.

The rules encode a contractual position, not a legal one. They live in one function with
the reasoning in comments so they can be corrected in a single reviewed place.

## Components

### 1. Validator (`make validate`)
Loads `models.yaml`, enforces the schema, derives tiers, fails on: unknown fields,
duplicate IDs, `deprecated` without a `replacement`, `review_by` in the past, a
`bank`-serving status the facts do not support. Runs in the registry's own CI.

### 2. README renderer (`make render`)
Regenerates the table in `README.md` between `<!-- BEGIN MODELS -->` markers. CI fails if
the committed README differs from the rendered output, so the browsable view can never
drift from the source.

### 3. PR-time scanner — *the primary consumer*
A composite GitHub Action consumer repos adopt (`documents-extractor` first, then
`maestro-graphs`). On a PR it scans **added lines only** for model-ID-shaped strings and
fails when one is unknown to the registry, `deprecated`, or `banned`.

The scanner is heuristic and this is its main design risk. Mitigations:
- Candidate patterns: `gemini-*`, `gpt-*`, `text-embedding-*`, `claude-*`, plus exact
  matches on any registry ID.
- Default excludes: `*.ipynb`, `accuracy/`, `docs/`, `CHANGELOG*` — evaluation notebooks
  legitimately name many models, including rejected ones.
- Per-line escape hatch: `# model-registry: ignore <reason>`.
- Configurable via `.model-registry.yml` in the consumer repo.

**Known limit:** the scanner verifies a model is approved for *some* tier. It cannot tell
whether a given call site serves bank tenants — static analysis does not know the tenant.
Only the runtime guard (Future) closes that gap.

### 4. Gateway drift check (weekly)
Calls `{LITELLM_GATEWAY_BASE_URL}/model/info` and compares served models against the
registry, reporting: served-but-unapproved, approved-but-not-served, and metadata
mismatches. Run by a Claude Code cloud routine following the existing DD-triage pattern;
the routine invokes `model-registry drift --json` (deterministic, exit-coded) and only
formats the Slack message.

**It posts even when clean** — `14 models · 0 drift` — because a check that is silent
when healthy is indistinguishable from a check that is broken. Terse format per existing
Slack conventions. Destination: DM to the maintainer.

### 5. Change notification
Handled by GitHub's native Slack app subscribed to the repo. No custom code — a merged PR
titled "approve bge-m3 for bank tier" already carries the information.

## Data flow

```
PR edits models.yaml -> CI: validate + render check -> merge
                                                        |
                          +-----------------------------+------------------+
                          v                             v                  v
                  GitHub Slack app            consumer repo CI      weekly cloud routine
                  (devs see the change)       (scan.py on diff)     (drift.py vs gateway)
                                                                            |
                                                                       DM: drift or heartbeat
```

## Error handling

- Invalid `models.yaml` fails the registry's own CI; consumers always read a valid file.
- Consumer scan failures are **blocking** for `banned`/`deprecated`, **warning** for
  unknown IDs during a grace period, configurable per repo, so adoption doesn't
  immediately break unrelated PRs.
- Gateway unreachable during drift check: report explicitly as `drift check failed`, never
  as clean. Distinguishing "no drift" from "could not tell" is a correctness requirement.

## Testing

- `policy.py`: table-driven cases per tier rule, including each falsifying fact.
- `schema.py`: rejection cases for every validation rule.
- `scan.py`: synthetic files covering hits, excluded paths, ignore comments, and
  diff-only behaviour. Highest-risk component, gets the most tests.
- `drift.py`: mocked `/model/info` payloads covering each drift category plus an
  unreachable gateway.
- `render.py`: golden-file test of the generated table.

## Rollout

1. Repo, schema, policy, validator, renderer, seeded `models.yaml`.
2. Scanner + action; adopt in `documents-extractor` in warn mode, then blocking.
3. Drift check + cloud routine + heartbeat DM.
4. Adopt scanner in `maestro-graphs`.

## Future (explicitly not v1)

- **Runtime guard.** `maestro-graphs` already resolves `tenant_id`/`tenant_slug` into its
  request context (500+ usages, `TenantResolutionError`, per-tenant config), so a
  tenant→tier map plus a check in `llm_kit.client` would fail closed on a standard-tier
  model serving a bank tenant. This is the only thing that closes the scanner's tenant gap.
- **Generate the gateway config.** Compile `models.yaml` into the LiteLLM `config.yaml` so
  an unapproved model is not merely flagged but not deployed. Makes drift structurally
  impossible. The `gateway:` block exists in the schema from day one so this stays cheap.

## Open questions for the maintainer

1. Real facts for the seed `models.yaml` — residency, retention terms, and contract basis
   per model in current use. This is a human input the implementation cannot infer.
2. Gateway base URL and credentials for the drift check, and whether the cloud routine
   can reach it.
3. Push to the nesto GitHub org, or stay local until the seed list is real?
4. Which of the seven in-use Gemini versions are actually approved versus incidental.
