# Model Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `model-registry` repo whose `models.yaml` is the single source of truth for which AI models Nesto may use for which client tier, enforced in developer PRs and checked weekly against the LiteLLM gateway.

**Architecture:** A small Python package reads a hand-edited YAML file, validates it, and derives client-tier eligibility from recorded facts rather than hand-set booleans. Four consumers read that one file: a validator in the registry's own CI, a README table renderer, a PR-time scanner shipped to consumer repos as a composite GitHub Action, and a gateway drift check driven by a Claude cloud routine. Nothing is hand-maintained except `models.yaml`.

**Tech Stack:** Python 3.12+, pydantic v2, PyYAML, httpx, argparse (stdlib CLI — no extra dependency), uv, ruff, mypy strict, pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-model-registry-design.md`

## Global Constraints

- `requires-python = ">=3.12"`.
- Every source file starts with `from __future__ import annotations` (enforced by ruff isort `required-imports`).
- Relative imports are banned; use absolute `model_registry.*` imports.
- mypy runs in **strict** mode over `model_registry/` and `tests/`.
- ruff: `line-length = 120`, `target-version = "py312"`, format `quote-style = "single"`.
- Test files are named `test_<module>.py`; `testpaths = ["tests"]`.
- `make check` = `format_check` + `lint` + `typecheck` + `run_tests`. It must pass before every commit.
- Tier names are exactly `bank` and `standard`. Status values are exactly `approved`, `trial`, `deprecated`, `banned`.
- No dependency on Nesto's private Artifact Registry — this repo uses public PyPI only, so CI and consumer repos need no keyring auth.

---

## File Structure

| File | Responsibility |
|---|---|
| `models.yaml` | Source of truth. Hand-edited via PR. The only hand-maintained artifact. |
| `model_registry/schema.py` | Pydantic types + per-entry validation rules. No I/O, no policy. |
| `model_registry/policy.py` | Pure function: facts → tiers. The contractual position lives here alone. |
| `model_registry/loader.py` | File I/O, cross-entry validation (duplicates, dangling replacements), resolution. |
| `model_registry/render.py` | `Registry` → markdown table between README markers. |
| `model_registry/scan.py` | Find model IDs in source/diff text, classify against the registry. |
| `model_registry/drift.py` | Gateway `/model/info` → drift report. Network isolated to one module. |
| `model_registry/cli.py` | argparse entry point: `validate`, `render`, `scan`, `drift`. |
| `action.yml` | Composite GitHub Action consumer repos adopt. |
| `docs/cloud-routine.md` | The weekly drift routine's prompt and setup. |

Policy is split from schema so the tier rules can be reviewed as one small file by someone who does not read Python packaging. Network access is confined to `drift.py` so every other module is testable without mocks.

---

### Task 1: Repo scaffolding and entry schema

**Files:**
- Create: `pyproject.toml`, `ruff.toml`, `Makefile`, `.gitignore`, `model_registry/__init__.py`, `model_registry/py.typed`, `model_registry/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Provider`, `Hosting`, `Residency`, `Status`, `UseCase` (all `StrEnum`); `GatewayBinding`; `ModelEntry` with fields `id: str`, `display_name: str`, `provider: Provider`, `hosting: Hosting`, `region: str`, `residency: Residency`, `open_weights: bool`, `trains_on_customer_data: bool`, `use_cases: list[UseCase]`, `status: Status`, `approved_on: date`, `approval_ref: str`, `review_by: date`, `notes: str`, `replacement: str | None`, `gateway: GatewayBinding | None`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "model-registry"
version = "0.1.0"
description = "Source of truth for AI models approved for use at Nesto, and the checks that enforce it."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.28",
]

[project.scripts]
model-registry = "model_registry.cli:main"

[build-system]
requires = ["setuptools>=82.0.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["model_registry*"]

[tool.setuptools.package-data]
"*" = ["py.typed"]

# disable pyright for cursor/vscode users; we use mypy
[tool.pyright]
typeCheckingMode = "off"
reportMissingTypeStubs = false

[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.coverage.run]
omit = ["tests/*"]

[dependency-groups]
dev = [
    "mypy>=1.20.2",
    "pre-commit>=4.6.0",
    "ruff>=0.15.12",
    "pytest>=9.0.3",
    "pytest-cov>=7.1.0",
    "types-pyyaml>=6.0",
]
```

- [ ] **Step 2: Copy `ruff.toml` from llm-kit verbatim**

Run: `cp ../llm-kit/ruff.toml ./ruff.toml`

Then remove nothing — the config is adopted as-is so lint behaviour matches the other repos.

- [ ] **Step 3: Create `Makefile`**

```make
export UV_LOCKED := 1

setup:
	uv venv
	uv sync --group dev
	GIT_CONFIG_GLOBAL=/dev/null uv run pre-commit install

update:
	UV_LOCKED=0 uv sync --group dev --upgrade

check-lock:
	uv lock --check

test: check

lint:
	uv run ruff check model_registry/ tests/

format:
	uv run ruff format model_registry/ tests/

format_check:
	uv run ruff format --check model_registry/ tests/

fix:
	uv run ruff check --fix model_registry/ tests/

typecheck:
	uv run mypy model_registry/ tests/

run_tests:
	uv run pytest -v ./tests --cov=model_registry --cov-report term-missing -p no:warnings

validate:
	uv run model-registry validate

render:
	uv run model-registry render

check: format_check lint typecheck run_tests validate
```

Note `check` includes `validate` — the registry's own data is part of its test gate.

- [ ] **Step 4: Create `.gitignore`**

```
.venv/
__pycache__/
*.egg-info/
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/
```

- [ ] **Step 5: Create empty package files**

Run: `mkdir -p model_registry tests && touch model_registry/__init__.py model_registry/py.typed tests/__init__.py`

- [ ] **Step 6: Write the failing test**

Create `tests/test_schema.py`:

