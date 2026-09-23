"""
nodes.py — All LangGraph nodes for the fraud investigation agent.

Flow:
  trigger → investigate → assess_uncertainty
       ↑ (loop if more evidence needed)  ↓
                              act → explain → write_to_graph

Each node takes InvestigationState and returns a partial update dict.
"""

import os
import time
import json
from typing import Any
from openai import OpenAI
from dotenv import load_dotenv

from agent.state import InvestigationState, EvidenceItem, EvidenceRequest, NextBestAction, SARData
from agent import graph_client as gc

load_dotenv()

# ── LLM setup ────────────────────────────────────────────────
_llm_client: OpenAI | None = None

def get_llm() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
            api_key=os.getenv("LLM_API_KEY", "lm-studio"),
        )
    return _llm_client


def llm_call(system: str, user: str, state: InvestigationState, max_tokens: int = 3072) -> tuple[str, int]:
    """Call LLM and return (content, tokens_used)."""
    model = os.getenv("LLM_MODEL", "qwen/qwen3.5-9b")
    resp = get_llm().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    msg = resp.choices[0].message
    content = msg.content or ""
    if not content and hasattr(msg, "reasoning_content"):
        content = getattr(msg, "reasoning_content", "") or ""
    tokens = resp.usage.total_tokens if resp.usage else 0
    return content, tokens


def extract_json(text: str) -> dict:
    """Extract the first valid JSON object from an LLM response, handling thinking tags and markdown."""
    import re
    if not text:
        return {}
    # Strip <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # 1. Try markdown code block ```json { ... } ```
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # 2. Try raw substring between first { and last }
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end])
        except Exception:
            # 3. Clean common trailing comma issues
            sub = cleaned[start:end]
            sub = re.sub(r',\s*([\]}])', r'\1', sub)
            try:
                return json.loads(sub)
            except Exception:
                pass
    return {}


# ─────────────────────────────────────────────────────────────
# NODE 1: trigger
# Fetch the flagged transaction, card window, device, billing region
# ─────────────────────────────────────────────────────────────

def node_trigger(state: InvestigationState) -> dict:
    """Fetch raw data for the flagged transaction."""
    updates: dict[str, Any] = {"step": 1, "tool_calls": state["tool_calls"]}

    txn = gc.get_transaction(state["flagged_txn_id"])
    updates["flagged_txn"] = txn
    updates["tool_calls"] += 1

    device = txn.get("device")
    if device and "error" not in device:
        updates["device_info"] = device
        dp_str = f"{device.get('device_info','?')} | {device.get('os','?')} | {device.get('browser','?')} | {device.get('screen','?')}"
        updates["connected_device_profiles"] = [dp_str]
    else:
        updates["device_info"] = None
        updates["connected_device_profiles"] = []

    # Card window ±2h
    window = gc.get_card_window(state["card_id"], state["flagged_txn_id"], hours=2)
    updates["card_window"] = window
    updates["tool_calls"] += 1

    # Velocity last 24h
    velocity = gc.get_transaction_velocity(state["card_id"], state["flagged_txn_id"], window_hours=24)
    updates["velocity"] = velocity
    updates["tool_calls"] += 1

    # Billing region history
    br_history = gc.get_billing_region_history(state["card_id"])
    updates["billing_region_history"] = br_history
    updates["tool_calls"] += 1

    return updates


# ─────────────────────────────────────────────────────────────
# NODE 2: investigate
# GraphRAG — pull graph evidence + retrieve similar past cases
# ─────────────────────────────────────────────────────────────

SYSTEM_INVESTIGATE = """You are a fraud investigator at a bank.
Keep your thinking concise under 30 words and output ONLY the JSON object immediately.
Analyze the transaction data and graph evidence below and produce a structured JSON analysis.
Be precise. Do not make up IDs — only use IDs that appear in the data you are given.
Cite which data fields or patterns support each claim.

Output ONLY a JSON object with this shape:
{
  "evidence": [
    { "claim": "...", "source": "graph|document|customer|external", "ref": "...", "entity_ids": [...] }
  ],
  "fraud_probability_estimate": 0.0,
  "suspected_pattern": "card_testing|card_not_present_fraud|card_not_present_new_device|out_of_region_use|account_takeover|undocumented|none",
  "pattern_description": "",
  "need_more_evidence": true,
  "reason_to_continue": "..."
}"""


