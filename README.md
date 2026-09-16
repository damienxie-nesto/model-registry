# model-registry

Source of truth for which AI models Nesto may use, and for which client tier.

`models.yaml` is the only hand-edited file here. Everything else — the table below,
the PR check, the weekly gateway drift report — is generated from it.

## How to use a model

1. Find it in the table below.
2. `bank` in the Tiers column means it may process data for bank clients. `standard`
   means it may not. `—` means do not use it at all.
3. If it is not listed, open a PR adding it. Approval is the PR review.

Tiers are **derived**, not declared: see `model_registry/policy.py` for the rules.

## Checks

| Check | Runs | On failure |
|---|---|---|
| `make validate` | this repo's CI, every PR | the registry is malformed — merge blocked |
| `model-registry render --check` | this repo's CI, every PR | the README table is stale — run `make render` |
| `model-registry scan` | consumer repos, every PR | a PR introduces a deprecated, banned, or unknown model |
| `model-registry drift` | weekly cloud routine | the gateway serves something the registry does not approve |

## Approved models

<!-- BEGIN MODELS -->
| Model | Use cases | Status | Tiers | Hosting | Region | Residency | Review by |
|---|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-2.5-pro` | general, ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-3.1-flash-lite` | ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-3.1-pro-preview` | general, ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-3.5-flash` | ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-3.5-flash-lite` | ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gemini-3.6-flash` | ocr | trial | standard | vertex | unverified | multi | 2026-12-16 |
| `gpt-4.1` | general | trial | standard | saas | us | us | 2026-12-16 |
| `gpt-4o` | general | trial | standard | saas | us | us | 2026-12-16 |
| `gpt-4o-mini` | general | trial | standard | saas | us | us | 2026-12-16 |
<!-- END MODELS -->

## Choosing a model

This registry answers *may I*, not *should I*. For which model performs best on
Nesto's own bilingual mortgage documents, see the head-to-head evaluations in
`documents-extractor/accuracy/reports/`. Public leaderboards (HF, MTEB) are a weak
signal for this domain and are referenced here only as background.
