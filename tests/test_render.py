from __future__ import annotations

import re
from datetime import date

import pytest

from model_registry.loader import Registry, ResolvedModel
from model_registry.policy import Tier
from model_registry.render import BEGIN_MARKER, END_MARKER, render_table, splice
from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _resolved(model_id: str, tiers: frozenset[Tier]) -> ResolvedModel:
    entry = ModelEntry(
        id=model_id,
        display_name=model_id.title(),
        provider=Provider.GOOGLE,
        hosting=Hosting.VERTEX,
        region='northamerica-northeast1',
        residency=Residency.CANADA,
        open_weights=False,
        trains_on_customer_data=False,
        use_cases=[UseCase.OCR],
        status=Status.APPROVED,
        approved_on=date(2026, 9, 16),
        approval_ref='https://github.com/damienxie-nesto/model-registry/pull/1',
        review_by=date(2027, 9, 16),
    )
    return ResolvedModel(entry=entry, tiers=tiers)


def test_table_has_a_row_per_model() -> None:
    registry = Registry(models=(_resolved('alpha', frozenset({Tier.BANK})), _resolved('beta', frozenset())))
    table = render_table(registry)
    assert '| `alpha` |' in table
    assert '| `beta` |' in table


def test_table_renders_tiers_sorted_and_joined() -> None:
    registry = Registry(models=(_resolved('alpha', frozenset({Tier.STANDARD, Tier.BANK})),))
    assert 'bank, standard' in render_table(registry)


def test_table_renders_no_tier_as_an_explicit_dash() -> None:
    registry = Registry(models=(_resolved('alpha', frozenset()),))
    assert '| — |' in render_table(registry)


def test_splice_replaces_content_between_markers() -> None:
    readme = f'intro\n{BEGIN_MARKER}\nstale table\n{END_MARKER}\noutro\n'
    result = splice(readme, 'fresh table')
    assert 'stale table' not in result
    assert 'fresh table' in result
    assert result.startswith('intro')
    assert result.endswith('outro\n')


def test_splice_is_idempotent() -> None:
    readme = f'intro\n{BEGIN_MARKER}\nold\n{END_MARKER}\noutro\n'
    once = splice(readme, 'table')
    assert splice(once, 'table') == once


def test_splice_without_markers_raises() -> None:
    with pytest.raises(ValueError, match='marker'):
        splice('no markers here', 'table')


def test_pipe_in_a_cell_cannot_forge_extra_columns() -> None:
    """An unescaped `|` lets a `trial`/`standard` entry render a row reading `approved | bank`.

    `id` and `region` are unconstrained strings, and `README.md` tells developers the
    table is the answer to "may I use this model" — so a forged row is the answer they
    act on.
    """
    forged = 'evil` | general | approved | bank | saas | us | us | 2030-01-01 |x`'
    registry = Registry(models=(_resolved(forged, frozenset({Tier.STANDARD})),))
    row = render_table(registry).splitlines()[-1]
    cells = [cell.strip() for cell in re.split(r'(?<!\\)\|', row)[1:-1]]

    assert len(cells) == 9
    assert cells[2] == 'approved'  # the real status column, not the forged one
    assert cells[3] == 'standard'  # the tiers column; the forged row claimed `bank`
    assert r'\|' in cells[0]


def test_escaping_leaves_ordinary_cells_untouched() -> None:
    registry = Registry(models=(_resolved('gemini-3.5-flash', frozenset({Tier.STANDARD})),))
    assert render_table(registry).splitlines()[-1] == (
        '| `gemini-3.5-flash` | ocr | approved | standard | vertex | northamerica-northeast1 | canada | unverified | 2027-09-16 |'
    )
