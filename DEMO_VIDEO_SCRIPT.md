# 🎬 3–4 Minute Demo Video Script — Hacker House Goa 2026
**Project:** Autonomous Multi-Hop GraphRAG Agent for Financial Fraud Investigation & Next-Best Action  
**Presenter:** Avanish Kasar  
**Target Time:** 3 minutes 30 seconds  

---

## 💡 Quick Tips for Recording:
- Open your windows side-by-side or have them ready in browser tabs:
  1. **Tab 1:** Streamlit Dashboard ([http://localhost:8501](http://localhost:8501))
  2. **Tab 2:** TigerGraph GraphStudio (`FraudGraph` schema)
  3. **Tab 3:** VS Code (showing `agent/nodes.py` and `cases/`)
- Speak in a calm, confident, clear voice. 
- You can record your screen first (clicking through the tabs) and read this script as a voiceover on top, or read it while clicking!

---

## 🎙️ Voiceover Script & Screen Cues

### **Part 1: The Problem & Architecture (0:00 – 0:45)**
* **[🖥️ SCREEN TO SHOW]:** Streamlit Operations Dashboard ([http://localhost:8501](http://localhost:8501)) — show the title and the top metrics row.
* **[🗣️ READ THIS]:**
> *"Hello judges, I’m Avanish Kasar. This is my submission for the TigerGraph Agentic Fraud Investigation challenge for Hacker House Goa 2026.*
>
> *Today, bank fraud analysts spend 80% of their time manually clicking between separate relational databases, checking device tables, and flipping through compliance handbooks while fraudulent transactions drain customer accounts.*
>
> *Traditional machine learning models only produce a scalar risk score like 0.85. But a score doesn't tell an investigator whether five other cards share the same device fingerprint, or whether bank policy requires blocking the card versus requesting step-up verification.*
>
> *To solve this, I built an Autonomous GraphRAG Fraud Investigation Agent powered by TigerGraph Savanna, LangGraph, and a local on-device LLM running on my GPU."*

---

### **Part 2: TigerGraph Schema & 2-Hop Graph Traversals (0:45 – 1:30)**
* **[🖥️ SCREEN TO SHOW]:** Switch to browser showing **TigerGraph GraphStudio** (`FraudGraph` schema with Customer, Card, Transaction, DeviceProfile, ClosedCase).
* **[🗣️ READ THIS]:**
> *"Here in TigerGraph GraphStudio, we have our property graph: `FraudGraph`.*
>
> *We loaded the IEEE-CIS benchmark dataset: over 590,000 transactions, 140,000 identity records, and 5,500 historical closed cases.*
>
> *Because fraud operates in networks, relational databases choke on multi-table joins. In TigerGraph, our agent executes sub-10 millisecond 2-hop traversals.*
>
> *By following edges from `Customer` to `Card`, `Transaction`, and `DeviceProfile`, TigerGraph instantly exposes shared-device fraud rings, card-testing bursts, and billing anomalies that flat tabular tables completely miss."*

---

### **Part 3: Live Investigation & Uncertainty Handling (1:30 – 2:30)**
* **[🖥️ SCREEN TO SHOW]:** Switch to the Streamlit app. In the sidebar, select case **`HHG-005`** or **`HHG-007`** and click **"▶️ Run Agent on this Case Live"**. Show the animated status container expanding and celebrating.
* **[🗣️ READ THIS]:**
> *"Now let's see the agent in action on our operations dashboard.*
>
> *When an alert triggers, our LangGraph state machine takes over. First, it extracts the transaction context. Then, it queries TigerGraph for device sharing patterns and searches our 5,500 closed cases for historical episodic memory.*
>
> *Crucially, notice how our agent handles uncertainty. Under bank policy, when signals are uncertain, blindly blocking a legitimate customer creates severe customer friction. Instead, our agent identifies what evidence is missing and initiates a simulated step-up authentication challenge.*
>
> *In the Policy and Actions matrix, you can see the two-phase decision: what the agent recommended initially, and how it updated the final action once the step-up verification returned."*

---

### **Part 4: Graph Subgraph & SAR Filing (2:30 – 3:15)**
* **[🖥️ SCREEN TO SHOW]:** Click on the **"🕸️ Graph Neighborhood"** tab (hover over the interactive network nodes), then click on the **"📄 SAR Filing"** tab.
* **[🗣️ READ THIS]:**
> *"In the Graph Neighborhood tab, analysts get an interactive Plotly visualization of the card, customer, and all devices involved in the shared ring.*
>
> *Under the SAR Filing tab, if financial exposure exceeds 1,000 dollars or indicates a coordinated device ring, our agent automatically drafts a FinCEN-compliant Suspicious Activity Report with full narrative and entity citations ready for compliance submission.*
>
> *Finally, our agent performs closed-loop memory writeback: it writes the finished investigation back into TigerGraph as an `InvestigationCase` vertex, making the system smarter for all future cases."*

---

### **Part 5: Conclusion & Benchmark Results (3:15 – 3:30)**
* **[🖥️ SCREEN TO SHOW]:** Show the **Verdict Distribution** pie chart and the 20 processed cases in the dashboard.
* **[🗣️ READ THIS]:**
> *"All 20 benchmark test cases have been processed, audited, and committed to our GitHub repository in the `cases/` folder.*
>
> *By combining TigerGraph's deep graph traversals with agentic reasoning, we turn slow manual fraud checks into autonomous, defensible, next-best actions. Thank you!"*
