"""Decision policy — the three-bucket rule at the core of Ambient Awareness.

Pure function of (risk, trust): no I/O, fully testable. The ambient engine calls
this to decide what to do with each classified approval.

Buckets (design Flow B):
  - AUTO_APPROVE: LOW risk AND session trust granted -> silently approve
  - AUTO_BLOCK:   an explicit deny rule matched -> silently reject
  - SURFACE:      everything else (HIGH, UNKNOWN, or LOW without trust) -> ask human

Safety invariant (NFR-1): HIGH and UNKNOWN ALWAYS surface. Trust never overrides
safety. When in doubt, SURFACE.
"""

from __future__ import annotations

from .models import DecisionAction, RiskAssessment, RiskLevel


def decide(
    risk: RiskAssessment,
    *,
    session_trust: bool = False,
    explicit_deny: bool = False,
) -> tuple[DecisionAction, str]:
    """Return (action, reason) for a classified approval.

    - explicit_deny: a bundled/opt-in deny rule already flagged this as always-block.
    - session_trust: the user opted into auto-approving low-risk steps this session.
    """
    # An explicit deny rule wins outright — silently block (R3.2, second clause).
    if explicit_deny:
        return DecisionAction.AUTO_BLOCK, "explicit deny rule"

    # HIGH and UNKNOWN must always reach a human (R3.2, R3.3). Trust cannot lower this.
    if risk.level in (RiskLevel.HIGH, RiskLevel.UNKNOWN):
        return DecisionAction.SURFACE, risk.reason or f"{risk.level} risk needs a human"

    # LOW: auto-approve only if the user granted session trust (R3.1); else surface.
    if risk.level == RiskLevel.LOW:
        if session_trust:
            return DecisionAction.AUTO_APPROVE, "low risk, session trusted"
        return DecisionAction.SURFACE, "low risk, but no session trust yet"

    # Defensive default (should be unreachable): surface.
    return DecisionAction.SURFACE, "unclassified, surfacing to be safe"
