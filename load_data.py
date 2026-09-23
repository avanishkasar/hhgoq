"""
load_data.py — High-speed REST++ data loader for TigerGraph Savanna.

Usage:
    python load_data.py --sample 5000     # quick test
    python load_data.py                   # full ingestion
    python load_data.py --closed-only     # only load 5,565 closed cases
"""

import os
import sys
import csv
import hashlib
import argparse
from datetime import datetime, timedelta
from tqdm import tqdm
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()
from agent.graph_client import get_client

DATA_DIR = os.path.join(os.path.dirname(__file__), "HHGOA_IEEE")
EPOCH = datetime(2016, 7, 2, 0, 0, 0)


def make_device_id(device_info: str, os_str: str, browser: str, screen: str) -> str:
    raw = f"{device_info}|{os_str}|{browser}|{screen}"
    return "D" + hashlib.md5(raw.encode()).hexdigest()[:15]


def ts_from_dt(transaction_dt_str: str) -> str:
    try:
        delta = timedelta(seconds=int(float(transaction_dt_str)))
        return (EPOCH + delta).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def load_identity(path: str) -> dict:
    print("Pre-loading identity.csv...")
    identity_map = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="identity"):
            tid = row["TransactionID"]
            identity_map[tid] = row
    print(f"  Loaded {len(identity_map)} identity records.")
    return identity_map


def load_closed_cases(client):
    print("\nLoading closed cases history (5,565 cases)...")
    path = os.path.join(DATA_DIR, "closed_cases_history.csv")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    vertices = {}
    edges = {"Card": {}, "ClosedCase": {}}
    count = 0

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="closed_cases"):
            case_id = row["case_id"]
            card_id = row.get("card_id", "")
            customer_id = row.get("customer_id", "")

            vertices[case_id] = {
                "customer_id": customer_id,
                "card_id": card_id,
                "opened_at": row.get("opened_at", ""),
                "closed_at": row.get("closed_at", ""),
                "outcome": row.get("outcome", ""),
                "pattern": row.get("pattern", ""),
                "first_fraud_txn_id": row.get("first_fraud_txn_id", ""),
                "txn_ids": row.get("txn_ids", ""),
                "n_txns": int(row.get("n_txns", 0) or 0),
                "exposure_usd": float(row.get("exposure_usd", 0) or 0),
                "connected_card_ids": row.get("connected_card_ids", ""),
                "actions_taken": row.get("actions_taken", ""),
                "report_filed": row.get("report_filed", ""),
                "analyst_notes": row.get("analyst_notes", ""),
            }

            if card_id:
                edges["Card"].setdefault(card_id, {}).setdefault("CASE_ON_CARD", {})["ClosedCase"] = {case_id: {}}

            count += 1
            if len(vertices) >= 500:
                client.upsert_graph({"vertices": {"ClosedCase": vertices}, "edges": edges})
                vertices = {}
                edges = {"Card": {}, "ClosedCase": {}}

    if vertices:
        client.upsert_graph({"vertices": {"ClosedCase": vertices}, "edges": edges})

    print(f"  [OK] Successfully loaded {count} closed cases into TigerGraph.")


