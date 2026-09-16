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

## Approved models

<!-- BEGIN MODELS -->
<!-- END MODELS -->

## Choosing a model

This registry answers *may I*, not *should I*. For which model performs best on
Nesto's own bilingual mortgage documents, see the head-to-head evaluations in
`documents-extractor/accuracy/reports/`. Public leaderboards (HF, MTEB) are a weak
signal for this domain and are referenced here only as background.