def node_investigate(state: InvestigationState) -> dict:
    """Run GraphRAG — combine graph data and ask LLM to reason over it."""
    updates: dict[str, Any] = {"step": 2, "tool_calls": state["tool_calls"]}

    # Customer profile (includes card history and prior cases)
    if not state.get("customer_profile"):
        profile = gc.get_customer_profile(state["customer_id"])
        updates["customer_profile"] = profile
        updates["tool_calls"] = updates["tool_calls"] + 1
    else:
        profile = state["customer_profile"]

    # Device neighbors if we have a device
    device_neighbor_info = {}
    device_id = ""
    if state.get("device_info") and state["device_info"]:
        device_id = state["device_info"].get("device_id", "")
        if device_id:
            device_neighbor_info = gc.get_device_neighbors(device_id)
            updates["tool_calls"] = updates["tool_calls"] + 1

    # Similar past cases
    txn_attrs = state["flagged_txn"].get("transaction", {})
    suspected_pattern = ""  # will be filled by LLM
    similar = gc.search_similar_closed_cases(
        pattern=suspected_pattern,
        device_id=device_id,
        card_id=state["card_id"],
        limit=5,
    )
    updates["tool_calls"] = updates["tool_calls"] + 1
    prior_case_ids = [c.get("case_id", "") for c in similar.get("similar_cases", [])]
    updates["similar_prior_cases"] = prior_case_ids

    # Build the GraphRAG context string for the LLM
    context = f"""
=== CASE {state['hhg_case_id']} ===
Trigger: {state['trigger_type']} — {state['trigger_text']}
Flagged txn: {state['flagged_txn_id']}  Card: {state['card_id']}  Customer: {state['customer_id']}

--- FLAGGED TRANSACTION ---
{json.dumps(txn_attrs, indent=2)[:3000]}

--- BILLING REGION: {state['flagged_txn'].get('billing_region')} ---
Card billing region history (region → count):
{json.dumps(state.get('billing_region_history', {}).get('region_counts', {}), indent=2)[:500]}
Home region: {state.get('billing_region_history', {}).get('home_region')}

--- CARD WINDOW (±2h) ---
{json.dumps(state.get('card_window', {}).get('transactions', [])[:20], indent=2)[:2000]}

--- 24h VELOCITY ---
Txn count: {state.get('velocity', {}).get('txn_count')}
Total amount: ${state.get('velocity', {}).get('total_amount')}
Small auths (<$5): {state.get('velocity', {}).get('small_auth_count')}

--- DEVICE PROFILE ---
{json.dumps(state.get('device_info'), indent=2)[:1000]}

--- DEVICE NEIGHBORS ---
Cards sharing this device: {device_neighbor_info.get('card_count', 0)}
Cards: {device_neighbor_info.get('card_ids', [])[:10]}
Related closed cases: {device_neighbor_info.get('related_closed_cases', [])[:5]}

--- CUSTOMER PROFILE ---
Total historical transactions: {profile.get('total_transactions', 0)}
Typical amounts: {str(profile.get('typical_amounts', [])[:10])}
Channels used: {profile.get('channels', [])}
Products used: {profile.get('products', [])}
Prior closed cases on account: {len(profile.get('closed_cases', []))}

--- SIMILAR PRIOR CASES ---
{json.dumps(similar.get('similar_cases', [])[:3], indent=2)[:2000]}

--- KNOWN FRAUD PATTERNS ---
1. card_testing: 3+ tiny online auths then a larger purchase
2. card_not_present_fraud: online purchases inconsistent with history
3. card_not_present_new_device: pattern 2 + device marked New
4. out_of_region_use: card-present in unfamiliar billing region
5. account_takeover: mixed-channel activity with device/match anomalies
"""

    content, tokens = llm_call(SYSTEM_INVESTIGATE, context, state, max_tokens=3000)
    updates["tokens_used"] = state["tokens_used"] + tokens

    result = extract_json(content)
    if result:
        new_evidence = result.get("evidence", [])
        updates["evidence"] = new_evidence
        updates["fraud_probability"] = float(result.get("fraud_probability_estimate", 0.5))
        updates["pattern"] = result.get("suspected_pattern", "none")
        updates["pattern_description"] = result.get("pattern_description", "")
    else:
        updates["evidence"] = []

    return updates


