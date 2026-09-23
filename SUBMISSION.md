# 🏆 Hacker House Goa 2026 — TigerGraph Partner Trial (PS#1) Submission Kit

**Project:** Autonomous Multi-Hop GraphRAG Agent for Financial Fraud Investigation & Next-Best Action  
**Author:** Avanish Kasar ([avanish.tech](https://avanish.tech) | [github.com/avanishkasar](https://github.com/avanishkasar))  
**Target Event:** Hacker House Goa 2026 (Oct 28–31, Goa, India)

---

## 1. Executive Summary & Architecture

Modern financial fraud teams face acute operational friction: investigators spend 80% of their time stitching together fragmented databases, examining device identifiers, and checking compliance handbooks while illicit transactions drain accounts. 

We built an **Autonomous Agentic Fraud Investigation System** powered by **TigerGraph Savanna** and **LangGraph**, backed by local on-device LLM reasoning (**Qwen 3.5 9B** on an RTX 4070).

### Core Flow:
```
[Trigger Alert] (Risk Score / Customer Report / Analyst Flag)
       │
       ▼
[Node 1: Trigger Contextualizer] ──► Extracts flagged transaction & ±2h window
       │
       ▼
[Node 2: GraphRAG Traversal] ─────► Queries TigerGraph for 2-hop neighborhood:
       │                             • Customer profile & multi-card ownership
       │                             • Shared device rings (SHARES_DEVICE)
       │                             • Billing region anomalies (BILLED_IN)
       │                             • Memory lookup in 5,565 past Closed Cases
       ▼
[Node 3: Assess Uncertainty] ────► Evaluates risk vs. evidence sufficiency
       │                             • If uncertain: Requests step-up auth or customer verification
       │                             • Loops up to 3x with simulated responses
       ▼
[Node 4: Policy & Action Engine] ─► Generates Next-Best-Action matrix:
       │                             • Initial Action (pre-verification)
       │                             • Final Action (post-verification)
       │                             • Explains "What Changed"
       │                             • Enforces approval routes (auto, L1 Lead, L2 Manager)
       │                             • Determines SAR filing requirement
       ▼
[Node 5: Audit & Explainability] ─► Produces structured summary with cited entity IDs
       │
       ▼
[Node 6: Graph Memory Writeback] ─► Persists InvestigationCase vertex & INV_ON_CARD edges back into TigerGraph
```

---

## 2. Technical Blog Post (Ready to publish on Dev.to / Medium)

> *Copy and paste the text below into your Dev.to or Medium article:*

### Title:
**Building an Autonomous GraphRAG Agent for Financial Fraud with TigerGraph and LangGraph**

### Article Body:
Financial fraud is inherently graph-structured. Fraudsters don't operate in isolated tabular rows; they operate in networks — recycling devices across stolen identities, testing cards across merchants, and jumping billing regions. 

For the **Hacker House Goa 2026 TigerGraph Partner Trial**, I built an autonomous agentic fraud investigator that moves from uncertain signals to defensible next-best actions.

#### The Problem with Traditional Fraud Detection
Standard machine learning models output a scalar risk score (e.g. `0.81`). But a score is not an investigation:
1. It doesn't trace whether five other cards logged in from the same iPhone fingerprint.
2. It doesn't check if the customer has a history of travel in that billing region.
3. It doesn't know whether to block the card, request 2FA step-up authentication, or escalate to a compliance manager under bank policy.

#### Why TigerGraph?
Relational databases choke on multi-hop graph traversals. In our solution:
- **590,742 transactions**, **144,432 identity records**, and **5,565 closed historical cases** from the IEEE-CIS benchmark are modeled as a property graph in **TigerGraph Savanna**.
- Using TigerGraph's high-speed REST++ and GSQL capabilities, our agent performs **sub-10ms 2-hop traversals** linking `Customer ➔ Card ➔ Transaction ➔ DeviceProfile ➔ Other Cards`.
- This uncovers **shared-device rings** and **card testing bursts** that flat tables completely miss.

#### GraphRAG & Case Memory
Instead of naive document retrieval, we implemented **Graph-Grounded Retrieval Augmented Generation (GraphRAG)**:
1. **Structural Context**: The agent retrieves the exact subgraph surrounding the flagged card.
2. **Episodic Memory**: The agent traverses the graph to find similar past investigations (`ClosedCase` vertices) that shared the same device or billing anomaly.
3. **Writeback Memory**: When the agent finishes an investigation, it writes the new `InvestigationCase` vertex directly back to TigerGraph. The next case can now retrieve this newly solved case as historical memory!

#### Policy Compliance & Next-Best Action
Under bank fraud policy rules (R1–R10):
- **Uncertainty Handling**: When confidence is below threshold, the agent initiates controlled actions (e.g. simulated step-up SMS verification) rather than blindly blocking the user.
- **Two-Phase Action Tracking**: The agent explicitly documents what action it recommended *before* evidence arrived, and what action it took *after*.
- **Regulatory Filings**: If financial exposure exceeds $1,000 or indicates coordinated device rings, the agent automatically drafts a **FinCEN-compliant Suspicious Activity Report (SAR)**.

#### Key Takeaways
Graph databases transform LLM agents from hallucination-prone chatbots into precision forensic investigators. TigerGraph's graph scalability provides the structured ground truth that agentic systems need to make high-stakes financial decisions.

---

## 3. Demo Video Script (3–4 Minutes Walkthrough)

*Use Loom, OBS, or Windows Game Bar (`Win + G`) to record your screen:*

1. **0:00 – 0:45: Introduction & Architecture**
   - Introduce yourself: *"Hi, I'm Avanish Kasar, and this is my submission for the TigerGraph Agentic Fraud Investigation trial for Hacker House Goa 2026."*
   - Show the architecture diagram: Explain how LangGraph coordinates with TigerGraph Savanna and local Qwen 3.5 9B.

2. **0:45 – 1:30: TigerGraph GraphStudio**
   - Switch to browser showing TigerGraph Savanna.
   - Show the `FraudGraph` schema with vertices (`Customer`, `Card`, `Transaction`, `DeviceProfile`, `ClosedCase`).
   - Mention that over 590,000 transactions and 5,500 historical cases are loaded and indexed.

3. **1:30 – 2:45: The Streamlit Analyst Dashboard**
   - Switch to the Streamlit app (`streamlit run app/streamlit_app.py`).
   - Show the top KPI cards: Total Cases, Fraud vs. Legitimate split, Total Exposure, SARs filed.
   - Click on **Case HHG-001**:
     - Show the **Plotly Subgraph Visualizer**: Point out how the flagged transaction links to the card, customer, and device profile.
     - Show the **Next-Best-Action Workbench**: Point out the initial action (`VERIFY_WITH_CUSTOMER`) vs. final action (`CLOSE_NO_FRAUD`) following Rule R1.
   - Show a high-severity fraud case with an auto-generated **Suspicious Activity Report (SAR)** narrative and download button.

4. **2:45 – 3:30: Conclusion**
   - Summarize the agentic loop: trigger ➔ GraphRAG ➔ uncertainty assessment ➔ action matrix ➔ graph memory writeback.
   - Conclude: *"Thank you TigerGraph and the Hacker House Goa team. Looking forward to hacking in Goa!"*

---

## 4. Social Media Post (X / Twitter & LinkedIn)

### X (Twitter) Post:
```text
Excited to share my submission for @TigerGraphDB × Hacker House Goa 2026 (@twofourtysevenpm)! 🛡️🏝️

Built an Autonomous Agentic Fraud Investigation system powered by TigerGraph Savanna, LangGraph, and GraphRAG over 590k+ transactions.

✨ Multi-hop device ring traversal
✨ Case memory & writeback to graph
✨ Automated SAR generation & Next-Best Action policy routing

Check out the demo & code: [YOUR_GITHUB_REPO_LINK]

#TigerGraph #HackerHouseGoa #AI #GraphRAG #FraudDetection #AgenticAI
```

### LinkedIn Post:
```text
I just completed the TigerGraph Agentic Fraud Investigation challenge for Hacker House Goa 2026! 🚀

Investigating financial fraud is fundamentally a graph problem. Rather than relying on static ML risk scores, I built an autonomous agent that performs multi-hop graph traversals to detect shared device rings, out-of-region card testing, and account takeover patterns.

Key architectural highlights:
🔹 TigerGraph Savanna: Houses 590,000+ IEEE-CIS transactions, identity records, and 5,500+ historical cases.
🔹 LangGraph State Machine: Orchestrates evidence gathering, uncertainty assessment, policy compliance (Rules R1-R10), and Next-Best Action generation.
🔹 Dynamic Case Memory: Every resolved case is written back into the TigerGraph property graph, constantly evolving the agent's long-term memory.
🔹 Operations Dashboard: Interactive Streamlit UI with graph subgraph visualizers, policy audit trail, and regulatory SAR export.

Huge thanks to the @TigerGraph team and @Hacker House Goa for this trial!

Github Repo: [YOUR_GITHUB_REPO_LINK]
Demo Video: [YOUR_LOOM_LINK]

#TigerGraph #GraphDatabase #AI #LangGraph #GraphRAG #FraudInvestigation #Fintech
```
