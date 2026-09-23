"""
state.py — LangGraph state schema for the fraud investigation agent.
Every field that any node reads or writes lives here.
"""

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
import operator


class EvidenceItem(TypedDict):
    claim: str
    source: str   # graph | document | customer | external
    ref: str
    entity_ids: list[str]


class EvidenceRequest(TypedDict):
    type: str          # customer_validation | step_up_auth | analyst_info
    asked_after_step: int
    assumed_response: str


class NextBestAction(TypedDict):
    action: str
    route: str   # auto | L1 | L2
    reason: str


class SARData(TypedDict):
    file: bool
    reason: str
    narrative: str
    subjects: list[str]
    total_amount_usd: float
    activity_dates: list[str]


# ─────────────────────────────────────────────────────────────
# Main investigation state — passed between all LangGraph nodes
# ─────────────────────────────────────────────────────────────

class InvestigationState(TypedDict):
    # ── Input (set once at trigger) ──────────────────────────
    case_id: str
    hhg_case_id: str
    trigger_type: str        # risk_score | customer_report | analyst_request
    trigger_text: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    trigger_risk_score: Optional[float]

    # ── Intermediate investigation data ──────────────────────
    flagged_txn: dict                 # full transaction record
    card_history: dict                # recent transactions on the card
    card_window: dict                 # ±N hours around flagged txn
    velocity: dict                    # count/amount in window
    device_info: Optional[dict]       # DeviceProfile if online
    billing_region_history: dict      # map of region → count
    customer_profile: dict            # cards, history summary, closed cases
    similar_prior_cases: list[str]    # CC-#### IDs retrieved

    # ── Investigation progress ────────────────────────────────
    step: int                         # which investigation step we're on
    evidence: Annotated[list[EvidenceItem], operator.add]
    evidence_requests: Annotated[list[EvidenceRequest], operator.add]
    loop_count: int                   # how many times we've looped for more evidence

    # ── Verdict ───────────────────────────────────────────────
    fraud_probability: float
    verdict: str                      # fraud | legitimate | uncertain
    pattern: str                      # card_testing | card_not_present_fraud | ...
    pattern_description: str

    # ── Affected scope ────────────────────────────────────────
    affected_txn_ids: list[str]
    first_suspicious_txn_id: str
    connected_card_ids: list[str]
    connected_device_profiles: list[str]
    exposure_usd: float

    # ── Case record ───────────────────────────────────────────
    case_status: str                  # open | closed_fraud | closed_legitimate | escalated
    summary: str
    written_to_graph: bool
    graph_case_id: str

    # ── Actions ───────────────────────────────────────────────
    initial_actions: list[NextBestAction]
    final_actions: list[NextBestAction]
    what_changed: str

    # ── SAR ───────────────────────────────────────────────────
    sar: Optional[SARData]

    # ── Stopping ─────────────────────────────────────────────
    stop_reason: str
    should_stop: bool

    # ── Telemetry ─────────────────────────────────────────────
    tool_calls: int
    tokens_used: int
    start_time: float


def initial_state(case_row: dict) -> InvestigationState:
    """Build starting state from a case_pack.csv row."""
    import time
    risk_score_raw = case_row.get("risk_score", "")
    try:
        risk_score = float(risk_score_raw) if risk_score_raw else None
    except (ValueError, TypeError):
        risk_score = None

    return InvestigationState(
        case_id=f"CASE-{case_row['case_id']}",
        hhg_case_id=case_row["case_id"],
        trigger_type=case_row["trigger_type"],
        trigger_text=case_row["trigger_text"],
        flagged_txn_id=str(case_row["flagged_txn_id"]),
        card_id=case_row["card_id"],
        customer_id=case_row["customer_id"],
        trigger_risk_score=risk_score,

        flagged_txn={},
        card_history={},
        card_window={},
        velocity={},
        device_info=None,
        billing_region_history={},
        customer_profile={},
        similar_prior_cases=[],

        step=0,
        evidence=[],
        evidence_requests=[],
        loop_count=0,

        fraud_probability=0.5,
        verdict="uncertain",
        pattern="none",
        pattern_description="",

        affected_txn_ids=[],
        first_suspicious_txn_id="",
        connected_card_ids=[],
        connected_device_profiles=[],
        exposure_usd=0.0,

        case_status="open",
        summary="",
        written_to_graph=False,
        graph_case_id="",

        initial_actions=[],
        final_actions=[],
        what_changed="nothing",

        sar=None,

        stop_reason="",
        should_stop=False,

        tool_calls=0,
        tokens_used=0,
        start_time=time.time(),
    )