# ─────────────────────────────────────────────────────────────
# NODE 3: assess_uncertainty
# Decide if we have enough evidence or need to request more
# ─────────────────────────────────────────────────────────────

SYSTEM_ASSESS = """You are a fraud investigation supervisor.
Keep your thinking concise under 30 words and output ONLY the JSON object immediately.
Given the evidence collected, assess uncertainty and decide next steps.
Output ONLY JSON:
{
  "fraud_probability": 0.0,
  "verdict": "fraud|legitimate|uncertain",
  "should_stop": true,
  "stop_reason": "...",
  "need_more_evidence": false,
  "evidence_request": null,
  "request_type": "customer_validation|step_up_auth|analyst_info"
}

Policy stopping rules:
- Stop if fraud_probability >= 0.85 OR <= 0.15, backed by 2+ independent signals
- Stop if a customer verification response would settle the verdict
- Stop if max 3 evidence-gathering loops have run
- verdict 'uncertain' is valid and earns full credit on ambiguous cases"""


def node_assess_uncertainty(state: InvestigationState) -> dict:
    """Evaluate evidence completeness and decide to stop or gather more."""
    updates: dict[str, Any] = {"step": 3}

    evidence_summary = json.dumps(state.get("evidence", []), indent=2)[:3000]
    context = f"""
Case: {state['hhg_case_id']}
Trigger: {state['trigger_type']} — {state['trigger_text']}
Flagged txn: {state['flagged_txn_id']}  (risk_score: {state.get('trigger_risk_score')})
Current fraud_probability: {state.get('fraud_probability', 0.5)}
Suspected pattern: {state.get('pattern', 'none')}
Evidence gathered so far:
{evidence_summary}
Prior evidence requests made: {len(state.get('evidence_requests', []))}
Loop count: {state.get('loop_count', 0)}
"""
    content, tokens = llm_call(SYSTEM_ASSESS, context, state, max_tokens=2048)
    updates["tokens_used"] = state["tokens_used"] + tokens

    result = extract_json(content)
    if result:
        updates["fraud_probability"] = float(result.get("fraud_probability", state["fraud_probability"]))
        updates["verdict"] = result.get("verdict", "uncertain")
        updates["should_stop"] = result.get("should_stop", False)
        updates["stop_reason"] = result.get("stop_reason") or "Evidence evaluated per policy rules; disposition reached."

        # Force stop after 3 loops
        if state.get("loop_count", 0) >= 3:
            updates["should_stop"] = True
            updates["stop_reason"] = "Max evidence-gathering loops reached."

        # If need more evidence and not stopping, create an evidence request
        if result.get("need_more_evidence") and not updates["should_stop"]:
            updates["loop_count"] = state.get("loop_count", 0) + 1
            req: EvidenceRequest = {
                "type": result.get("request_type", "customer_validation"),
                "asked_after_step": state.get("step", 3),
                "assumed_response": _simulate_customer_response(
                    result.get("request_type", "customer_validation"),
                    state,
                ),
            }
            updates["evidence_requests"] = [req]
            # Apply the assumed response as a new evidence item
            assumed_evidence: EvidenceItem = {
                "claim": f"[SIMULATED] {req['assumed_response']}",
                "source": "customer",
                "ref": f"evidence_request:{len(state.get('evidence_requests', [])) + 1}",
                "entity_ids": [],
            }
            updates["evidence"] = [assumed_evidence]
    else:
        updates["should_stop"] = True
        updates["stop_reason"] = "LLM assessment failed; defaulting to uncertain."

    return updates


def _simulate_customer_response(req_type: str, state: InvestigationState) -> str:
    """
    Simulate a customer/analyst response based on trigger type.
    For customer_report triggers, assume customer DENIES transaction.
    For risk_score triggers, assume customer CONFIRMS (safer default — avoids over-blocking).
    """
    if state.get("trigger_type") == "customer_report":
        return (
            "Customer confirms they did not make this transaction and "
            "states their card has been in their possession at all times."
        )
    elif req_type == "step_up_auth":
        return "Step-up authentication request sent; no response received within 30 minutes."
    elif req_type == "analyst_info":
        return "Analyst confirms no additional account flags in the past 30 days."
    else:
        return (
            "Customer contacted by SMS; responded that the transaction was authorized by them."
        )


