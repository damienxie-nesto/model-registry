from __future__ import annotations

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
        approval_ref='https://github.com/OWNER/model-registry/pull/1',
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
