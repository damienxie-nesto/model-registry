from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from model_registry.policy import Tier, derive_tiers
from model_registry.schema import ModelEntry

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / 'models.yaml'


class RegistryError(Exception):
    """Raised when models.yaml cannot be loaded or violates a cross-entry rule."""


@dataclass(frozen=True)
class ResolvedModel:
    entry: ModelEntry
    tiers: frozenset[Tier]


@dataclass(frozen=True)
class Registry:
    models: tuple[ResolvedModel, ...]

    def by_id(self, model_id: str) -> ResolvedModel | None:
        for model in self.models:
            if model.entry.id == model_id:
                return model
        return None

    def ids(self) -> frozenset[str]:
        return frozenset(model.entry.id for model in self.models)


def load_registry(path: Path = DEFAULT_REGISTRY_PATH, today: date | None = None) -> Registry:
    """Load, validate, and resolve models.yaml.

    `today` is injectable so the review-date rule is testable without freezing time.
    """
    reference_date = today or datetime.now(UTC).date()

    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise RegistryError(f'registry file not found: {path}') from exc
    except yaml.YAMLError as exc:
        raise RegistryError(f'{path} is not valid YAML: {exc}') from exc

    if not raw:
        raise RegistryError(f'{path} is empty; the registry must list at least one model')
    if not isinstance(raw, list):
        raise RegistryError(f'{path} must contain a list of models, got {type(raw).__name__}')

    entries: list[ModelEntry] = []
    for index, item in enumerate(raw):
        identifier = item.get('id', f'<entry {index}>') if isinstance(item, dict) else f'<entry {index}>'
        try:
            entries.append(ModelEntry(**item))
        except ValidationError as exc:
            raise RegistryError(f'{identifier}: {exc}') from exc
        except TypeError as exc:
            raise RegistryError(f'{identifier}: entry must be a mapping') from exc

    _check_unique_ids(entries)
    _check_replacements_resolve(entries)
    _check_reviews_current(entries, reference_date)

    return Registry(models=tuple(ResolvedModel(entry=entry, tiers=derive_tiers(entry)) for entry in entries))


def _check_unique_ids(entries: list[ModelEntry]) -> None:
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            raise RegistryError(f'duplicate model id: {entry.id}')
        seen.add(entry.id)


def _check_replacements_resolve(entries: list[ModelEntry]) -> None:
    known = {entry.id for entry in entries}
    for entry in entries:
        if entry.replacement and entry.replacement not in known:
            raise RegistryError(f'{entry.id}: replacement {entry.replacement!r} is not a model in this registry')


def _check_reviews_current(entries: list[ModelEntry], today: date) -> None:
    for entry in entries:
        if entry.review_by < today:
            raise RegistryError(
                f'{entry.id}: review_by {entry.review_by.isoformat()} has passed; re-review or retire it'
            )