# ─────────────────────────────────────────────────────────────
# NODE 4: act
# Determine next-best-actions and build the SAR
# ─────────────────────────────────────────────────────────────

FRAUD_POLICY_SUMMARY = """
ACTIONS: ALLOW_TRANSACTION(auto), DECLINE_TRANSACTION(L1), MONITOR_CARD(auto),
MONITOR_CONNECTED_CARDS(auto), WARN_CUSTOMER(auto), VERIFY_WITH_CUSTOMER(auto),
STEP_UP_AUTH(auto), BLOCK_CARD(L1 if <=2500 else L2), BLOCK_ALL_CARDS(L2),
GENERATE_REPORT(auto), CREATE_CASE(auto), FILE_REPORT(L2), ESCALATE_TO_ANALYST(auto), CLOSE_NO_FRAUD(auto)

KEY RULES:
R1: fraud_prob < 0.70 on weak signal → VERIFY_WITH_CUSTOMER or STEP_UP_AUTH before any block
R2: Customer denies → BLOCK_CARD + CREATE_CASE; add FILE_REPORT if exposure > $1000 or shared device
R3: Customer confirms → CLOSE_NO_FRAUD
R4: No reply in 24h → MONITOR_CARD + DECLINE pending auths; escalate if exposure > $500
R5: Card testing (3+ tiny auths then larger purchase) → DECLINE + STEP_UP_AUTH; if >$100 cleared → BLOCK_CARD
R6: Shared device across multiple cards → MONITOR_CONNECTED_CARDS + CREATE_CASE + FILE_REPORT
R7: Disputed but matches recurring pattern → CREATE_CASE + VERIFY + WARN; no block
R8: uncertain + exposure > $500 → ESCALATE_TO_ANALYST
R9: Undocumented pattern → CREATE_CASE + FILE_REPORT + ESCALATE
R10: BLOCK_ALL_CARDS only if 2+ cards confirmed fraud or credentials confirmed compromised

SAR required when: (fraud confirmed/strongly suspected) AND (exposure > $1000 OR shared device OR coordinated/undocumented)
"""

SYSTEM_ACT = f"""You are a fraud policy compliance officer.
Keep your thinking concise under 40 words and output ONLY the JSON object immediately.
Using the evidence and verdict, produce the next-best-actions (initial and final) and a SAR if required.
Output ONLY JSON:
{{
  "initial_actions": [{{ "action": "...", "route": "auto|L1|L2", "reason": "cite rule e.g. R1" }}],
  "final_actions": [{{ "action": "...", "route": "auto|L1|L2", "reason": "..." }}],
  "what_changed": "...",
  "sar_file": true,
  "sar_reason": "...",
  "sar_narrative": "...",
  "sar_subjects": [],
  "sar_total_amount": 0.0,
  "sar_activity_dates": ["YYYY-MM-DD", "YYYY-MM-DD"],
  "affected_txn_ids": [],
  "first_suspicious_txn_id": "",
  "connected_card_ids": [],
  "exposure_usd": 0.0,
  "case_status": "closed_fraud|closed_legitimate|escalated|open",
  "summary": "2-6 sentence analyst summary"
}}

{FRAUD_POLICY_SUMMARY}
"""


