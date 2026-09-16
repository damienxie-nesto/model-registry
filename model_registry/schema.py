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


class LaunchStage(StrEnum):
    """A model's launch stage at its provider.

    Compliance-relevant, not cosmetic: Google's data residency commitments for
    Vertex AI explicitly exclude any feature in experimental or preview launch
    status. A preview model can therefore carry a regional `region` value while
    Google makes no residency commitment about it at all, so launch stage has to
    be recorded as its own fact rather than inferred from the region.

    `UNVERIFIED` is the default so an unrecorded stage fails closed: it cannot
    satisfy the bank tier.
    """

    GA = 'ga'
    PREVIEW = 'preview'
    EXPERIMENTAL = 'experimental'
    UNVERIFIED = 'unverified'


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
    launch_stage: LaunchStage = LaunchStage.UNVERIFIED
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
