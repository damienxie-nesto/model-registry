"""Tests over the shipped artifacts themselves — `models.yaml` and the committed `README.md`.

Every other test in this suite builds its own fixture. These two are the only ones that
exercise the real compliance artifact: the file that decides who may touch bank-client
data, and the table developers are told to read as the answer.
"""

from __future__ import annotations

import re
from pathlib import Path

from model_registry.loader import load_registry
from model_registry.policy import Tier
from model_registry.render import BEGIN_MARKER, END_MARKER
from model_registry.schema import Status

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_YAML = REPO_ROOT / 'models.yaml'
README = REPO_ROOT / 'README.md'


def _readme_rows() -> list[list[str]]:
    """Parse the generated table out of the committed README, splitting on unescaped pipes."""
    text = README.read_text()
    body = text[text.index(BEGIN_MARKER) + len(BEGIN_MARKER) : text.index(END_MARKER)]
    rows = []
    for line in body.strip().splitlines():
        cells = [cell.strip() for cell in re.split(r'(?<!\\)\|', line)[1:-1]]
        if len(cells) == 8 and not cells[0].startswith(('---', 'Model')):
            rows.append(cells)
    return rows


def test_readme_bank_models_match_the_derived_bank_set() -> None:
    """The published table must name exactly the models policy grants the bank tier.

    Today both sides are empty: every seed entry is `trial`, so `bank` is structurally
    unreachable. This assertion is what keeps that true — it fails on a policy
    regression, a rendering injection, a stale README, a bad merge into `models.yaml`,
    and on the day someone flips an entry to `approved` without regenerating the table.
    """
    registry = load_registry(MODELS_YAML)
    derived_bank = {model.entry.id for model in registry.models if Tier.BANK in model.tiers}

    rows = _readme_rows()
    # Guard against a parse that silently finds nothing and makes the comparison vacuous.
    assert len(rows) == len(registry.models)

    published_bank = {row[0].strip('`') for row in rows if 'bank' in {tier.strip() for tier in row[3].split(',')}}
    assert published_bank == derived_bank


def test_no_banned_or_deprecated_entry_yet_gates_the_snapshot_pin_gap() -> None:
    """Fails the moment `models.yaml` gains its first `banned` or `deprecated` entry.

    Deliberately deferred behaviour, gated rather than written down: a snapshot pin
    (`gemini-2.5-pro-002`) classifies as *unknown* — a WARN, exit 0 — instead of
    inheriting a banned `gemini-2.5-pro`'s BLOCK. Prefix inheritance was rejected on
    purpose: `gemini-2.5-pro-exp` is a different model, not a pin, so a naive rule would
    produce false blocks, which is the failure shape that gets checks switched off.

    The gap is unreachable while nothing is banned or deprecated. This test is what
    makes it visible at the exact moment it starts to matter — the PR that bans a model
    is the PR that needs to decide what happens to its snapshot pins.
    """
    registry = load_registry(MODELS_YAML)
    blocking = sorted(
        model.entry.id for model in registry.models if model.entry.status in {Status.BANNED, Status.DEPRECATED}
    )
    assert blocking == [], (
        f'models.yaml now bans or deprecates {blocking}. The scanner blocks the exact ID only: '
        'a snapshot pin such as `<id>-002` still classifies as unknown (WARN, exit 0) and will '
        'not inherit the BLOCK. Decide how pins are handled before merging this entry — see the '
        'deferred snapshot-pin finding in .superpowers/sdd/2026-09-16-model-registry/final-review.md '
        '(section 6) — then update or remove this gate.'
    )