```python
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _entry(**overrides: object) -> ModelEntry:
    base: dict[str, object] = {
        'id': 'gemini-2.5-flash',
        'display_name': 'Gemini 2.5 Flash',
        'provider': Provider.GOOGLE,
        'hosting': Hosting.VERTEX,
        'region': 'northamerica-northeast1',
        'residency': Residency.CANADA,
        'open_weights': False,
        'trains_on_customer_data': False,
        'use_cases': [UseCase.OCR],
        'status': Status.APPROVED,
        'approved_on': date(2026, 9, 16),
        'approval_ref': 'https://github.com/OWNER/model-registry/pull/1',
        'review_by': date(2027, 9, 16),
    }
    base.update(overrides)
    return ModelEntry(**base)  # type: ignore[arg-type]


def test_valid_entry_parses():
    entry = _entry()
    assert entry.id == 'gemini-2.5-flash'
    assert entry.residency is Residency.CANADA


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        _entry(bank_approved=True)


def test_deprecated_without_replacement_is_rejected():
    with pytest.raises(ValidationError, match='requires a replacement'):
        _entry(status=Status.DEPRECATED)


def test_deprecated_with_replacement_parses():
    entry = _entry(status=Status.DEPRECATED, replacement='gemini-3.5-flash')
    assert entry.replacement == 'gemini-3.5-flash'


def test_empty_use_cases_is_rejected():
    with pytest.raises(ValidationError):
        _entry(use_cases=[])


def test_entry_is_frozen():
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.id = 'other'  # type: ignore[misc]
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `make setup && uv run pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.schema'`

- [ ] **Step 8: Write `model_registry/schema.py`**

```python
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Provider(StrEnum):
    GOOGLE = 'google'
    OPENAI = 'openai'
    ANTHROPIC = 'anthropic'
    COMMUNITY = 'community'


class Hosting(StrEnum):
    VERTEX = 'vertex'
    SAAS = 'saas'
    SELF_HOSTED = 'self-hosted'


class Residency(StrEnum):
    CANADA = 'canada'
    US = 'us'
    MULTI = 'multi'


class Status(StrEnum):
    APPROVED = 'approved'
    TRIAL = 'trial'
    DEPRECATED = 'deprecated'
    BANNED = 'banned'


class UseCase(StrEnum):
    OCR = 'ocr'
    EMBEDDING = 'embedding'
    GENERAL = 'general'
    RERANKING = 'reranking'


class GatewayBinding(BaseModel):
    """LiteLLM-facing fields. Unused in v1; recorded so the gateway config can later
    be generated from this file instead of hand-maintained alongside it."""

    # `model_name` collides with pydantic's protected `model_` namespace.
    model_config = ConfigDict(frozen=True, extra='forbid', protected_namespaces=())

    model_name: str
    api_base: str | None = None


class ModelEntry(BaseModel):
    """One model and the verifiable facts about it.

    Eligibility is deliberately absent: it is derived from these facts by
    `model_registry.policy`, never asserted here.
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    id: str
    display_name: str
    provider: Provider
    hosting: Hosting
    region: str
    residency: Residency
    open_weights: bool
    trains_on_customer_data: bool
    use_cases: Annotated[list[UseCase], Field(min_length=1)]
    status: Status
    approved_on: date
    approval_ref: str
    review_by: date
    notes: str = ''
    replacement: str | None = None
    gateway: GatewayBinding | None = None

    @model_validator(mode='after')
    def _deprecated_needs_replacement(self) -> ModelEntry:
        if self.status is Status.DEPRECATED and not self.replacement:
            raise ValueError(f'{self.id}: status=deprecated requires a replacement')
        return self
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `uv run pytest tests/test_schema.py -v`
Expected: 6 passed

- [ ] **Step 10: Run the full gate**

Run: `uv run ruff format model_registry/ tests/ && uv run ruff check model_registry/ tests/ && uv run mypy model_registry/ tests/`
Expected: all clean. (`make check` will fail until Task 5 adds the CLI — that is expected at this point.)

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml ruff.toml Makefile .gitignore uv.lock model_registry/ tests/
git commit -m "feat: model entry schema and repo scaffolding"
```

---

### Task 2: Tier derivation policy

**Files:**
- Create: `model_registry/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: `ModelEntry`, `Hosting`, `Residency`, `Status` from `model_registry.schema`.
- Produces: `Tier` (`StrEnum` with `BANK = 'bank'`, `STANDARD = 'standard'`) and `derive_tiers(entry: ModelEntry) -> frozenset[Tier]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_policy.py`:

```python
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
        'approval_ref': 'https://github.com/OWNER/model-registry/pull/1',
        'review_by': date(2027, 9, 16),
    }
    base.update(overrides)
    return ModelEntry(**base)  # type: ignore[arg-type]


def test_canadian_approved_model_serves_both_tiers():
    assert derive_tiers(_entry()) == frozenset({Tier.BANK, Tier.STANDARD})


def test_us_saas_model_serves_standard_only():
    tiers = derive_tiers(_entry(hosting=Hosting.SAAS, residency=Residency.US, provider=Provider.OPENAI))
    assert tiers == frozenset({Tier.STANDARD})


def test_self_hosted_open_weights_serves_bank_regardless_of_residency_label():
    tiers = derive_tiers(
        _entry(hosting=Hosting.SELF_HOSTED, open_weights=True, residency=Residency.MULTI),
    )
    assert Tier.BANK in tiers


def test_training_on_customer_data_disqualifies_bank_tier():
    tiers = derive_tiers(_entry(trains_on_customer_data=True))
    assert tiers == frozenset({Tier.STANDARD})


def test_trial_status_never_reaches_bank_tier():
    tiers = derive_tiers(_entry(status=Status.TRIAL))
    assert tiers == frozenset({Tier.STANDARD})


@pytest.mark.parametrize('status', [Status.DEPRECATED, Status.BANNED])
def test_deprecated_and_banned_serve_no_tier(status: Status):
    tiers = derive_tiers(_entry(status=status, replacement='other-model'))
    assert tiers == frozenset()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.policy'`

- [ ] **Step 3: Write `model_registry/policy.py`**

```python
from __future__ import annotations

from enum import StrEnum

from model_registry.schema import Hosting, ModelEntry, Residency, Status


class Tier(StrEnum):
    """Client segments, ordered from most to least restricted."""

    BANK = 'bank'
    STANDARD = 'standard'


def derive_tiers(entry: ModelEntry) -> frozenset[Tier]:
    """Derive which client tiers may use a model from its recorded facts.

    These rules encode a contractual position, not a legal one. They live in one
    place so that correcting them is a single reviewed change.

    - `standard`: anything we have approved or are trialling.
    - `bank`: fully approved, never trained on customer data, and either the data
      stays in Canada or the weights are open and we run them ourselves.
    """
    tiers: set[Tier] = set()

    if entry.status in {Status.APPROVED, Status.TRIAL}:
        tiers.add(Tier.STANDARD)

    data_stays_under_our_control = entry.residency is Residency.CANADA or (
        entry.open_weights and entry.hosting is Hosting.SELF_HOSTED
    )
    if entry.status is Status.APPROVED and not entry.trains_on_customer_data and data_stays_under_our_control:
        tiers.add(Tier.BANK)

    return frozenset(tiers)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_policy.py -v`
