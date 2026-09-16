from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from model_registry.policy import PLACEHOLDER_REGIONS, Tier, derive_tiers
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


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> Registry:
    """Load, validate, and resolve models.yaml.

    This enforces *structural* validity only — the rules that make the file readable
    and internally coherent. Every consumer (a repo's PR scan, the drift routine) runs
    this, so a rule that fails here fails everywhere, in every repo, at once.

    Governance rules that go stale with the calendar rather than with the data live in
    `check_reviews_current`, which only the `validate` command runs.
    """
    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise RegistryError(f'registry file not found: {path}') from exc
    except UnicodeDecodeError as exc:
        raise RegistryError(f'{path} is not valid UTF-8 text: {exc}') from exc
    except OSError as exc:
        # A directory, an unreadable file, a dead symlink, a vanished mount. Every one
        # of these means the registry could not be read, which is exactly what
        # RegistryError says — and RegistryError is what routes `scan` and `drift` to
        # exit 2. Letting the OSError escape instead gave the CLI's generic exit 1 with
        # no JSON line, so the weekly routine read "drift found, gateway read
        # successfully" for a check that never opened the file.
        raise RegistryError(f'{path} could not be read: {exc.strerror or exc}') from exc
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

    models = tuple(ResolvedModel(entry=entry, tiers=derive_tiers(entry)) for entry in entries)
    _check_bank_facts_are_recorded(models)

    return Registry(models=models)


def check_reviews_current(registry: Registry, today: date | None = None) -> None:
    """Fail when any entry's `review_by` has passed.

    Deliberately *not* part of `load_registry`. An overdue review is a governance
    signal about this repo — someone owes the registry a re-review — not a structural
    defect in the file. The spec's contract is "invalid models.yaml fails the
    registry's own CI; consumers always read a valid file", so running this rule on
    load would, the day the dates lapse, break every adopting repo's PR check and the
    drift routine at once. It runs in `validate`, which is this repo's own CI gate.

    `today` is injectable so the rule stays testable without freezing time.
    """
    reference_date = today or datetime.now(UTC).date()
    for model in registry.models:
        entry = model.entry
        if entry.review_by < reference_date:
            raise RegistryError(
                f'{entry.id}: review_by {entry.review_by.isoformat()} has passed; re-review or retire it'
            )


def _check_unique_ids(entries: list[ModelEntry]) -> None:
    """Reject IDs that collide, including on case alone.

    The scanner resolves through a lower-cased index (`scan._build_id_index`), so two
    entries differing only in case would silently conflate there — last one wins, and
    the losing entry's status stops being enforced at the one point where enforcement
    happens. Case-insensitive uniqueness keeps that collision impossible rather than
    invisible.
    """
    seen: dict[str, str] = {}
    for entry in entries:
        previous = seen.get(entry.id.lower())
        if previous is not None:
            detail = (
                f'duplicate model id: {entry.id}'
                if previous == entry.id
                else f'model ids {previous!r} and {entry.id!r} differ only in case; IDs are matched case-insensitively'
            )
            raise RegistryError(detail)
        seen[entry.id.lower()] = entry.id


def _check_replacements_resolve(entries: list[ModelEntry]) -> None:
    known = {entry.id for entry in entries}
    for entry in entries:
        if entry.replacement and entry.replacement not in known:
            raise RegistryError(f'{entry.id}: replacement {entry.replacement!r} is not a model in this registry')


def _check_bank_facts_are_recorded(models: tuple[ResolvedModel, ...]) -> None:
    """Reject a bank grant resting on a region nobody has recorded.

    `derive_tiers` reads `residency`, which is self-asserted, and never looks at
    `region`. An entry can therefore say `residency: canada` while its `region` is
    still the seed placeholder `unverified` and come out bank-eligible — a model whose
    physical location is literally unrecorded, presented as cleared for bank-client
    data. This is the cross-field half of the spec's "a bank-serving status the facts
    do not support". It is structural (the facts contradict each other on the page),
    so it belongs on the load path with the other coherence checks.
    """
    for model in models:
        if Tier.BANK in model.tiers and model.entry.region.strip().lower() in PLACEHOLDER_REGIONS:
            raise RegistryError(
                f'{model.entry.id}: facts derive the bank tier but region is '
                f'{model.entry.region.strip() or "empty"!r}; record the real region or do not approve it'
            )
