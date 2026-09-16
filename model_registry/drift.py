from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

import httpx

from model_registry.loader import Registry
from model_registry.schema import Status

_TIMEOUT_SECONDS = 20.0


class DriftKind(StrEnum):
    SERVED_NOT_APPROVED = 'served_not_approved'
    APPROVED_NOT_SERVED = 'approved_not_served'


class GatewayUnreachableError(Exception):
    """The gateway could not be read.

    Raised rather than returning an empty result so that 'we could not tell' is never
    reported as 'no drift'.
    """


@dataclass(frozen=True)
class DriftItem:
    kind: DriftKind
    model_id: str
    detail: str


@dataclass(frozen=True)
class DriftReport:
    items: tuple[DriftItem, ...]
    models_checked: int

    @property
    def is_clean(self) -> bool:
        return not self.items


def fetch_served_models(base_url: str, api_key: str, client: httpx.Client | None = None) -> frozenset[str]:
    """Read the model names the LiteLLM gateway currently serves.

    Raises `GatewayUnreachableError` on any failure to obtain a usable payload —
    transport errors, non-2xx responses, a body that is not valid JSON, and JSON
    that is not shaped like `{"data": [{"model_name": ...}, ...]}` — so that "could
    not tell" is never silently reported as "no drift".
    """
    owns_client = client is None
    active = client or httpx.Client(timeout=_TIMEOUT_SECONDS)
    try:
        response = active.get(
            f'{base_url.rstrip("/")}/model/info',
            headers={'Authorization': f'Bearer {api_key}'},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise GatewayUnreachableError(f'could not read {base_url}/model/info: {exc}') from exc
    finally:
        if owns_client:
            active.close()

    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise GatewayUnreachableError(f'unexpected /model/info payload from {base_url}')

    return frozenset(str(item['model_name']) for item in data if isinstance(item, dict) and 'model_name' in item)


def compare(served: frozenset[str], registry: Registry) -> DriftReport:
    """Compare what the gateway serves against models the registry approves.

    Approval means `status is Status.APPROVED` specifically: a registry entry with
    any other status (trial, deprecated, banned) is not approved, and the gateway
    serving it is drift — the report says what its status actually is.
    """
    items: list[DriftItem] = []

    servable = {model.entry.id for model in registry.models if model.entry.status is Status.APPROVED}

    for model_id in sorted(served - servable):
        resolved = registry.by_id(model_id)
        detail = f'status is {resolved.entry.status.value}' if resolved else 'not in the registry at all'
        items.append(DriftItem(kind=DriftKind.SERVED_NOT_APPROVED, model_id=model_id, detail=detail))

    items.extend(
        DriftItem(
            kind=DriftKind.APPROVED_NOT_SERVED,
            model_id=model_id,
            detail='approved in the registry but the gateway does not serve it',
        )
        for model_id in sorted(servable - served)
    )

    return DriftReport(items=tuple(items), models_checked=len(registry.models))