Expected: 7 passed (the parametrized case counts twice)

- [ ] **Step 5: Commit**

```bash
git add model_registry/policy.py tests/test_policy.py
git commit -m "feat: derive client tiers from recorded model facts"
```

---

### Task 3: Registry loader and seed data

**Files:**
- Create: `model_registry/loader.py`, `models.yaml`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `ModelEntry` from `schema`, `Tier`/`derive_tiers` from `policy`.
- Produces: `RegistryError(Exception)`; `ResolvedModel` (frozen dataclass with `entry: ModelEntry`, `tiers: frozenset[Tier]`); `Registry` (frozen dataclass with `models: tuple[ResolvedModel, ...]`, methods `by_id(model_id: str) -> ResolvedModel | None` and `ids() -> frozenset[str]`); `load_registry(path: Path, today: date | None = None) -> Registry`; `DEFAULT_REGISTRY_PATH: Path`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_loader.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from model_registry.loader import Registry, RegistryError, load_registry
from model_registry.policy import Tier

VALID_ENTRY = """
- id: gemini-2.5-flash
  display_name: Gemini 2.5 Flash
  provider: google
  hosting: vertex
  region: northamerica-northeast1
  residency: canada
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: approved
  approved_on: 2026-09-16
  approval_ref: https://github.com/OWNER/model-registry/pull/1
  review_by: 2027-09-16
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / 'models.yaml'
    path.write_text(content)
    return path


def test_loads_and_derives_tiers(tmp_path: Path):
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert isinstance(registry, Registry)
    resolved = registry.by_id('gemini-2.5-flash')
    assert resolved is not None
    assert Tier.BANK in resolved.tiers


def test_unknown_id_returns_none(tmp_path: Path):
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert registry.by_id('nope') is None


def test_duplicate_ids_are_rejected(tmp_path: Path):
    with pytest.raises(RegistryError, match='duplicate'):
        load_registry(_write(tmp_path, VALID_ENTRY + VALID_ENTRY), today=date(2026, 9, 16))


def test_overdue_review_is_rejected(tmp_path: Path):
    with pytest.raises(RegistryError, match='review_by'):
        load_registry(_write(tmp_path, VALID_ENTRY), today=date(2028, 1, 1))


def test_dangling_replacement_is_rejected(tmp_path: Path):
    content = VALID_ENTRY.replace('status: approved', 'status: deprecated\n  replacement: ghost-model')
    with pytest.raises(RegistryError, match='replacement'):
        load_registry(_write(tmp_path, content), today=date(2026, 9, 16))


def test_empty_file_is_rejected(tmp_path: Path):
    with pytest.raises(RegistryError, match='empty'):
        load_registry(_write(tmp_path, ''), today=date(2026, 9, 16))


def test_invalid_entry_reports_the_model_id(tmp_path: Path):
    content = VALID_ENTRY.replace('residency: canada', 'residency: mars')
    with pytest.raises(RegistryError, match='gemini-2.5-flash'):
        load_registry(_write(tmp_path, content), today=date(2026, 9, 16))


def test_ids_returns_every_model(tmp_path: Path):
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert registry.ids() == frozenset({'gemini-2.5-flash'})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.loader'`

- [ ] **Step 3: Write `model_registry/loader.py`**

```python
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
            raise RegistryError(f'{entry.id}: review_by {entry.review_by.isoformat()} has passed; re-review or retire it')
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_loader.py -v`
Expected: 8 passed

- [ ] **Step 5: Create the seed `models.yaml`**

This seed encodes what is *observably in use* today, with every entry marked `trial` and carrying a `notes` field stating the facts are unverified. It deliberately grants **no** bank-tier access until a human confirms residency and retention terms — `trial` status cannot reach the bank tier by policy, so an unverified seed is safe by construction.

```yaml
# Source of truth for AI models approved for use at Nesto.
#
# Edit via pull request only. Tiers are NOT set here: they are derived from these
# facts by model_registry/policy.py. To approve a model for bank clients, record
# facts that justify it (Canadian residency or self-hosted open weights, and no
# training on customer data) and set status: approved.
#
# SEED DATA — every entry below is `trial` because its residency and retention
# terms have not yet been verified by a human. No entry is bank-eligible until
# someone confirms the facts and flips status to `approved` in a reviewed PR.

- id: gemini-2.5-pro
  display_name: Gemini 2.5 Pro
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr, general]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: In use in documents-extractor. Region and DPA terms UNVERIFIED.

- id: gemini-2.5-flash
  display_name: Gemini 2.5 Flash
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Region and DPA terms UNVERIFIED.

- id: gemini-3.5-flash
  display_name: Gemini 3.5 Flash
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Region and DPA terms UNVERIFIED.

- id: gemini-3.5-flash-lite
  display_name: Gemini 3.5 Flash Lite
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Region and DPA terms UNVERIFIED.

- id: gemini-3.6-flash
  display_name: Gemini 3.6 Flash
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Region and DPA terms UNVERIFIED.

- id: gemini-3.1-pro-preview
  display_name: Gemini 3.1 Pro (preview)
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr, general]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Preview model. Region and DPA terms UNVERIFIED.

- id: gemini-3.1-flash-lite
  display_name: Gemini 3.1 Flash Lite
  provider: google
  hosting: vertex
  region: unverified
  residency: multi
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: Region and DPA terms UNVERIFIED.

- id: gpt-4.1
  display_name: GPT-4.1
  provider: openai
  hosting: saas
  region: us
  residency: us
  open_weights: false
  trains_on_customer_data: false
  use_cases: [general]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: US-hosted; standard tier only by policy. Retention terms UNVERIFIED.

- id: gpt-4o
  display_name: GPT-4o
  provider: openai
  hosting: saas
  region: us
  residency: us
  open_weights: false
  trains_on_customer_data: false
  use_cases: [general]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: US-hosted; standard tier only by policy. Retention terms UNVERIFIED.

- id: gpt-4o-mini
  display_name: GPT-4o mini
  provider: openai
  hosting: saas
  region: us
  residency: us
  open_weights: false
  trains_on_customer_data: false
  use_cases: [general]
  status: trial
  approved_on: 2026-09-16
  approval_ref: seed — no approval yet
  review_by: 2026-12-16
  notes: US-hosted; standard tier only by policy. Retention terms UNVERIFIED.
```

- [ ] **Step 6: Verify the seed loads**

Run: `uv run python -c "from model_registry.loader import load_registry; r = load_registry(); print(len(r.models), 'models'); print({m.entry.id: sorted(m.tiers) for m in r.models})"`
Expected: `10 models` and every model showing `['standard']` only — no bank tier, because all entries are `trial`.

- [ ] **Step 7: Commit**

```bash
git add model_registry/loader.py tests/test_loader.py models.yaml
git commit -m "feat: registry loader with cross-entry validation and seed data"
```

---
### Task 4: README table renderer

**Files:**
- Create: `model_registry/render.py`, `README.md`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Registry`, `ResolvedModel` from `loader`; `Tier` from `policy`.
- Produces: `BEGIN_MARKER: str`, `END_MARKER: str`, `render_table(registry: Registry) -> str`, `splice(readme_text: str, table: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
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


def test_table_has_a_row_per_model():
    registry = Registry(models=(_resolved('alpha', frozenset({Tier.BANK})), _resolved('beta', frozenset())))
    table = render_table(registry)
    assert '| `alpha` |' in table
    assert '| `beta` |' in table


def test_table_renders_tiers_sorted_and_joined():
    registry = Registry(models=(_resolved('alpha', frozenset({Tier.STANDARD, Tier.BANK})),))
    assert 'bank, standard' in render_table(registry)


def test_table_renders_no_tier_as_an_explicit_dash():
    registry = Registry(models=(_resolved('alpha', frozenset()),))
    assert '| — |' in render_table(registry)


def test_splice_replaces_content_between_markers():
    readme = f'intro\n{BEGIN_MARKER}\nstale table\n{END_MARKER}\noutro\n'
    result = splice(readme, 'fresh table')
    assert 'stale table' not in result
    assert 'fresh table' in result
    assert result.startswith('intro')
    assert result.endswith('outro\n')


def test_splice_is_idempotent():
    readme = f'intro\n{BEGIN_MARKER}\nold\n{END_MARKER}\noutro\n'
    once = splice(readme, 'table')
    assert splice(once, 'table') == once


def test_splice_without_markers_raises():
    with pytest.raises(ValueError, match='marker'):
        splice('no markers here', 'table')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.render'`

- [ ] **Step 3: Write `model_registry/render.py`**

```python
from __future__ import annotations

from model_registry.loader import Registry

BEGIN_MARKER = '<!-- BEGIN MODELS -->'
END_MARKER = '<!-- END MODELS -->'

_HEADER = (
    '| Model | Use cases | Status | Tiers | Hosting | Region | Residency | Review by |\n'
    '|---|---|---|---|---|---|---|---|'
)


def render_table(registry: Registry) -> str:
    """Render the registry as a markdown table. Generated — never hand-edited."""
    rows = [_HEADER]
    for model in sorted(registry.models, key=lambda m: m.entry.id):
        entry = model.entry
        tiers = ', '.join(sorted(model.tiers)) if model.tiers else '—'
        use_cases = ', '.join(sorted(use_case.value for use_case in entry.use_cases))
        rows.append(
            f'| `{entry.id}` | {use_cases} | {entry.status.value} | {tiers} | '
            f'{entry.hosting.value} | {entry.region} | {entry.residency.value} | '
            f'{entry.review_by.isoformat()} |',
        )
    return '\n'.join(rows)


def splice(readme_text: str, table: str) -> str:
    """Replace whatever sits between the markers with `table`."""
    start = readme_text.find(BEGIN_MARKER)
    end = readme_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f'README is missing the {BEGIN_MARKER} / {END_MARKER} marker pair')
    head = readme_text[: start + len(BEGIN_MARKER)]
    tail = readme_text[end:]
    return f'{head}\n{table}\n{tail}'
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render.py -v`
Expected: 6 passed

- [ ] **Step 5: Create `README.md` with the marker pair**

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add model_registry/render.py tests/test_render.py README.md
git commit -m "feat: generate the README model table from models.yaml"
```

---

### Task 5: CLI with validate and render commands

**Files:**
- Create: `model_registry/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_registry`, `RegistryError`, `DEFAULT_REGISTRY_PATH` from `loader`; `render_table`, `splice` from `render`.
- Produces: `main(argv: list[str] | None = None) -> int`. Exit codes: `0` success, `1` validation/render failure, `2` usage error (argparse default).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from model_registry.cli import main

VALID_ENTRY = """
- id: gemini-2.5-flash
  display_name: Gemini 2.5 Flash
  provider: google
  hosting: vertex
  region: northamerica-northeast1
  residency: canada
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: approved
  approved_on: 2026-09-16
  approval_ref: https://github.com/OWNER/model-registry/pull/1
  review_by: 2099-01-01
