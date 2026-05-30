"""The FROZEN integration contract between the engine and the capsule emitter.

Field names here are load-bearing: the capsule generator and the cockpit API
both depend on them. A test (test_contract.py) asserts the exact field-name
sets so a rename can never silently drift (the user has been bitten by
field-name drift between modules before).

Naming rules:
  - snake_case everywhere
  - always ``nct_id`` (never ``nct`` / ``NCT``)
  - log-scale effect is ``yi`` / ``sei`` (matches AlBurhan + EvidenceForecast)
  - CIs are ``ci_lower`` / ``ci_upper`` (canonical long form, NOT ci_lo/ci_hi)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class PICO:
    population: str
    outcome: str
    intervention: str | None = None
    comparator: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArmEffect:
    label: str
    ctgov_group_code: str | None = None
    events: int | None = None
    n: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EffectRecord:
    nct_id: str
    study_label: str
    year: int | None
    endpoint: str                  # classify_endpoint id, e.g. "acm" | "cv_death"
    measure_type: str              # "HR" | "OR" | "RR" | "MD"
    point_estimate: float | None   # raw param_value (natural scale)
    ci_lower: float | None         # reported lower CI; None if derived
    ci_upper: float | None         # reported upper CI; None if derived
    ci_percent: float | None       # e.g. 95.0
    yi: float                      # log-scale effect
    sei: float                     # log-scale standard error (>0)
    derived: bool                  # True => yi/sei reconstructed, ci_* are None
    source_nct_id: str             # == nct_id, explicit for audit
    source_outcome_id: str         # outcomes.id
    source_outcome_analysis_id: str  # outcome_analyses.id (the cited row)
    source_method: str             # outcome_analyses.method
    arm_experimental: ArmEffect | None = None
    arm_comparator: ArmEffect | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass(frozen=True)
class EffectsDataset:
    records: list[EffectRecord]
    provenance: object             # aact_engine.provenance.Provenance
    pico: PICO
    primary_estimand: str
    measure: str                   # dominant measure_type across records
    n_studies: int
    notes: list[str] = field(default_factory=list)  # guard rejections / skipped-row reasons

    def to_dict(self) -> dict:
        prov = self.provenance
        return {
            "pico": self.pico.to_dict(),
            "primary_estimand": self.primary_estimand,
            "measure": self.measure,
            "snapshot_date": getattr(prov, "snapshot_date", None),
            "provenance": prov.to_dict() if hasattr(prov, "to_dict") else dict(prov),
            "n_studies": self.n_studies,
            "studies": [r.to_dict() for r in self.records],
            "notes": list(self.notes),
        }


# The authoritative field-name sets (asserted by test_contract.py).
EFFECT_RECORD_FIELDS = frozenset(EffectRecord.__dataclass_fields__.keys())
EFFECTS_DATASET_FIELDS = frozenset(EffectsDataset.__dataclass_fields__.keys())

__all__ = [
    "PICO", "ArmEffect", "EffectRecord", "EffectsDataset",
    "EFFECT_RECORD_FIELDS", "EFFECTS_DATASET_FIELDS",
]
