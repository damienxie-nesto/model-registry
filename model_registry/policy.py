from __future__ import annotations

from enum import StrEnum

from model_registry.schema import Hosting, ModelEntry, Residency, Status

#: Region values that record nothing. An entry carrying one of these has not had its
#: physical location verified, so it must not reach the `bank` tier however its other
#: facts read; `loader._check_bank_facts_are_recorded` enforces that on load.
PLACEHOLDER_REGIONS: frozenset[str] = frozenset({'', 'unverified', 'unknown', 'tbd'})


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
    - `bank` additionally requires a recorded `region`. That rule is not applied here
      — it is enforced at load time by `loader._check_bank_facts_are_recorded`, which
      rejects the file outright rather than silently downgrading a tier, so an entry
      whose facts contradict each other is fixed rather than quietly demoted. A
      placeholder region (see `PLACEHOLDER_REGIONS`) means nobody has verified where
      the data physically goes, which is exactly the fact the bank contracts turn on.
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