"""


def test_validate_passes_on_good_registry(tmp_path: Path, capsys):
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    assert main(['validate', '--registry', str(registry)]) == 0
    assert 'gemini-2.5-flash' not in capsys.readouterr().err


def test_validate_fails_on_bad_registry(tmp_path: Path, capsys):
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('residency: canada', 'residency: mars'))
    assert main(['validate', '--registry', str(registry)]) == 1
    assert 'gemini-2.5-flash' in capsys.readouterr().err


def test_render_writes_the_table(tmp_path: Path):
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['render', '--registry', str(registry), '--readme', str(readme)]) == 0
    assert '`gemini-2.5-flash`' in readme.read_text()


def test_render_check_fails_when_readme_is_stale(tmp_path: Path):
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['render', '--registry', str(registry), '--readme', str(readme), '--check']) == 1


def test_render_check_passes_when_readme_is_current(tmp_path: Path):
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    main(['render', '--registry', str(registry), '--readme', str(readme)])
    assert main(['render', '--registry', str(registry), '--readme', str(readme), '--check']) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.cli'`

- [ ] **Step 3: Write `model_registry/cli.py`**

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_registry.loader import DEFAULT_REGISTRY_PATH, RegistryError, load_registry
from model_registry.render import render_table, splice

DEFAULT_README_PATH = Path(__file__).resolve().parent.parent / 'README.md'


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='model-registry', description='Nesto approved-model registry.')
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY_PATH, help='path to models.yaml')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('validate', help='validate models.yaml')

    render_parser = subparsers.add_parser('render', help='regenerate the README table')
    render_parser.add_argument('--readme', type=Path, default=DEFAULT_README_PATH)
    render_parser.add_argument(
        '--check',
        action='store_true',
        help='fail instead of writing when the README is out of date',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except RegistryError as exc:
        sys.stderr.write(f'registry invalid: {exc}\n')
        return 1

    if args.command == 'validate':
        sys.stdout.write(f'{len(registry.models)} models, registry valid\n')
        return 0

    if args.command == 'render':
        current = args.readme.read_text()
        try:
            updated = splice(current, render_table(registry))
        except ValueError as exc:
            sys.stderr.write(f'{exc}\n')
            return 1
        if args.check:
            if updated != current:
                sys.stderr.write('README table is out of date; run `make render` and commit the result\n')
                return 1
            return 0
        args.readme.write_text(updated)
        sys.stdout.write(f'rendered {len(registry.models)} models into {args.readme}\n')
        return 0

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 5 passed

- [ ] **Step 5: Render the real README and verify the full gate**

Run: `uv run model-registry render && uv run model-registry render --check && make check`
Expected: the README table fills with the 10 seed models; `--check` returns 0; `make check` passes end to end.

- [ ] **Step 6: Commit**

```bash
git add model_registry/cli.py tests/test_cli.py README.md
git commit -m "feat: model-registry CLI with validate and render"
```

---

### Task 6: Source scanner

**Files:**
- Create: `model_registry/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `Registry` from `loader`; `Status` from `schema`.
- Produces: `Severity` (`StrEnum`: `BLOCK = 'block'`, `WARN = 'warn'`); `Finding` (frozen dataclass: `path: str`, `line_no: int`, `model_id: str`, `reason: str`, `severity: Severity`); `scan_diff(diff_text: str, registry: Registry, excluded_globs: tuple[str, ...] = DEFAULT_EXCLUDES, unknown_severity: Severity = Severity.WARN) -> list[Finding]`; `DEFAULT_EXCLUDES: tuple[str, ...]`.

Why diff-only: scanning a whole repo would fail every PR for pre-existing model IDs. Scanning added lines means adoption does not require fixing history first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan.py`:

```python
from __future__ import annotations

from datetime import date

import pytest

from model_registry.loader import Registry, ResolvedModel
from model_registry.policy import Tier
from model_registry.scan import Severity, scan_diff
from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _resolved(model_id: str, status: Status) -> ResolvedModel:
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
        approval_ref='https://github.com/OWNER/model-registry/pull/1',
        review_by=date(2099, 1, 1),
        replacement='gemini-3.5-flash' if status is Status.DEPRECATED else None,
    )
    return ResolvedModel(entry=entry, tiers=frozenset({Tier.STANDARD}))


@pytest.fixture
def registry() -> Registry:
    return Registry(
        models=(
            _resolved('gemini-3.5-flash', Status.APPROVED),
            _resolved('gemini-2.5-pro', Status.DEPRECATED),
            _resolved('gpt-4o', Status.BANNED),
        ),
    )


def _diff(path: str, *added: str) -> str:
    body = '\n'.join(f'+{line}' for line in added)
    return f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,0 +1,{len(added)} @@\n{body}\n'


def test_approved_model_produces_no_finding(registry: Registry):
    assert scan_diff(_diff('app.py', "MODEL = 'gemini-3.5-flash'"), registry) == []


def test_deprecated_model_blocks(registry: Registry):
    findings = scan_diff(_diff('app.py', "MODEL = 'gemini-2.5-pro'"), registry)
    assert len(findings) == 1
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'deprecated'


def test_banned_model_blocks(registry: Registry):
    findings = scan_diff(_diff('app.py', "MODEL = 'gpt-4o'"), registry)
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'banned'


def test_unknown_model_warns_by_default(registry: Registry):
    findings = scan_diff(_diff('app.py', "MODEL = 'gemini-9.9-turbo'"), registry)
    assert findings[0].severity is Severity.WARN
    assert findings[0].reason == 'unknown'


def test_unknown_model_can_be_escalated_to_block(registry: Registry):
    findings = scan_diff(
        _diff('app.py', "MODEL = 'gemini-9.9-turbo'"),
        registry,
        unknown_severity=Severity.BLOCK,
    )
    assert findings[0].severity is Severity.BLOCK


def test_ignore_comment_suppresses_the_finding(registry: Registry):
    diff = _diff('app.py', "MODEL = 'gemini-2.5-pro'  # model-registry: ignore benchmarking only")
    assert scan_diff(diff, registry) == []


def test_excluded_paths_are_skipped(registry: Registry):
    assert scan_diff(_diff('accuracy/report.py', "M = 'gemini-2.5-pro'"), registry) == []
    assert scan_diff(_diff('notebook.ipynb', "M = 'gemini-2.5-pro'"), registry) == []
    assert scan_diff(_diff('docs/models.md', "M = 'gemini-2.5-pro'"), registry) == []


def test_removed_lines_are_ignored(registry: Registry):
    diff = (
        'diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n'
        "@@ -1,1 +1,1 @@\n-MODEL = 'gemini-2.5-pro'\n+MODEL = 'gemini-3.5-flash'\n"
    )
    assert scan_diff(diff, registry) == []


def test_line_numbers_come_from_the_hunk_header(registry: Registry):
    diff = (
        'diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n'
        "@@ -40,0 +42,2 @@\n+# comment\n+MODEL = 'gpt-4o'\n"
    )
    findings = scan_diff(diff, registry)
    assert findings[0].line_no == 43


def test_multiple_models_on_one_line_each_report(registry: Registry):
    diff = _diff('app.py', "PAIR = ('gemini-2.5-pro', 'gpt-4o')")
    assert {finding.model_id for finding in scan_diff(diff, registry)} == {'gemini-2.5-pro', 'gpt-4o'}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.scan'`

- [ ] **Step 3: Write `model_registry/scan.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch

from model_registry.loader import Registry
from model_registry.schema import Status

#: Paths where naming a model is legitimate rather than a usage decision:
#: evaluation notebooks and reports name rejected models on purpose.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    '*.ipynb',
    'accuracy/*',
    '*/accuracy/*',
    'docs/*',
    '*/docs/*',
    'CHANGELOG*',
    '*.lock',
)

#: Deliberately loose: it is better to warn on a non-model string than to miss a
#: real model ID. False positives are silenced with the ignore comment.
_CANDIDATE = re.compile(r'\b(?:gemini|gpt|text-embedding|claude)[-\w.]*\b', re.IGNORECASE)
_IGNORE = re.compile(r'model-registry:\s*ignore')
_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
_TARGET_FILE = re.compile(r'^\+\+\+ b/(.+)$')


class Severity(StrEnum):
    BLOCK = 'block'
    WARN = 'warn'


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int
    model_id: str
    reason: str
    severity: Severity

    def format(self) -> str:
        return f'{self.path}:{self.line_no}: {self.severity.value}: {self.model_id} is {self.reason}'


def _is_excluded(path: str, excluded_globs: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pattern) for pattern in excluded_globs)


def _classify(
    model_id: str,
    registry: Registry,
    unknown_severity: Severity,
) -> tuple[str, Severity] | None:
    resolved = registry.by_id(model_id)
    if resolved is None:
        return ('unknown', unknown_severity)
    if resolved.entry.status is Status.DEPRECATED:
        return ('deprecated', Severity.BLOCK)
    if resolved.entry.status is Status.BANNED:
        return ('banned', Severity.BLOCK)
    return None


def scan_diff(
    diff_text: str,
    registry: Registry,
    excluded_globs: tuple[str, ...] = DEFAULT_EXCLUDES,
    unknown_severity: Severity = Severity.WARN,
) -> list[Finding]:
    """Report model IDs introduced by added lines in a unified diff.

    Only added lines are examined, so adopting the check does not require a repo to
    first clean up model IDs it already contains.
    """
    findings: list[Finding] = []
    path = ''
    skip_file = True
    line_no = 0

    for raw_line in diff_text.splitlines():
        target = _TARGET_FILE.match(raw_line)
        if target:
            path = target.group(1)
            skip_file = _is_excluded(path, excluded_globs)
            continue

        hunk = _HUNK.match(raw_line)
        if hunk:
            line_no = int(hunk.group(1))
            continue

        if raw_line.startswith('-') or raw_line.startswith('---'):
            continue

        if not raw_line.startswith('+'):
            line_no += 1
            continue

        content = raw_line[1:]
        if not skip_file and not _IGNORE.search(content):
            findings.extend(_scan_line(content, path, line_no, registry, unknown_severity))
        line_no += 1

    return findings


def _scan_line(
    content: str,
    path: str,
    line_no: int,
    registry: Registry,
    unknown_severity: Severity,
) -> list[Finding]:
    found: list[Finding] = []
    for match in _CANDIDATE.finditer(content):
        model_id = match.group(0)
        classification = _classify(model_id, registry, unknown_severity)
        if classification is None:
            continue
        reason, severity = classification
        found.append(
            Finding(path=path, line_no=line_no, model_id=model_id, reason=reason, severity=severity),
        )
    return found
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_scan.py -v`
Expected: 10 passed

- [ ] **Step 5: Add the `scan` subcommand to `cli.py`**

In `_build_parser()`, after the `render` parser:

```python
    scan_parser = subparsers.add_parser('scan', help='scan a unified diff on stdin for model IDs')
    scan_parser.add_argument(
        '--block-unknown',
        action='store_true',
        help='treat unregistered model IDs as blocking rather than warnings',
    )
```

In `main()`, before the final `return 0`:

```python
    if args.command == 'scan':
        diff_text = sys.stdin.read()
        severity = Severity.BLOCK if args.block_unknown else Severity.WARN
        findings = scan_diff(diff_text, registry, unknown_severity=severity)
        for finding in findings:
            sys.stderr.write(f'{finding.format()}\n')
        if any(finding.severity is Severity.BLOCK for finding in findings):
            sys.stderr.write('\nSee the approved list: https://github.com/OWNER/model-registry\n')
            return 1
        sys.stdout.write(f'{len(findings)} warning(s), no blocking model usage\n')
        return 0
```

Add to the imports at the top of `cli.py`:

```python
from model_registry.scan import Severity, scan_diff
```

- [ ] **Step 6: Add a CLI test for scan**

Append to `tests/test_cli.py`:

```python
def test_scan_blocks_on_banned_model(tmp_path: Path, monkeypatch, capsys):
    import io

    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('status: approved', 'status: banned'))
    diff = (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
        "@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-flash'\n"
    )
    monkeypatch.setattr('sys.stdin', io.StringIO(diff))

    assert main(['scan', '--registry', str(registry)]) == 1
    assert 'banned' in capsys.readouterr().err
```

- [ ] **Step 7: Run the full suite**

Run: `make check`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add model_registry/scan.py model_registry/cli.py tests/test_scan.py tests/test_cli.py
git commit -m "feat: scan added diff lines for unapproved model IDs"
```

---

### Task 7: Composite GitHub Action for consumer repos

**Files:**
- Create: `action.yml`, `docs/adopting.md`
- Test: manual verification against a real diff (documented below)

**Interfaces:**
- Consumes: the `model-registry` CLI installed from this repo.
- Produces: an action consumer repos reference as `OWNER/model-registry@v1`.

**Prerequisite:** the repo must be **public** for nesto-org repos to reference this action. If it stays private, consumers must instead `pip install` from a git URL with a token — `docs/adopting.md` covers both.

- [ ] **Step 1: Create `action.yml`**

```yaml
name: Model Registry Check
description: Fail a PR that introduces a model ID that is not approved in the Nesto model registry.

inputs:
  block-unknown:
    description: Treat unregistered model IDs as blocking rather than warnings.
    required: false
    default: 'false'
  registry-ref:
    description: Git ref of the model-registry repo to check against.
    required: false
    default: main

runs:
  using: composite
  steps:
    - name: Check out the registry
      uses: actions/checkout@v4
      with:
        repository: OWNER/model-registry
        ref: ${{ inputs.registry-ref }}
        path: .model-registry

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install the registry CLI
      shell: bash
      run: pip install ./.model-registry

    - name: Scan the pull request diff
      shell: bash
      env:
        BLOCK_UNKNOWN: ${{ inputs.block-unknown }}
      run: |
        set -euo pipefail
        BASE="${{ github.event.pull_request.base.sha }}"
        HEAD="${{ github.event.pull_request.head.sha }}"
        FLAGS=""
        if [ "$BLOCK_UNKNOWN" = "true" ]; then FLAGS="--block-unknown"; fi
        git diff "$BASE" "$HEAD" \
          | model-registry scan --registry .model-registry/models.yaml $FLAGS
```

Note the scan reads the diff from stdin, so the action needs no temporary files.

- [ ] **Step 2: Verify the action logic locally against a real repo**

Run:
```bash
cd ../documents-extractor && git diff HEAD~5 HEAD | uv run --project ../model-registry model-registry scan --registry ../model-registry/models.yaml
```
Expected: exit 0 with a warning count. If it reports dozens of warnings, tighten `DEFAULT_EXCLUDES` in `scan.py` and re-run — this is the calibration step for the heuristic, and it is expected to need one round.

- [ ] **Step 3: Write `docs/adopting.md`**

```markdown
# Adopting the model registry check

Add `.github/workflows/model-registry.yml` to your repo:

```yaml
name: Model Registry
on: pull_request

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the scan needs both sides of the diff
      - uses: OWNER/model-registry@v1
        with:
          block-unknown: 'false'   # start in warn mode
```

## Rollout order

1. Land it with `block-unknown: 'false'`. Unregistered models warn; deprecated and
   banned models block immediately.
2. Watch a week of PRs. Every legitimate warning means a model missing from the
   registry — add it.
3. Flip to `block-unknown: 'true'` once the warnings stop.

## Silencing a false positive

Append `# model-registry: ignore <reason>` to the line. Use it for strings that
merely look like model IDs, not to skip an approval.

## If this repo is private

Replace the `uses:` step with a direct install:

```yaml
      - run: pip install "git+https://x-access-token:${{ secrets.REGISTRY_TOKEN }}@github.com/OWNER/model-registry.git"
      - run: git diff ${{ github.event.pull_request.base.sha }} ${{ github.event.pull_request.head.sha }} | model-registry scan
```
```

- [ ] **Step 4: Commit**

```bash
git add action.yml docs/adopting.md
git commit -m "feat: composite action so consumer repos can run the scan"
```

---

### Task 8: Gateway drift check

**Files:**
- Create: `model_registry/drift.py`
- Test: `tests/test_drift.py`

**Interfaces:**
- Consumes: `Registry` from `loader`; `Tier` from `policy`.
- Produces: `DriftKind` (`StrEnum`: `SERVED_NOT_APPROVED`, `APPROVED_NOT_SERVED`); `DriftItem` (frozen dataclass: `kind: DriftKind`, `model_id: str`, `detail: str`); `DriftReport` (frozen dataclass: `items: tuple[DriftItem, ...]`, `models_checked: int`, property `is_clean: bool`); `GatewayUnreachableError(Exception)`; `fetch_served_models(base_url: str, api_key: str, client: httpx.Client | None = None) -> frozenset[str]`; `compare(served: frozenset[str], registry: Registry) -> DriftReport`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_drift.py`:

```python
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
        approval_ref='https://github.com/OWNER/model-registry/pull/1',
        review_by=date(2099, 1, 1),
        replacement='beta' if status is Status.DEPRECATED else None,
    )
    return ResolvedModel(entry=entry, tiers=frozenset({Tier.STANDARD}))


def test_clean_when_served_matches_approved():
    registry = Registry(models=(_resolved('alpha'), _resolved('beta')))
    report = compare(frozenset({'alpha', 'beta'}), registry)
    assert report.is_clean
    assert report.models_checked == 2


def test_served_but_not_approved_is_drift():
    registry = Registry(models=(_resolved('alpha'),))
    report = compare(frozenset({'alpha', 'rogue'}), registry)
    assert not report.is_clean
    assert report.items[0].kind is DriftKind.SERVED_NOT_APPROVED
    assert report.items[0].model_id == 'rogue'


def test_serving_a_deprecated_model_is_drift():
    registry = Registry(models=(_resolved('alpha', Status.DEPRECATED), _resolved('beta')))
    report = compare(frozenset({'alpha', 'beta'}), registry)
    assert any(item.model_id == 'alpha' for item in report.items)


def test_approved_but_not_served_is_drift():
    registry = Registry(models=(_resolved('alpha'), _resolved('beta')))
    report = compare(frozenset({'alpha'}), registry)
    assert report.items[0].kind is DriftKind.APPROVED_NOT_SERVED
    assert report.items[0].model_id == 'beta'


def test_fetch_parses_model_info_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['authorization'] == 'Bearer key-123'
        return httpx.Response(
            200,
            json={'data': [{'model_name': 'alpha'}, {'model_name': 'beta'}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_served_models('https://gw.example', 'key-123', client=client) == frozenset({'alpha', 'beta'})


def test_fetch_raises_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayUnreachableError):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_on_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(GatewayUnreachableError):
        fetch_served_models('https://gw.example', 'key-123', client=client)


def test_fetch_raises_on_malformed_payload():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'oops': 1})))
    with pytest.raises(GatewayUnreachableError, match='unexpected'):
        fetch_served_models('https://gw.example', 'key-123', client=client)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_drift.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_registry.drift'`

- [ ] **Step 3: Write `model_registry/drift.py`**

```python
from __future__ import annotations

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
    """Read the model names the LiteLLM gateway currently serves."""
    owns_client = client is None
    active = client or httpx.Client(timeout=_TIMEOUT_SECONDS)
    try:
        response = active.get(
            f'{base_url.rstrip("/")}/model/info',
            headers={'Authorization': f'Bearer {api_key}'},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise GatewayUnreachableError(f'could not read {base_url}/model/info: {exc}') from exc
    finally:
        if owns_client:
            active.close()

    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise GatewayUnreachableError(f'unexpected /model/info payload from {base_url}')

    return frozenset(str(item['model_name']) for item in data if isinstance(item, dict) and 'model_name' in item)


def compare(served: frozenset[str], registry: Registry) -> DriftReport:
    """Compare what the gateway serves against what the registry approves."""
    items: list[DriftItem] = []

    servable = {model.entry.id for model in registry.models if model.entry.status is Status.APPROVED}

    for model_id in sorted(served - servable):
        resolved = registry.by_id(model_id)
        detail = (
            f'status is {resolved.entry.status.value}' if resolved else 'not in the registry at all'
        )
        items.append(DriftItem(kind=DriftKind.SERVED_NOT_APPROVED, model_id=model_id, detail=detail))

    for model_id in sorted(servable - served):
        items.append(
            DriftItem(
                kind=DriftKind.APPROVED_NOT_SERVED,
                model_id=model_id,
                detail='approved in the registry but the gateway does not serve it',
            ),
        )

    return DriftReport(items=tuple(items), models_checked=len(registry.models))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 8 passed

- [ ] **Step 5: Add the `drift` subcommand to `cli.py`**

In `_build_parser()`:

```python
    drift_parser = subparsers.add_parser('drift', help='compare the gateway against the registry')
    drift_parser.add_argument('--base-url', default=os.environ.get('LITELLM_GATEWAY_BASE_URL', ''))
    drift_parser.add_argument('--api-key', default=os.environ.get('LITELLM_GATEWAY_API_KEY', ''))
    drift_parser.add_argument('--json', action='store_true', help='emit JSON for a downstream reporter')
```

In `main()`, before the final `return 0`:

```python
    if args.command == 'drift':
        if not args.base_url or not args.api_key:
            sys.stderr.write('drift needs LITELLM_GATEWAY_BASE_URL and LITELLM_GATEWAY_API_KEY\n')
            return 1
        try:
            served = fetch_served_models(args.base_url, args.api_key)
        except GatewayUnreachableError as exc:
            sys.stderr.write(f'drift check failed: {exc}\n')
            return 2
        report = compare(served, registry)
        if args.json:
            sys.stdout.write(
                json.dumps({
                    'models_checked': report.models_checked,
                    'clean': report.is_clean,
                    'items': [
                        {'kind': item.kind.value, 'model_id': item.model_id, 'detail': item.detail}
                        for item in report.items
                    ],
                }) + '\n',
            )
        else:
            for item in report.items:
                sys.stdout.write(f'{item.kind.value}: {item.model_id} — {item.detail}\n')
            sys.stdout.write(f'{report.models_checked} models checked, {len(report.items)} drift item(s)\n')
        return 0 if report.is_clean else 1
```

Add to the imports at the top of `cli.py`:

```python
import json
import os

from model_registry.drift import GatewayUnreachableError, compare, fetch_served_models
```

**Exit codes matter here:** `0` clean, `1` drift found, `2` could not check. The routine in Task 9 reports `2` differently from `1` — conflating them would let a broken check look healthy.

- [ ] **Step 6: Commit**

```bash
git add model_registry/drift.py model_registry/cli.py tests/test_drift.py
git commit -m "feat: gateway drift check with distinct unreachable exit code"
```

---

### Task 9: Weekly cloud routine

**Files:**
- Create: `docs/cloud-routine.md`
- Modify: `README.md` (add a "Checks" section above the marker pair)

**Interfaces:**
- Consumes: `model-registry drift --json` and its exit codes from Task 8.
- Produces: no code — an operational document plus the routine registered via the `schedule` skill.

- [ ] **Step 1: Write `docs/cloud-routine.md`**

```markdown
# Weekly drift routine

A scheduled Claude Code routine runs the drift check and posts the result to Slack.
The check itself is deterministic Python; the routine only formats the message.

## Routine prompt

> Run the model registry drift check and report it to Slack.
>
> 1. `cd` to the model-registry checkout and run:
>    `uv run model-registry drift --json`
> 2. Read the exit code:
>    - `0` — clean. Post exactly: `model registry · N models · 0 drift`
>    - `1` — drift found. Post the count, then one line per item:
>      `<kind>: <model_id> — <detail>`. Lead with `served_not_approved` items;
>      those mean an unapproved model is callable right now.
>    - `2` — the check could not run. Post `model registry · drift check FAILED`
>      followed by the stderr line. Do not report this as clean.
> 3. Post to the maintainer's Slack DM. Keep it terse — no preamble, no summary
>    paragraph, no restating the request.

## Why it posts when clean

A check that is silent when healthy is indistinguishable from a check that is
broken. The `N models · 0 drift` heartbeat is the evidence that it ran.

## Scheduling

Register with the `schedule` skill. Weekly is the starting cadence; if the gateway
config changes more often than that, shorten it.

## Prerequisites

- The routine's environment needs `LITELLM_GATEWAY_BASE_URL` and
  `LITELLM_GATEWAY_API_KEY`, and network reachability to the gateway. If the cloud
  runner cannot reach a VPC-internal gateway, this check has to move to a GCP job
  and only the Slack formatting stays here.
```

- [ ] **Step 2: Add a "Checks" section to `README.md`**

Insert above `## Approved models`:

```markdown
## Checks

| Check | Runs | On failure |
|---|---|---|
| `make validate` | this repo's CI, every PR | the registry is malformed — merge blocked |
| `model-registry render --check` | this repo's CI, every PR | the README table is stale — run `make render` |
| `model-registry scan` | consumer repos, every PR | a PR introduces a deprecated, banned, or unknown model |
| `model-registry drift` | weekly cloud routine | the gateway serves something the registry does not approve |
```

- [ ] **Step 3: Regenerate the README and run the full gate**

Run: `uv run model-registry render && make check`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add docs/cloud-routine.md README.md
git commit -m "docs: weekly drift routine and checks overview"
```

- [ ] **Step 5: Add this repo's own CI**

Create `.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group dev
      - run: make check
      - run: uv run model-registry render --check
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the full gate and the README freshness check"
```

---

## Deferred to v2 (do not build now)

- **Runtime tenant guard in `llm-kit`.** `maestro-graphs` already resolves
  `tenant_id`/`tenant_slug` into its request context, so a tenant→tier map plus a check
  in `llm_kit.client` would fail closed when a standard-tier model serves a bank tenant.
  This is the only thing that closes the scanner's tenant blind spot.
- **Generating the LiteLLM gateway config from `models.yaml`.** The `gateway:` block
  exists in the schema for this. It would make drift structurally impossible rather
  than merely detectable.

## Human inputs still required

These block the registry being *true*, not the code being *done*:

1. Verify residency, region, and retention terms for each seed model, then flip the
   justified ones from `trial` to `approved` in a reviewed PR. Until then the registry
   grants no bank-tier access to anything.
2. Decide which of the seven in-use Gemini versions are intentional and which are
   incidental; mark the incidental ones `deprecated` with a `replacement`.
3. Provide gateway URL and credentials, and confirm the cloud runner can reach it.
4. Add the embedding models actually used for semantic similarity — none appear as
   string literals in the scanned repos, so the seed cannot infer them.
