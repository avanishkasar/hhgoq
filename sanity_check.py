"""
sanity_check.py — Quick local checks before touching TigerGraph.
Tests: dataset files present, case pack parseable, dry-run output schema valid.
Run: python sanity_check.py
"""

import csv
import json
import sys
import os
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PASS = "[OK]"
FAIL = "[FAIL]"
errors = []

def check(desc, condition, detail=""):
    if condition:
        print(f"  {PASS} {desc}")
    else:
        print(f"  {FAIL} {desc}" + (f" — {detail}" if detail else ""))
        errors.append(desc)

print("\n=== Sanity Check ===\n")

# 1. Dataset files
print("[1] Dataset files")
for fname in ["transactions.csv", "identity.csv", "closed_cases_history.csv", "case_pack.csv", "README.md"]:
    p = Path("HHGOA_IEEE") / fname
    check(fname, p.exists(), f"Not found: {p}")

# 2. Case pack
print("\n[2] Case pack")
cases = []
try:
    with open("HHGOA_IEEE/case_pack.csv", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
    check("case_pack.csv parsed", len(cases) == 20, f"Expected 20, got {len(cases)}")
    required_cols = {"case_id", "trigger_type", "flagged_txn_id", "card_id", "customer_id"}
    check("Required columns present", required_cols.issubset(set(cases[0].keys())))
except Exception as e:
    check("case_pack.csv parseable", False, str(e))

# 3. .env file
print("\n[3] Environment")
try:
    from dotenv import load_dotenv
    load_dotenv()
    check(".env loaded", True)
    check("TG_HOST set", bool(os.getenv("TG_HOST")) and "REPLACE_ME" not in os.getenv("TG_HOST", ""),
          "Edit .env and replace REPLACE_ME with your TigerGraph host")
    check("LLM_BASE_URL set", bool(os.getenv("LLM_BASE_URL")))
except ImportError:
    check("python-dotenv installed", False, "pip install python-dotenv")

# 4. Import agent modules
print("\n[4] Agent module imports")
try:
    from agent.state import initial_state, InvestigationState
    check("agent.state", True)
    test_state = initial_state(cases[0])
    check("initial_state() works", test_state["hhg_case_id"] == cases[0]["case_id"])
except Exception as e:
    check("agent.state imports", False, str(e))

try:
    from agent import graph_client as gc
    check("agent.graph_client", True)
except Exception as e:
    check("agent.graph_client", False, str(e))

try:
    from agent.workflow import build_graph
    graph = build_graph()
    check("LangGraph compiles", True)
except Exception as e:
    check("agent.workflow compiles", False, str(e))

# 5. Dry run on case HHG-001
print("\n[5] Dry run (HHG-001)")
try:
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "benchmark_runner.py", "--case", "HHG-001", "--dry-run"],
        capture_output=True, text=True, timeout=30,
        cwd=os.getcwd()
    )
    out_path = Path("cases/HHG-001.json")
    check("Dry run exits 0", result.returncode == 0, result.stderr[:300])
    if out_path.exists():
        with open(out_path) as f:
            ans = json.load(f)
        required_top = {"case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason"}
        check("Output has required top-level keys", required_top.issubset(ans.keys()))
        check("case.verdict is set", ans["case"]["verdict"] in {"fraud", "legitimate", "uncertain"})
        check("case.fraud_probability in [0,1]", 0 <= ans["case"]["fraud_probability"] <= 1)
    else:
        check("cases/HHG-001.json created", False)
except Exception as e:
    check("Dry run", False, str(e))

# Summary
print(f"\n{'='*40}")
if errors:
    print(f"  {len(errors)} issue(s) found:")
    for e in errors:
        print(f"    - {e}")
    print("\n  Fix the above before running load_data.py or benchmark_runner.py")
    sys.exit(1)
else:
    print(f"  {PASS} All checks passed — ready to run!")
    sys.exit(0)
