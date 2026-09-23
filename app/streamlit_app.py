"""
streamlit_app.py — TigerGraph Agentic Fraud Investigation Operations Center
Built for Hacker House Goa 2026 (Partner Trial PS#1)
"""

import os
import json
import glob
from pathlib import Path
from datetime import datetime

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sys

# Ensure project root is in sys.path when running from inside the app folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()
from agent import graph_client as gc
from benchmark_runner import run_single_case, assemble_answer

st.set_page_config(
    page_title="TigerGraph Fraud Intel | HH Goa 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CASES_DIR = Path("cases")
CASES_DIR.mkdir(exist_ok=True)

# ── Custom CSS for Modern Dark Financial Terminal Theme ───────
st.markdown("""
<style>
    /* Fade In Animation */
    @keyframes fadeIn {
        0% { opacity: 0; transform: translateY(15px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    
    .block-container {
        animation: fadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    .metric-card {
        background: linear-gradient(145deg, #1f2937, #111827);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .metric-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
        border-color: #4f46e5;
    }

    /* Pulse animation for active cases */
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(79, 70, 229, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(79, 70, 229, 0); }
        100% { box-shadow: 0 0 0 0 rgba(79, 70, 229, 0); }
    }

    .badge-fraud {
        background: linear-gradient(90deg, #ef444422, #dc262622);
        color: #f87171;
        padding: 6px 12px;
        border-radius: 16px;
        border: 1px solid #ef4444;
        font-weight: 700;
        letter-spacing: 0.5px;
        box-shadow: 0 0 10px #ef444422;
    }
    .badge-legit {
        background: linear-gradient(90deg, #22c55e22, #16a34a22);
        color: #4ade80;
        padding: 6px 12px;
        border-radius: 16px;
        border: 1px solid #22c55e;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .badge-uncertain {
        background: linear-gradient(90deg, #eab30822, #ca8a0422);
        color: #facc15;
        padding: 6px 12px;
        border-radius: 16px;
        border: 1px solid #eab308;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    
    /* Sleek tab styling overrides */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 8px 8px 0px 0px;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────

def load_all_cases() -> list[dict]:
    answers = []
    for path in sorted(glob.glob(str(CASES_DIR / "HHG-*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                answers.append(json.load(f))
        except Exception:
            pass
    return answers


def load_case_pack() -> list[dict]:
    pack_path = Path("HHGOA_IEEE/case_pack.csv")
    if pack_path.exists():
        import csv
        with open(pack_path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []


def verdict_badge(v: str) -> str:
    colors = {
        "fraud": "<span class='badge-fraud'>🔴 CONFIRMED FRAUD</span>",
        "legitimate": "<span class='badge-legit'>🟢 LEGITIMATE</span>",
        "uncertain": "<span class='badge-uncertain'>🟡 UNCERTAIN (STEP-UP)</span>",
    }
    return colors.get(v, f"<span>{v.upper()}</span>")


def route_badge(r: str) -> str:
    colors = {"auto": "🤖 AUTO", "L1": "👤 L1 LEAD", "L2": "👔 L2 MANAGER"}
    return colors.get(r, r)


PATTERN_LABELS = {
    "card_testing": "Card Testing",
    "card_not_present_fraud": "CNP Fraud",
    "card_not_present_new_device": "CNP New Device",
    "out_of_region_use": "Out-of-Region",
    "account_takeover": "Account Takeover",
    "undocumented": "Undocumented",
    "none": "Normal Activity",
}


def build_subgraph_figure(txn_id: str, card_id: str, customer_id: str, connected_cards: list[str] = None) -> go.Figure:
    """Generate an interactive Plotly network diagram of the TigerGraph neighborhood."""
    if not connected_cards:
        connected_cards = []
    nodes = []
    edges = []

    # Center: Flagged Transaction
    nodes.append({"id": f"Txn:{txn_id}", "label": f"Flagged Txn\n#{txn_id}", "color": "#ef4444", "size": 28, "type": "Transaction"})

    # Card & Customer
    if card_id:
        nodes.append({"id": f"Card:{card_id}", "label": f"Card\n{card_id}", "color": "#10b981", "size": 24, "type": "Card"})
        edges.append((f"Card:{card_id}", f"Txn:{txn_id}", "MADE"))

    if customer_id:
        nodes.append({"id": f"Cust:{customer_id}", "label": f"Customer\n{customer_id}", "color": "#3b82f6", "size": 24, "type": "Customer"})
        if card_id:
            edges.append((f"Cust:{customer_id}", f"Card:{card_id}", "OWNS"))

    # Connected Cards (via device sharing ring)
    for i, cc in enumerate(connected_cards[:5]):
        cc_id = f"SharedCard:{cc}"
        nodes.append({"id": cc_id, "label": f"Shared Card\n{cc}", "color": "#f59e0b", "size": 20, "type": "Connected Card"})
        if card_id:
            edges.append((f"Card:{card_id}", cc_id, "SHARES_DEVICE"))

    # Layout nodes in circle
    import math
    n = len(nodes)
    pos = {}
    for i, node in enumerate(nodes):
        if i == 0:
            pos[node["id"]] = (0.0, 0.0)
        else:
            angle = 2 * math.pi * (i - 1) / max(1, n - 1)
            pos[node["id"]] = (math.cos(angle) * 1.5, math.sin(angle) * 1.5)

    # Build Plotly traces
    edge_x, edge_y = [], []
    for u, v, _ in edges:
        if u in pos and v in pos:
            edge_x.extend([pos[u][0], pos[v][0], None])
            edge_y.extend([pos[u][1], pos[v][1], None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color="#4b5563"),
        hoverinfo="none",
        mode="lines"
    )

    node_x = [pos[node["id"]][0] for node in nodes]
    node_y = [pos[node["id"]][1] for node in nodes]
    node_colors = [node["color"] for node in nodes]
    node_sizes = [node["size"] for node in nodes]
    node_text = [node["label"].replace("\n", " — ") for node in nodes]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=[node["id"].split(":")[0] for node in nodes],
        textposition="bottom center",
        hovertext=node_text,
        hoverinfo="text",
        marker=dict(size=node_sizes, color=node_colors, line=dict(width=2, color="#ffffff"))
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=dict(text="TigerGraph Multi-Hop Subgraph Traversal", font=dict(size=14, color="#e5e7eb")),
            showlegend=False,
            hovermode="closest",
            margin=dict(b=10, l=10, r=10, t=35),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=320,
        )
    )
    return fig


# ── Header & Status Bar ───────────────────────────────────────

st.title("🛡️ TigerGraph Agentic Fraud Intel Operations Center")
st.caption("TigerGraph × Hacker House Goa 2026 | Autonomous Multi-Hop Graph Investigation System")

cases = load_all_cases()
case_pack = load_case_pack()
pack_map = {row["case_id"]: row for row in case_pack}

# ── Metrics Row ───────────────────────────────────────────────
col1, col2, col3, col4, col5, col6 = st.columns(6)
fraud_cases = [c for c in cases if c["case"]["verdict"] == "fraud"]
legit_cases = [c for c in cases if c["case"]["verdict"] == "legitimate"]
uncertain_cases = [c for c in cases if c["case"]["verdict"] == "uncertain"]
total_exposure = sum((c.get("case", {}).get("exposure_usd") or 0.0) for c in cases)
sar_cases = [c for c in cases if c.get("sar", {}).get("file")]

def make_metric(title, value):
    return f'<div class="metric-card"><p style="color:#9ca3af; font-size:14px; margin-bottom:4px;">{title}</p><h2 style="margin:0; font-weight:700;">{value}</h2></div>'

col1.markdown(make_metric("Processed Cases", f"{len(cases)} / 20"), unsafe_allow_html=True)
col2.markdown(make_metric("🔴 Fraud", len(fraud_cases)), unsafe_allow_html=True)
col3.markdown(make_metric("🟢 Legitimate", len(legit_cases)), unsafe_allow_html=True)
col4.markdown(make_metric("🟡 Uncertain", len(uncertain_cases)), unsafe_allow_html=True)
col5.markdown(make_metric("💰 Total Exposure", f"${total_exposure:,.0f}"), unsafe_allow_html=True)
col6.markdown(make_metric("📄 SARs Filed", len(sar_cases)), unsafe_allow_html=True)

st.divider()

# ── Sidebar Case Selector & Runner ────────────────────────────
with st.sidebar:
    st.header("⚡ Investigation Control")
    st.markdown("Select a benchmark case to inspect or run an autonomous investigation live:")

    all_case_ids = [f"HHG-{i:03d}" for i in range(1, 21)]
    selected_case_id = st.selectbox("Select Case", all_case_ids, index=0)

    row_data = pack_map.get(selected_case_id, {})
    if row_data:
        st.info(
            f"**Trigger:** `{row_data.get('trigger_type', '')}`\n\n"
            f"**Card:** `{row_data.get('card_id', '')}`\n\n"
            f"**Flagged Txn:** `{row_data.get('flagged_txn_id', '')}`\n\n"
            f"**Risk Score:** `{row_data.get('risk_score', 'N/A')}`"
        )

    if st.button("▶️ Run Agent on this Case Live", type="primary", use_container_width=True):
        with st.status(f"🕵️‍♂️ **Agent investigating {selected_case_id}...**", expanded=True) as status:
            st.write("🔄 Initializing LangGraph state machine...")
            st.write("🕸️ Traversing TigerGraph for multi-hop evidence...")
            st.write("🧠 Prompting Qwen 3.5 9B (Local LLM)...")
            
            import time
            start_t = time.time()
            ans = run_single_case(selected_case_id, dry_run=False)
            elapsed = time.time() - start_t
            
            status.update(label=f"✅ Case {selected_case_id} completed in {elapsed:.1f}s!", state="complete", expanded=False)
        st.balloons()
        time.sleep(1.5)
        st.rerun()

    st.markdown("---")
    st.markdown("### 🏛️ System Architecture")
    st.markdown("""
    - **Database**: TigerGraph Savanna 4.2.5
    - **Vertices**: Customer, Card, Txn, Device, ClosedCase
    - **Orchestration**: LangGraph State Machine
    - **Graph Traversals**: 2-hop BFS + Shared Device Rings
    - **Policy Engine**: Bank Rules R1–R10
    """)


# ── Analytics Visualizations ──────────────────────────────────
if cases:
    chart_col1, chart_col2, chart_col3 = st.columns(3)

    with chart_col1:
        st.subheader("Verdict Distribution")
        v_df = pd.DataFrame({
            "Verdict": ["Fraud", "Legitimate", "Uncertain"],
            "Count": [len(fraud_cases), len(legit_cases), len(uncertain_cases)]
        })
        fig_pie = px.pie(
            v_df, names="Verdict", values="Count",
            color="Verdict",
            color_discrete_map={"Fraud": "#ef4444", "Legitimate": "#22c55e", "Uncertain": "#eab308"},
            hole=0.45
        )
        fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=240)
        st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        st.subheader("Detected Fraud Patterns")
        p_counts: dict[str, int] = {}
        for c in cases:
            p = PATTERN_LABELS.get(c["case"]["pattern"], c["case"]["pattern"])
            p_counts[p] = p_counts.get(p, 0) + 1
        p_df = pd.DataFrame(list(p_counts.items()), columns=["Pattern", "Count"]).sort_values("Count", ascending=True)
        fig_bar = px.bar(p_df, x="Count", y="Pattern", orientation="h", color="Count", color_continuous_scale="Blues", height=240)
        fig_bar.update_layout(margin=dict(t=0, b=0, l=0, r=0), coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col3:
        st.subheader("Fraud Probability vs Risk Score")
        scatter_data = []
        for c in cases:
            cid = c["case_id"]
            orig_risk = float(pack_map.get(cid, {}).get("risk_score") or 0.5)
            prob = c["case"]["fraud_probability"]
            scatter_data.append({"Case": cid, "Initial Risk Score": orig_risk, "Agent Fraud Probability": prob, "Verdict": c["case"]["verdict"]})
        sc_df = pd.DataFrame(scatter_data)
        fig_sc = px.scatter(
            sc_df, x="Initial Risk Score", y="Agent Fraud Probability", color="Verdict",
            color_discrete_map={"fraud": "#ef4444", "legitimate": "#22c55e", "uncertain": "#eab308"},
            hover_name="Case", height=240
        )
        fig_sc.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_sc, use_container_width=True)

st.divider()

# ── Selected Case Deep-Dive ───────────────────────────────────
case_file = CASES_DIR / f"{selected_case_id}.json"

if not case_file.exists():
    st.warning(f"Case `{selected_case_id}` has not been investigated yet. Click the **'▶️ Run Agent on this Case Live'** button in the sidebar to run it!")
else:
    with open(case_file, encoding="utf-8") as f:
        case_data = json.load(f)

    c_info = case_data["case"]
    sar_info = case_data.get("sar", {})
    actions = case_data.get("next_best_actions", {})

    st.subheader(f"🔍 Case Dossier: {selected_case_id}")
    st.markdown(verdict_badge(c_info["verdict"]), unsafe_allow_html=True)

    tab_summary, tab_graph, tab_actions, tab_sar, tab_json = st.tabs([
        "📋 Executive Summary", 
        "🕸️ Graph Neighborhood", 
        "⚖️ Policy & Actions", 
        "📄 SAR Filing", 
        "📦 Raw Data"
    ])

    with tab_summary:
        col_meta1, col_meta2 = st.columns([1, 1])
        with col_meta1:
            st.markdown(f"**Pattern Detected:** `{PATTERN_LABELS.get(c_info.get('pattern'), c_info.get('pattern', 'N/A'))}`")
            prob = c_info.get("fraud_probability") or 0.0
            st.markdown(f"**Assessed Fraud Probability:** `{prob:.2f}`")
            exp_val = c_info.get("exposure_usd") or 0.0
            st.markdown(f"**Financial Exposure:** `${float(exp_val):,.2f}`")
            st.markdown(f"**Primary Affected Txn:** `{c_info.get('first_suspicious_txn_id', '—')}`")
            st.markdown(f"**TigerGraph Memory Persisted:** `{c_info.get('graph_case_id', 'Not written')}`")

        with col_meta2:
            st.markdown("**Executive Summary & Decision Audit:**")
            st.info(c_info.get("summary", "No summary available."))
            st.caption(f"**Stopping Rule:** {case_data.get('stop_reason', 'Policy threshold satisfied.')}")

    with tab_graph:
        # Subgraph Visualizer
        flagged_txn = pack_map.get(selected_case_id, {}).get("flagged_txn_id", "")
        card_id = pack_map.get(selected_case_id, {}).get("card_id", "")
        cust_id = pack_map.get(selected_case_id, {}).get("customer_id", "")
        connected_cards = c_info.get("connected_card_ids") or []

        st.markdown("### 🕸️ TigerGraph Knowledge Subgraph")
        st.caption("Visualizing the immediate neighborhood and device-sharing rings.")
        subgraph_fig = build_subgraph_figure(flagged_txn, card_id, cust_id, connected_cards)
        st.plotly_chart(subgraph_fig, use_container_width=True)

    with tab_actions:
        # Next Best Action Workbench
        st.markdown("### ⚖️ Next-Best-Action Policy Matrix")
        if actions.get("what_changed") and actions.get("what_changed") != "nothing":
            st.success(f"**Policy Drift / Transition:** {actions['what_changed']}")
            
        act_col1, act_col2 = st.columns(2)

        with act_col1:
            st.markdown("#### ⏳ Initial Actions (Pre-Evidence Request)")
            init_acts = actions.get("initial", [])
            if init_acts:
                for a in init_acts:
                    st.markdown(f"- **`{a.get('action')}`** `[{route_badge(a.get('route', ''))}]` — *{a.get('reason', '')}*")
            else:
                st.write("None recorded.")

        with act_col2:
            st.markdown("#### ✅ Final Actions (Post-Evidence Assessment)")
            final_acts = actions.get("final", [])
            if final_acts:
                for a in final_acts:
                    st.markdown(f"- **`{a.get('action')}`** `[{route_badge(a.get('route', ''))}]` — *{a.get('reason', '')}*")
            else:
                st.write("None recorded.")

    with tab_sar:
        # SAR Filing Section
        st.markdown("### 📄 Suspicious Activity Report (SAR) Regulatory Filing")
        if sar_info.get("file"):
            st.error(f"⚠️ **SAR REQUIRED FOR REGULATORY FILING** — Reason: {sar_info.get('reason', '')}")
            st.markdown(f"**Total SAR Exposure:** `${sar_info.get('total_amount_usd', 0):,.2f}` | **Subjects:** {', '.join(sar_info.get('subjects', []))}")
            st.text_area("Narrative", sar_info.get("narrative", ""), height=250)
            st.download_button("📥 Download Official SAR (.txt)", sar_info.get("narrative", ""), file_name=f"SAR_{selected_case_id}.txt", type="primary")
        else:
            st.success("✅ **No SAR Filing Required** (Case exposure or risk level falls below FinCEN / Bank threshold).")

    with tab_json:
        # Raw JSON Download
        st.json(case_data)
        st.download_button(
            label=f"📥 Download {selected_case_id}.json",
            data=json.dumps(case_data, indent=2),
            file_name=f"{selected_case_id}.json",
            mime="application/json"
        )
