"""
benchmark_runner.py — Run the fraud investigation agent on all 20 benchmark cases
and write JSON answer files to ./cases/

Usage:
    python benchmark_runner.py                  # all 20 cases
    python benchmark_runner.py --case HHG-001   # single case
    python benchmark_runner.py --dry-run        # no TigerGraph, uses mock data
"""

import os
import csv
import json
import time
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

CASES_DIR = Path("cases")
CASES_DIR.mkdir(exist_ok=True)

CASE_PACK = os.path.join("HHGOA_IEEE", "case_pack.csv")


def load_case_pack() -> list[dict]:
    cases = []
    with open(CASE_PACK, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(dict(row))
    return cases


def assemble_answer(state: dict) -> dict:
    """Build the final JSON answer from the completed investigation state."""
    case = {
        "status": state.get("case_status", "open"),
        "verdict": state.get("verdict", "uncertain"),
        "fraud_probability": round(float(state.get("fraud_probability", 0.5)), 3),
        "pattern": state.get("pattern", "none"),
        "pattern_description": state.get("pattern_description", ""),
        "affected_txn_ids": state.get("affected_txn_ids", []),
        "first_suspicious_txn_id": state.get("first_suspicious_txn_id", ""),
        "connected_card_ids": state.get("connected_card_ids", []),
        "connected_device_profiles": state.get("connected_device_profiles", []),
        "exposure_usd": round(float(state.get("exposure_usd", 0.0)), 2),
        "evidence": state.get("evidence", []),
        "similar_prior_cases": state.get("similar_prior_cases", []),
        "summary": state.get("summary", ""),
        "written_to_graph": state.get("written_to_graph", False),
        "graph_case_id": state.get("graph_case_id", ""),
    }

    sar_raw = state.get("sar") or {}
    sar = {
        "file": sar_raw.get("file", False),
        "reason": sar_raw.get("reason", ""),
        "narrative": sar_raw.get("narrative", "") if sar_raw.get("file") else "",
        "subjects": sar_raw.get("subjects", []) if sar_raw.get("file") else [],
        "total_amount_usd": float(sar_raw.get("total_amount_usd", 0)),
        "activity_dates": sar_raw.get("activity_dates", []) if sar_raw.get("file") else [],
    }

    nba = {
        "initial": state.get("initial_actions", []),
        "final": state.get("final_actions", []),
        "what_changed": state.get("what_changed", "nothing"),
    }

    elapsed = round(time.time() - state.get("start_time", time.time()), 1)

    answer = {
        "case_id": state.get("hhg_case_id", ""),
        "case": case,
        "evidence_requests": state.get("evidence_requests", []),
        "next_best_actions": nba,
        "sar": sar,
        "stop_reason": state.get("stop_reason", ""),
        "tool_calls": state.get("tool_calls", 0),
        "tokens": state.get("tokens_used", 0),
        "latency_s": elapsed,
    }
    return answer


def run_case(case_row: dict, dry_run: bool = False) -> dict:
    """Run the agent on a single case and return the answer dict."""
    from agent.state import initial_state

    state = initial_state(case_row)
    hhg_id = case_row["case_id"]
    print(f"\n{'='*60}")
    print(f"  Investigating {hhg_id} — {case_row['trigger_type']}: {case_row['flagged_txn_id']}")
    print(f"{'='*60}")

    if dry_run:
        # Return a skeleton answer for dry-run testing
        answer = assemble_answer(dict(state))
        answer["stop_reason"] = "dry_run: no graph connection"
        return answer

    from agent.workflow import investigation_graph

    try:
        final_state = investigation_graph.invoke(state)
    except Exception as e:
        print(f"  ERROR on {hhg_id}: {e}")
        import traceback
        traceback.print_exc()
        # Return a degraded answer rather than crashing the whole batch
        state["stop_reason"] = f"Agent error: {str(e)}"
        state["verdict"] = "uncertain"
        state["case_status"] = "escalated"
        state["initial_actions"] = [
            {"action": "ESCALATE_TO_ANALYST", "route": "auto",
             "reason": "R8: agent encountered an error during investigation"}
        ]
        state["final_actions"] = state["initial_actions"]
        state["sar"] = {"file": False, "reason": "Error during investigation", "narrative": "",
                        "subjects": [], "total_amount_usd": 0, "activity_dates": []}
        return assemble_answer(dict(state))

    return assemble_answer(dict(final_state))


def save_answer(answer: dict) -> Path:
    case_id = answer["case_id"]
    path = CASES_DIR / f"{case_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(answer, f, indent=2, ensure_ascii=False)
    print(f"  [OK] Saved {path}")
    return path


def run_single_case(case_id: str, dry_run: bool = False) -> dict:
    cases = load_case_pack()
    matches = [c for c in cases if c["case_id"] == case_id]
    if not matches:
        raise ValueError(f"Case {case_id} not found in case pack.")
    ans = run_case(matches[0], dry_run=dry_run)
    save_answer(ans)
    return ans


def print_summary(answers: list[dict]):
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    verdicts = {"fraud": 0, "legitimate": 0, "uncertain": 0}
    total_exposure = 0.0
    total_tokens = 0
    total_latency = 0.0

    for a in answers:
        v = a["case"]["verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
        total_exposure += a["case"]["exposure_usd"]
        total_tokens += a.get("tokens", 0)
        total_latency += a.get("latency_s", 0)

    print(f"  Verdicts: fraud={verdicts['fraud']}, legitimate={verdicts['legitimate']}, "
          f"uncertain={verdicts['uncertain']}")
    print(f"  Total exposure identified: ${total_exposure:,.2f}")
    print(f"  Total LLM tokens: {total_tokens:,}")
    print(f"  Total wall time: {total_latency:.1f}s")
    print(f"  Avg time per case: {total_latency/max(len(answers),1):.1f}s")
    print()

    # Per-case table
    print(f"  {'Case':<12} {'Verdict':<12} {'Pattern':<30} {'Prob':>5} {'Exposure':>10}")
    print(f"  {'-'*12} {'-'*12} {'-'*30} {'-'*5} {'-'*10}")
    for a in answers:
        c = a["case"]
        print(f"  {a['case_id']:<12} {c['verdict']:<12} {c['pattern']:<30} "
              f"{c['fraud_probability']:>5.2f} ${c['exposure_usd']:>9,.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=str, default=None,
                        help="Run only this case (e.g. HHG-001)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip cases that already have an answer file in cases/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip TigerGraph; produce skeleton answers")
    args = parser.parse_args()

    cases = load_case_pack()

    if args.case:
        cases = [c for c in cases if c["case_id"] == args.case]
        if not cases:
            print(f"Case {args.case} not found in case pack.")
            return

    answers = []
    for case_row in cases:
        target_path = CASES_DIR / f"{case_row['case_id']}.json"
        if args.skip_existing and target_path.exists():
            print(f"  [SKIP] {case_row['case_id']} already exists in cases/")
            with open(target_path, encoding="utf-8") as f:
                answers.append(json.load(f))
            continue
        answer = run_case(case_row, dry_run=args.dry_run)
        save_answer(answer)
        answers.append(answer)

    print_summary(answers)


if __name__ == "__main__":
    main()
