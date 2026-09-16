from __future__ import annotations

from datetime import date

import pytest

from model_registry.policy import Tier, derive_tiers
from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _entry(**overrides: object) -> ModelEntry:
    base: dict[str, object] = {
        'id': 'test-model',
        'display_name': 'Test Model',
        'provider': Provider.GOOGLE,
        'hosting': Hosting.VERTEX,
        'region': 'northamerica-northeast1',
        'residency': Residency.CANADA,
        'open_weights': False,
        'trains_on_customer_data': False,
        'use_cases': [UseCase.OCR],
        'status': Status.APPROVED,
        'approved_on': date(2026, 9, 16),
        'approval_ref': 'https://github.com/damienxie-nesto/model-registry/pull/1',
        'review_by': date(2027, 9, 16),
    }
    base.update(overrides)
    return ModelEntry(**base)  # type: ignore[arg-type]


def test_canadian_approved_model_serves_both_tiers() -> None:
    assert derive_tiers(_entry()) == frozenset({Tier.BANK, Tier.STANDARD})


def test_us_saas_model_serves_standard_only() -> None:
    tiers = derive_tiers(_entry(hosting=Hosting.SAAS, residency=Residency.US, provider=Provider.OPENAI))
    assert tiers == frozenset({Tier.STANDARD})


def test_self_hosted_open_weights_serves_bank_regardless_of_residency_label() -> None:
    tiers = derive_tiers(
        _entry(hosting=Hosting.SELF_HOSTED, open_weights=True, residency=Residency.MULTI),
    )
    assert tiers == frozenset({Tier.BANK, Tier.STANDARD})


def test_training_on_customer_data_disqualifies_bank_tier() -> None:
    tiers = derive_tiers(_entry(trains_on_customer_data=True))
    assert tiers == frozenset({Tier.STANDARD})


def test_trial_status_never_reaches_bank_tier() -> None:
    tiers = derive_tiers(_entry(status=Status.TRIAL))
    assert tiers == frozenset({Tier.STANDARD})


def test_open_weights_requires_self_hosted_for_bank() -> None:
    tiers = derive_tiers(_entry(open_weights=True, hosting=Hosting.SAAS, residency=Residency.US))
    assert tiers == frozenset({Tier.STANDARD})


def test_self_hosted_requires_open_weights_for_bank() -> None:
    tiers = derive_tiers(_entry(open_weights=False, hosting=Hosting.SELF_HOSTED, residency=Residency.US))
    assert tiers == frozenset({Tier.STANDARD})


@pytest.mark.parametrize('status', [Status.DEPRECATED, Status.BANNED])
def test_deprecated_and_banned_serve_no_tier(status: Status) -> None:
    tiers = derive_tiers(_entry(status=status, replacement='other-model'))
    assert tiers == frozenset()