def load_transactions(client, identity_map: dict, limit: int | None = None):
    print(f"\nLoading transactions (limit: {limit or 'ALL'})...")
    path = os.path.join(DATA_DIR, "transactions.csv")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    cust_v = {}
    card_v = {}
    txn_v = {}
    dev_v = {}
    email_v = {}
    region_v = {}

    card_edges = {}
    txn_edges = {}
    cust_edges = {}

    prev_txn_by_card = {}
    count = 0
    BATCH_SIZE = 1000

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="transactions"):
            if limit and count >= limit:
                break

            txn_id = row["TransactionID"]
            customer_id = row.get("customer_id", "")
            card_id = customer_id + "-K1" if customer_id else ""
            ts_str = row.get("ts", "") or ts_from_dt(row.get("TransactionDT", "0"))

            # Customer & Card
            if customer_id:
                cust_v[customer_id] = {}
                card_v[card_id] = {
                    "card1": row.get("card1", ""),
                    "card2": row.get("card2", ""),
                    "card3": row.get("card3", ""),
                    "card4": row.get("card4", ""),
                    "card5": row.get("card5", ""),
                    "card6": row.get("card6", ""),
                }
                cust_edges.setdefault(customer_id, {}).setdefault("OWNS", {})["Card"] = {card_id: {}}

            # Transaction
            try:
                amt = float(row.get("TransactionAmt", 0) or 0)
                risk = float(row.get("risk_score", 0) or 0)
            except Exception:
                amt, risk = 0.0, 0.0

            txn_v[txn_id] = {
                "amount": amt,
                "product_cd": row.get("ProductCD", ""),
                "addr1": row.get("addr1", ""),
                "addr2": row.get("addr2", ""),
                "p_email": row.get("P_emaildomain", ""),
                "r_email": row.get("R_emaildomain", ""),
                "channel": row.get("channel", ""),
                "risk_score": risk,
                "ts": ts_str,
                "dist1": float(row.get("dist1") or 0),
                "dist2": float(row.get("dist2") or 0),
                "c_features": "",
                "d_features": "",
                "m_features": "",
            }

            if card_id:
                card_edges.setdefault(card_id, {}).setdefault("MADE", {})["Transaction"] = {txn_id: {}}

            # NEXT_TXN within card
            if card_id in prev_txn_by_card:
                prev_tid = prev_txn_by_card[card_id]
                txn_edges.setdefault(prev_tid, {}).setdefault("NEXT_TXN", {})["Transaction"] = {txn_id: {}}
            prev_txn_by_card[card_id] = txn_id

            # Device
            identity = identity_map.get(txn_id)
            if identity:
                did = make_device_id(
                    identity.get("DeviceInfo", ""),
                    identity.get("id_30", ""),
                    identity.get("id_31", ""),
                    identity.get("id_33", ""),
                )
                dev_v[did] = {
                    "device_type": identity.get("DeviceType", ""),
                    "device_info": identity.get("DeviceInfo", ""),
                    "os": identity.get("id_30", ""),
                    "browser": identity.get("id_31", ""),
                    "screen": identity.get("id_33", ""),
                    "proxy_type": identity.get("id_23", ""),
                    "id_15": identity.get("id_15", ""),
                }
                txn_edges.setdefault(txn_id, {}).setdefault("FROM_DEVICE", {})["DeviceProfile"] = {did: {}}

            # Email
            p_email = row.get("P_emaildomain", "")
            if p_email:
                email_v[p_email] = {}
                txn_edges.setdefault(txn_id, {}).setdefault("PURCHASER_EMAIL", {})["EmailDomain"] = {p_email: {}}

            # Region
            addr1 = row.get("addr1", "")
            if addr1:
                region_v[addr1] = {"country_code": row.get("addr2", "")}
                txn_edges.setdefault(txn_id, {}).setdefault("BILLED_IN", {})["BillingRegion"] = {addr1: {}}

            count += 1

            # Flush batch
            if count % BATCH_SIZE == 0:
                payload = {
                    "vertices": {
                        "Customer": cust_v,
                        "Card": card_v,
                        "Transaction": txn_v,
                        "DeviceProfile": dev_v,
                        "EmailDomain": email_v,
                        "BillingRegion": region_v,
                    },
                    "edges": {
                        "Customer": cust_edges,
                        "Card": card_edges,
                        "Transaction": txn_edges,
                    }
                }
                client.upsert_graph(payload)
                cust_v, card_v, txn_v, dev_v, email_v, region_v = {}, {}, {}, {}, {}, {}
                card_edges, txn_edges, cust_edges = {}, {}, {}

        # Final flush
        if txn_v:
            payload = {
                "vertices": {
                    "Customer": cust_v,
                    "Card": card_v,
                    "Transaction": txn_v,
                    "DeviceProfile": dev_v,
                    "EmailDomain": email_v,
                    "BillingRegion": region_v,
                },
                "edges": {
                    "Customer": cust_edges,
                    "Card": card_edges,
                    "Transaction": txn_edges,
                }
            }
            client.upsert_graph(payload)

    print(f"  [OK] Successfully loaded {count} transactions.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None, help="Load only first N transactions")
    parser.add_argument("--closed-only", action="store_true", help="Only load closed cases")
    args = parser.parse_args()

    client = get_client()
    print("Connected to TigerGraph REST++ API.")

    if args.closed_only:
        load_closed_cases(client)
    else:
        identity_map = load_identity(os.path.join(DATA_DIR, "identity.csv"))
        load_transactions(client, identity_map, limit=args.sample)
        load_closed_cases(client)

    print("\n[OK] Done! Data is populated in TigerGraph.")


if __name__ == "__main__":
    main()
