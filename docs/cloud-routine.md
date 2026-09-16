# Weekly drift routine

A scheduled Claude Code routine runs the drift check and posts the result to Slack.
The check itself is deterministic Python; the routine only formats the message.

## What the command actually does

This section documents the real behaviour of `model-registry drift` as implemented
in `model_registry/cli.py` and `model_registry/drift.py`, which is stricter than a
first guess at the interface would suggest.

- **Exit 0** — clean. The gateway was read successfully and every served model is
  `approved` in the registry (and every `approved` model is served).
- **Exit 1** — drift found. The gateway was read successfully but disagrees with the
  registry: something is served that isn't approved, or something approved isn't
  served.
- **Exit 2** — the check did not run to completion, for **either** of two reasons:
  1. **Misconfigured**: `--base-url`/`--api-key` (normally
     `LITELLM_GATEWAY_BASE_URL`/`LITELLM_GATEWAY_API_KEY`) are missing. This is the
     most likely real-world cause of a 2 — a routine with a broken or missing secret
     will hit this every time, before ever touching the network.
  2. **Unreachable**: the gateway could not be read into a usable result. This covers
     more than "the network is down" — `fetch_served_models` also raises this for a
     non-2xx response, a body that isn't valid (or valid UTF-8) JSON, a payload that
     isn't shaped like `{"data": [...]}`, an entry in `data` missing `model_name`, and
     even a gateway that answers successfully with an **empty** `{"data": []}` (a
     gateway serving nothing is treated as broken, not as "no drift"). There are at
     least nine such distinct failure shapes bucketed into this single exit code.

  **Exit 2 always means "nobody actually looked."** Never treat it as clean, and
  never treat it as a smaller problem than exit 1 — it hides both false negatives
  and false positives equally.

- **`--json`** always emits exactly one line of pure JSON to stdout — on every exit
  path, including both exit-2 cases. The reporter should parse this line rather than
  scrape stderr or the exit code alone. Its keys, exactly as emitted by
  `_write_drift_json`:

  | Key | Type | Meaning |
  |---|---|---|
  | `status` | string | One of `clean`, `drift`, `unreachable`, `misconfigured`. |
  | `clean` | bool | `true` iff `status == "clean"`. |
  | `models_checked` | int | Total number of models in the registry (present on every status, including failures). |
  | `served_count` | int or `null` | Number of models the gateway reported serving. `null` whenever the gateway wasn't successfully read (`unreachable` or `misconfigured`). |
  | `items` | array | `{"kind", "model_id", "detail"}` objects. Empty on `clean`, `unreachable`, and `misconfigured`. `kind` is `served_not_approved` or `approved_not_served`. |
  | `error` | string or `null` | The failure message on `unreachable`/`misconfigured`; `null` otherwise. |

## Routine prompt

> Run the model registry drift check and report it to Slack.
>
> 1. `cd` to the model-registry checkout and run:
>    `uv run model-registry drift --json`
>    Capture stdout (one JSON line) regardless of the exit code.
> 2. Parse the JSON and branch on `status`:
>    - `status == "clean"` — post exactly:
>      `model registry · {models_checked} models · 0 drift`
>    - `status == "drift"` — post the item count, then one line per item:
>      `<kind>: <model_id> — <detail>`. Lead with `served_not_approved` items; those
>      mean an unapproved model is callable right now.
>    - `status == "unreachable"` or `status == "misconfigured"` — post
>      `model registry · drift check FAILED (<status>)` followed by the `error`
>      field. Do not report this as clean, and do not treat `misconfigured`
>      (usually a missing `LITELLM_GATEWAY_BASE_URL`/`LITELLM_GATEWAY_API_KEY` in the
>      routine's own environment) as a lesser issue than `unreachable`.
> 3. Post to the maintainer's Slack DM. Keep it terse — no preamble, no summary
>    paragraph, no restating the request.

## Why it posts when clean

A check that is silent when healthy is indistinguishable from a check that is
broken. The `{models_checked} models · 0 drift` heartbeat is the evidence that it
ran — not just that nothing is wrong.

## Expect drift on the first real run

Every seeded model in `models.yaml` is currently `status: trial`, and `compare()`
only treats `approved` models as servable. Until a reviewed PR flips justified
models to `approved`, the **first run against a live gateway will report every
served model as `served_not_approved` drift.** That is correct behaviour given the
current registry contents, not a bug in the check — do not read it as "the tool is
broken" or silence the routine to work around it.

## Scheduling

Register with the `schedule` skill. Weekly is the starting cadence; if the gateway
config changes more often than that, shorten it.

## Prerequisites

- The routine's environment needs `LITELLM_GATEWAY_BASE_URL` and
  `LITELLM_GATEWAY_API_KEY`, and network reachability to the gateway. If the cloud
  runner cannot reach a VPC-internal gateway, this check has to move to a GCP job
  and only the Slack formatting stays here.
