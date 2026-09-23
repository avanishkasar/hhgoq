"""
graph_client.py — TigerGraph Savanna REST++ client wrapper + fraud queries.
Communicates directly via port 443 with JWT authentication.
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Any
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

_token: Optional[str] = None
_token_expiry: Optional[datetime] = None


class TigerGraphRESTClient:
    def __init__(self):
        self.host = os.getenv("TG_HOST", "https://localhost").rstrip("/")
        self.secret = os.getenv("TG_SECRET", "")
        self.graph = os.getenv("TG_GRAPHNAME", "FraudGraph")
        self.session = requests.Session()
        self.session.verify = False

    def get_token(self) -> str:
        global _token
        if _token:
            return _token

        url = f"{self.host}/gsql/v1/tokens"
        resp = self.session.post(url, json={"secret": self.secret, "graph": self.graph})
        if resp.status_code == 200:
            data = resp.json()
            _token = data.get("token", "")
            return _token
        else:
            raise RuntimeError(f"Failed to get TigerGraph token: {resp.status_code} {resp.text}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def upsert_graph(self, payload: dict) -> dict:
        """Upsert vertices and edges in bulk: POST /restpp/graph/{graph}"""
        url = f"{self.host}/restpp/graph/{self.graph}"
        resp = self.session.post(url, headers=self._headers(), json=payload)
        return resp.json() if resp.status_code == 200 else {"error": True, "details": resp.text}

    def get_vertex(self, vertex_type: str, vertex_id: str) -> Optional[dict]:
        url = f"{self.host}/restpp/graph/{self.graph}/vertices/{vertex_type}/{vertex_id}"
        resp = self.session.get(url, headers=self._headers())
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return results[0] if results else None
        return None

    def get_edges(self, vertex_type: str, vertex_id: str, edge_type: str = "") -> list:
        url = f"{self.host}/restpp/graph/{self.graph}/edges/{vertex_type}/{vertex_id}"
        if edge_type:
            url += f"/{edge_type}"
        resp = self.session.get(url, headers=self._headers())
        if resp.status_code == 200:
            return resp.json().get("results", [])
        return []


_client: Optional[TigerGraphRESTClient] = None


def get_client() -> TigerGraphRESTClient:
    global _client
    if _client is None:
        _client = TigerGraphRESTClient()
    return _client


# ─────────────────────────────────────────────────────────────
# CORE QUERY FUNCTIONS (used as agent tools)
# ─────────────────────────────────────────────────────────────

def get_transaction(txn_id: str) -> dict:
    """Fetch a single transaction vertex and its connected edges."""
    client = get_client()
    result = {"txn_id": txn_id}

    v = client.get_vertex("Transaction", txn_id)
    result["transaction"] = v.get("attributes", {}) if v else {}

    # Card that made this transaction (MADE_BY reverse edge)
    made_by = client.get_edges("Transaction", txn_id, "MADE_BY")
    result["card_id"] = made_by[0]["to_id"] if made_by else None

    # Device
    dev_edges = client.get_edges("Transaction", txn_id, "FROM_DEVICE")
    if dev_edges:
        did = dev_edges[0]["to_id"]
        dv = client.get_vertex("DeviceProfile", did)
        result["device"] = dv.get("attributes", {}) if dv else {}
        result["device"]["device_id"] = did
    else:
        result["device"] = None

    # Billing region
    br = client.get_edges("Transaction", txn_id, "BILLED_IN")
    result["billing_region"] = br[0]["to_id"] if br else None

    return result


def get_card_history(card_id: str, days: int = 90) -> dict:
    """Return all transactions for a card in the past `days` days."""
    client = get_client()
    try:
        edges = client.get_edges("Card", card_id, "MADE")
        txns = []
        for e in edges:
            tid = e["to_id"]
            v = client.get_vertex("Transaction", tid)
            if v:
                attrs = v.get("attributes", {})
                attrs["txn_id"] = tid
                txns.append(attrs)
        txns.sort(key=lambda x: x.get("ts", ""))
        return {"card_id": card_id, "transactions": txns, "count": len(txns)}
    except Exception as e:
        return {"card_id": card_id, "error": str(e), "transactions": []}


def get_card_window(card_id: str, txn_id: str, hours: int = 2) -> dict:
    """Return all transactions on a card within ±hours of txn_id."""
    client = get_client()
    try:
        anchor_v = client.get_vertex("Transaction", txn_id)
        if not anchor_v:
            return {"error": f"Transaction {txn_id} not found"}
        anchor_ts_str = anchor_v.get("attributes", {}).get("ts", "")
        anchor_ts = datetime.strptime(anchor_ts_str, "%Y-%m-%d %H:%M:%S")
        lo = anchor_ts - timedelta(hours=hours)
        hi = anchor_ts + timedelta(hours=hours)

        history = get_card_history(card_id, days=365)
        window_txns = []
        for t in history["transactions"]:
            try:
                t_ts = datetime.strptime(t.get("ts", ""), "%Y-%m-%d %H:%M:%S")
                if lo <= t_ts <= hi:
                    window_txns.append(t)
            except Exception:
                pass
        window_txns.sort(key=lambda x: x.get("ts", ""))
        return {
            "card_id": card_id,
            "anchor_txn": txn_id,
            "anchor_ts": anchor_ts_str,
            "window_hours": hours,
            "transactions": window_txns,
            "count": len(window_txns),
        }
    except Exception as e:
        return {"error": str(e), "transactions": []}


def get_device_neighbors(device_id: str) -> dict:
    """Find all cards and closed cases that have used this device profile."""
    client = get_client()
    try:
        edges = client.get_edges("DeviceProfile", device_id, "DEVICE_USED_IN")
        txn_ids = [e["to_id"] for e in edges]

        card_ids = set()
        for tid in txn_ids[:100]:
            card_edges = client.get_edges("Transaction", tid, "MADE_BY")
            for ce in card_edges:
                card_ids.add(ce["to_id"])

        related_cases = []
        for cid in list(card_ids)[:15]:
            cc_edges = client.get_edges("Card", cid, "CASE_ON_CARD")
            for ce in cc_edges:
                related_cases.append({"case_id": ce["to_id"], "card_id": cid})

        return {
            "device_id": device_id,
            "transaction_count": len(txn_ids),
            "card_ids": list(card_ids),
            "card_count": len(card_ids),
            "related_closed_cases": related_cases,
        }
    except Exception as e:
        return {"device_id": device_id, "error": str(e), "card_ids": []}


def get_customer_profile(customer_id: str) -> dict:
    """Return all cards owned by a customer, summary of history, and closed cases."""
    client = get_client()
    try:
        card_edges = client.get_edges("Customer", customer_id, "OWNS")
        cards = [e["to_id"] for e in card_edges]
        profile = {"customer_id": customer_id, "cards": cards}

        all_txns = []
        closed_cases = []
        for cid in cards:
            hist = get_card_history(cid, days=365)
            all_txns.extend(hist.get("transactions", []))
            cc_edges = client.get_edges("Card", cid, "CASE_ON_CARD")
            for e in cc_edges:
                v = client.get_vertex("ClosedCase", e["to_id"])
                if v:
                    closed_cases.append(v.get("attributes", {}))

        profile["total_transactions"] = len(all_txns)
        if all_txns:
            profile["typical_amounts"] = sorted([float(t.get("amount", 0)) for t in all_txns])
            profile["channels"] = list({t.get("channel") for t in all_txns})
            profile["products"] = list({t.get("product_cd") for t in all_txns})
        profile["closed_cases"] = closed_cases
        return profile
    except Exception as e:
        return {"customer_id": customer_id, "error": str(e)}


def get_billing_region_history(card_id: str) -> dict:
    """Return all billing regions this card has been used in."""
    client = get_client()
    try:
        edges = client.get_edges("Card", card_id, "MADE")
        region_counts: dict[str, int] = {}
        for e in edges:
            tid = e["to_id"]
            br_edges = client.get_edges("Transaction", tid, "BILLED_IN")
            for br in br_edges:
                r = br["to_id"]
                region_counts[r] = region_counts.get(r, 0) + 1
        home_region = max(region_counts, key=region_counts.get) if region_counts else None
        return {
            "card_id": card_id,
            "region_counts": region_counts,
            "home_region": home_region,
            "distinct_regions": len(region_counts),
        }
    except Exception as e:
        return {"card_id": card_id, "error": str(e)}


def search_similar_closed_cases(
    pattern: str = "",
    device_id: str = "",
    card_id: str = "",
    limit: int = 5,
) -> dict:
    """Retrieve closed cases similar to the current investigation."""
    client = get_client()
    try:
        results = []
        if card_id:
            cc_edges = client.get_edges("Card", card_id, "CASE_ON_CARD")
            for e in cc_edges[:limit]:
                v = client.get_vertex("ClosedCase", e["to_id"])
                if v:
                    results.append(v.get("attributes", {}))

        if device_id and len(results) < limit:
            dn = get_device_neighbors(device_id)
            for cid in dn.get("card_ids", [])[:5]:
                cc_edges = client.get_edges("Card", cid, "CASE_ON_CARD")
                for e in cc_edges[:2]:
                    v = client.get_vertex("ClosedCase", e["to_id"])
                    if v and v.get("attributes") not in results:
                        results.append(v.get("attributes", {}))
                if len(results) >= limit:
                    break

        return {"similar_cases": results[:limit], "count": len(results[:limit])}
    except Exception as e:
        return {"error": str(e), "similar_cases": []}


def write_investigation_case(case_data: dict) -> dict:
    """Write an InvestigationCase vertex to TigerGraph and link it to the card."""
    client = get_client()
    try:
        graph_case_id = f"CASE-{case_data.get('hhg_case_id', 'UNKNOWN')}"
        attrs = {
            "hhg_case_id": case_data.get("hhg_case_id", ""),
            "status": case_data.get("status", "open"),
            "verdict": case_data.get("verdict", "uncertain"),
            "fraud_probability": float(case_data.get("fraud_probability", 0.5)),
            "pattern": case_data.get("pattern", "none"),
            "exposure_usd": float(case_data.get("exposure_usd", 0.0)),
            "summary": case_data.get("summary", ""),
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "closed_at": "",
            "answer_json": case_data.get("answer_json", ""),
        }

        payload: dict[str, Any] = {
            "vertices": {"InvestigationCase": {graph_case_id: attrs}},
            "edges": {}
        }

        card_id = case_data.get("card_id")
        if card_id:
            payload["edges"]["InvestigationCase"] = {
                graph_case_id: {"INV_ON_CARD": {"Card": {card_id: {}}}}
            }

        client.upsert_graph(payload)
        return {"success": True, "graph_case_id": graph_case_id}
    except Exception as e:
        return {"success": False, "error": str(e), "graph_case_id": ""}


def get_transaction_velocity(card_id: str, txn_id: str, window_hours: int = 24) -> dict:
    """Count transactions and total amount in the window_hours window before txn_id."""
    window_data = get_card_window(card_id, txn_id, hours=window_hours)
    txns = window_data.get("transactions", [])
    anchor_ts_str = window_data.get("anchor_ts", "")
    if anchor_ts_str:
        try:
            anchor_ts = datetime.strptime(anchor_ts_str, "%Y-%m-%d %H:%M:%S")
            txns = [
                t for t in txns
                if datetime.strptime(t.get("ts", "1900-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S") <= anchor_ts
            ]
        except Exception:
            pass
    total_amount = sum(float(t.get("amount", 0)) for t in txns)
    small_auths = [t for t in txns if float(t.get("amount", 0)) < 5]
    return {
        "card_id": card_id,
        "window_hours": window_hours,
        "txn_count": len(txns),
        "total_amount": total_amount,
        "small_auth_count": len(small_auths),
        "transactions": txns,
    }
