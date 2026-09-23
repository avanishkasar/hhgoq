# Fraud Investigation Agent — HH Goa 2026

**TigerGraph × Hacker House Goa 2026 — Partner Trial PS#1**

An agentic AI system that investigates financial fraud using graph-based evidence retrieval, LLM reasoning, and policy-compliant next-best-action generation.

---

## Architecture

```
Trigger → Investigate (GraphRAG) → Assess Uncertainty
              ↑ loop                        ↓ (evidence settled)
                                      Act → Explain → Write to Graph
```

- **TigerGraph** — stores customers, cards, transactions, device profiles, and closed case history as a property graph
- **LangGraph** — state machine orchestrating the 6-node investigation pipeline
- **GraphRAG** — retrieves 2-hop graph neighborhood + similar past cases, synthesized for LLM reasoning
- **LLM (LM Studio / OpenAI)** — produces evidence analysis, fraud probability, pattern classification, and next-best-actions
- **Streamlit** — analyst dashboard with case drill-down, SAR display, and action tracking

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your TigerGraph and LLM credentials
```

### 3. Create TigerGraph schema
Paste the contents of `tigergraph/schema.gsql` into the TigerGraph Studio GSQL editor and run it.

### 4. Load data (first time only)
```bash
# Quick test with 5000 transactions
python load_data.py --sample 5000

# Full load (~40 min on Savanna free tier)
python load_data.py
```

### 5. Run the benchmark (all 20 cases)
```bash
python benchmark_runner.py
```
Outputs one JSON file per case in `./cases/`.

### 6. Dry run (no TigerGraph needed)
```bash
python benchmark_runner.py --dry-run
```

### 7. Launch the dashboard
```bash
streamlit run app/streamlit_app.py
```

## Project Structure

```
├── HHGOA_IEEE/              # Dataset (not committed)
│   ├── transactions.csv
│   ├── identity.csv
│   ├── closed_cases_history.csv
│   └── case_pack.csv
├── agent/
│   ├── __init__.py
│   ├── state.py             # LangGraph TypedDict state schema
│   ├── nodes.py             # All 6 investigation nodes
│   ├── workflow.py          # StateGraph definition
│   └── graph_client.py      # TigerGraph query functions (tools)
├── app/
│   └── streamlit_app.py     # Analyst dashboard
├── tigergraph/
│   └── schema.gsql          # Graph schema DDL
├── cases/                   # Output: 20 JSON answer files
├── load_data.py             # Data loader
├── benchmark_runner.py      # Runs agent on all 20 cases
├── requirements.txt
└── .env.example
```

## Fraud Patterns Detected

| Pattern | Code |
|---|---|
| Card Testing | `card_testing` |
| Card-Not-Present Fraud | `card_not_present_fraud` |
| CNP Fraud via New Device | `card_not_present_new_device` |
| Out-of-Region Use | `out_of_region_use` |
| Account Takeover | `account_takeover` |
| Undocumented (agent-discovered) | `undocumented` |

## Policy Compliance

Actions follow the bank's Fraud Policy v1.0:
- **R1–R10** rules map to all next-best-action decisions
- Approval routing: `auto` / `L1` (team lead) / `L2` (fraud manager)
- SAR filing triggered automatically when policy criteria met

## Known Limitations

- `load_data.py` uses single-row upserts for simplicity; for production, use TigerGraph's bulk CSV loader
- Simulated customer/analyst responses in `evidence_requests` use heuristic defaults
- LLM JSON extraction uses brace-matching; prompt engineering may be needed for different model families