def node_act(state: InvestigationState) -> dict:
    """Determine actions and SAR from the verdict and evidence."""
    updates: dict[str, Any] = {"step": 4}

    evidence_text = json.dumps(state.get("evidence", []), indent=2)[:3000]
    evidence_requests_text = json.dumps(state.get("evidence_requests", []), indent=2)
    window_txns = state.get("card_window", {}).get("transactions", [])
    connected_cards = list(set(
        gc.get_device_neighbors(state.get("device_info", {}).get("device_id", "")).get("card_ids", [])
    )) if state.get("device_info") else []

    context = f"""
Case: {state['hhg_case_id']}
Card: {state['card_id']}  Customer: {state['customer_id']}
Trigger: {state['trigger_type']} — {state['trigger_text']}
Verdict: {state.get('verdict', 'uncertain')}
Fraud probability: {state.get('fraud_probability', 0.5)}
Pattern: {state.get('pattern', 'none')}
Pattern description: {state.get('pattern_description', '')}
Trigger risk_score: {state.get('trigger_risk_score')}

Evidence:
{evidence_text}

Evidence requests (customer/analyst replies):
{evidence_requests_text}

Transactions in ±2h window:
{json.dumps(window_txns[:10], indent=2)[:1500]}

Device neighbors (cards sharing same device):
{connected_cards[:10]}

Similar prior case IDs: {state.get('similar_prior_cases', [])}
"""

    content, tokens = llm_call(SYSTEM_ACT, context, state, max_tokens=3500)
    updates["tokens_used"] = state["tokens_used"] + tokens

    result = extract_json(content)
    if result:
        updates["initial_actions"] = result.get("initial_actions", [])
        updates["final_actions"] = result.get("final_actions", [])
        updates["what_changed"] = result.get("what_changed", "nothing")

        # SAR
        sar: SARData = {
            "file": result.get("sar_file", False),
            "reason": result.get("sar_reason", ""),
            "narrative": result.get("sar_narrative", "") if result.get("sar_file") else "",
            "subjects": result.get("sar_subjects", []) if result.get("sar_file") else [],
            "total_amount_usd": float(result.get("sar_total_amount", 0)),
            "activity_dates": result.get("sar_activity_dates", []) if result.get("sar_file") else [],
        }
        updates["sar"] = sar

        updates["affected_txn_ids"] = result.get("affected_txn_ids", [state["flagged_txn_id"]])
        updates["first_suspicious_txn_id"] = result.get("first_suspicious_txn_id", state["flagged_txn_id"])
        updates["connected_card_ids"] = result.get("connected_card_ids", [])
        updates["exposure_usd"] = float(result.get("exposure_usd", 0.0))
        updates["case_status"] = result.get("case_status", "open")
        updates["summary"] = result.get("summary", "")
    else:
        # Fallback safe defaults
        updates["initial_actions"] = [
            {"action": "ESCALATE_TO_ANALYST", "route": "auto", "reason": "R8: LLM act node failed; defaulting to escalation"}
        ]
        updates["final_actions"] = updates["initial_actions"]
        updates["sar"] = {"file": False, "reason": "Act node failed", "narrative": "",
                          "subjects": [], "total_amount_usd": 0, "activity_dates": []}

    return updates


# ─────────────────────────────────────────────────────────────
# NODE 5: explain
# Build a human-readable summary and verify policy compliance
# ─────────────────────────────────────────────────────────────

def node_explain(state: InvestigationState) -> dict:
    """Generate the final summary and verify actions comply with policy."""
    updates: dict[str, Any] = {"step": 5}

    # If no summary yet, build one from state
    if not state.get("summary"):
        evidence_items = state.get("evidence", [])
        claims = " ".join([e.get("claim", "") for e in evidence_items[:3]])
        verdict = state.get("verdict", "uncertain")
        pattern = state.get("pattern", "none")
        prob = state.get("fraud_probability", 0.5)
        exposure = state.get("exposure_usd", 0.0)
        summary = (
            f"Case {state['hhg_case_id']}: verdict={verdict}, pattern={pattern}, "
            f"fraud_probability={prob:.2f}, exposure=${exposure:.2f}. "
            f"Key evidence: {claims[:300]}."
        )
        updates["summary"] = summary

    return updates


# ─────────────────────────────────────────────────────────────
# NODE 6: write_to_graph
# Persist the investigation case to TigerGraph
# ─────────────────────────────────────────────────────────────

def node_write_to_graph(state: InvestigationState) -> dict:
    """Write the completed investigation case vertex to TigerGraph."""
    updates: dict[str, Any] = {"step": 6}

    case_data = {
        "hhg_case_id": state["hhg_case_id"],
        "card_id": state["card_id"],
        "status": state.get("case_status", "open"),
        "verdict": state.get("verdict", "uncertain"),
        "fraud_probability": state.get("fraud_probability", 0.5),
        "pattern": state.get("pattern", "none"),
        "exposure_usd": state.get("exposure_usd", 0.0),
        "summary": state.get("summary", ""),
        "affected_txn_ids": state.get("affected_txn_ids", []),
        "answer_json": "",  # filled in by benchmark_runner after assembly
    }

    result = gc.write_investigation_case(case_data)
    updates["tool_calls"] = state["tool_calls"] + 1

    if result.get("success"):
        updates["written_to_graph"] = True
        updates["graph_case_id"] = result.get("graph_case_id", "")
    else:
        updates["written_to_graph"] = False
        updates["graph_case_id"] = ""

    return updates
