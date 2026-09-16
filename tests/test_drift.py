from __future__ import annotations

from datetime import date

import httpx
import pytest

from model_registry.drift import (
    DriftKind,
    GatewayUnreachableError,
    compare,
    fetch_served_models,
)
from model_registry.loader import Registry, ResolvedModel
from model_registry.policy import Tier
from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _resolved(model_id: str, status: Status = Status.APPROVED) -> ResolvedModel:
    entry = ModelEntry(
        id=model_id,
        display_name=model_id,
        provider=Provider.GOOGLE,
        hosting=Hosting.VERTEX,
        region='northamerica-northeast1',
        residency=Residency.CANADA,
        open_weights=False,
        trains_on_customer_data=False,
        use_cases=[UseCase.OCR],
        status=status,
        approved_on=date(2026, 9, 16),
        approval_ref='https://github.com/damienxie-nesto/model-registry/pull/1',
        review_by=date(2099, 1, 1),
        replacement='beta' if status is Status.DEPRECATED else None,
    )
    return ResolvedModel(entry=entry, tiers=frozenset({Tier.STANDARD}))


def test_clean_when_served_matches_approved() -> None:
    registry = Registry(models=(_resolved('alpha'), _resolved('beta')))
    report = compare(frozenset({'alpha', 'beta'}), registry)
    assert report.is_clean
    assert report.models_checked == 2


def test_served_but_not_approved_is_drift() -> None:
    registry = Registry(models=(_resolved('alpha'),))
    report = compare(frozenset({'alpha', 'rogue'}), registry)
    assert not report.is_clean
    assert report.items[0].kind is DriftKind.SERVED_NOT_APPROVED
    assert report.items[0].model_id == 'rogue'


def test_serving_a_deprecated_model_is_drift() -> None:
    registry = Registry(models=(_resolved('alpha', Status.DEPRECATED), _resolved('beta')))
    report = compare(frozenset({'alpha', 'beta'}), registry)
    assert any(item.model_id == 'alpha' for item in report.items)


def test_approved_but_not_served_is_drift() -> None:
    registry = Registry(models=(_resolved('alpha'), _resolved('beta')))
    report = compare(frozenset({'alpha'}), registry)
    assert report.items[0].kind is DriftKind.APPROVED_NOT_SERVED
    assert report.items[0].model_id == 'beta'


def test_fetch_parses_model_info_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['authorization'] == 'Bearer key-123'
        return httpx.Response(
            200,
            json={'data': [{'model_name': 'alpha'}, {'model_name': 'beta'}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_served_models('https://gw.example', 'key-123', client=client) == frozenset({'alpha', 'beta'})


def test_fetch_raises_on_transport_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayUnreachableError):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_on_http_error() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(503)))
    with pytest.raises(GatewayUnreachableError):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_on_malformed_payload() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={'oops': 1})))
    with pytest.raises(GatewayUnreachableError, match='unexpected'):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_when_an_entry_is_missing_model_name() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'data': [{'model_name': 'alpha'}, {'not_model_name': 'rogue'}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayUnreachableError, match='unexpected entry'):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_when_gateway_serves_nothing() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={'data': []})))
    with pytest.raises(GatewayUnreachableError, match='no models'):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_on_undecodable_body() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b'\xff\xfe\x00\x01')),
    )
    with pytest.raises(GatewayUnreachableError):
        fetch_served_models('https://gw.example', 'key-123', client=client)
