"""Versioned taxonomy audit; no public surface or V1/V2 score changes."""

from benchmarks.surface_review_controls import ReviewControl
from benchmarks.surface_review_controls_v2 import build_controls as build_v2_controls

GOLD_REVISION = "review-control-gold.v3"
# The full family audit is documented in the frozen V3 plan. The only remaining
# missing temporal category is overlapping exclusive intervals; do not accept all
# categories merely to make a control pass.
TEMPORAL_CONFLICT_FAMILIES = frozenset(
    {"old_current_custody", "return_and_readoption_lifecycle"}
)


def build_controls() -> list[ReviewControl]:
    controls = []
    for original in build_v2_controls():
        codes = list(original.allowed_issue_codes)
        if (
            not original.acceptable
            and original.family in TEMPORAL_CONFLICT_FAMILIES
            and "temporal_mismatch" not in codes
        ):
            codes.append("temporal_mismatch")
        controls.append(
            original.model_copy(deep=True, update={"allowed_issue_codes": codes})
        )
    return controls
