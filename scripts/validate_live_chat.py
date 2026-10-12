"""Run live API checks and compare cited evidence with original local sources.

PowerShell: $env:UQL_API_TOKEN='...'; python -m scripts.validate_live_chat --case document
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


QUERIES = {
    "sql": "Retrieve the first five available D05 closing prices in January 2024. "
           "Return the source observations directly; no arithmetic is requested.",
    "document": "Read the original DOCX file D05_Investment_Committee_Note.docx "
                "for DBS Group (D05) and report NIM, ROE and CET1 from its Key Metrics "
                "table. Use document evidence, not SQL rows or catalog summaries.",
}


def verify(case, response, market_db, documents_dir):
    errors = []
    if response.get("status") != "COMPLETED":
        errors.append("API did not complete: " + str(response.get("status")))
    evidence = {e["id"]: e for e in response.get("evidence", [])}
    cited = set(response.get("citations", []))
    if not cited or not cited.issubset(evidence):
        errors.append("Missing or unknown citations")
    answer = response.get("answer") or ""
    if set(re.findall(r"\[(e\d+)\]", answer)) != cited:
        errors.append("Inline citations disagree with response citations")
    if case == "sql":
        with closing(sqlite3.connect(f"file:{Path(market_db).resolve().as_posix()}?mode=ro", uri=True)) as c:
            expected = c.execute("SELECT trade_date, close_price FROM daily_prices "
                "WHERE ticker='D05' AND trade_date BETWEEN '2024-01-01' AND '2024-01-31' "
                "ORDER BY trade_date LIMIT 5").fetchall()
        matches = [e for e in evidence.values() if e["tool"] == "read_sql"
                   and e["id"] in cited and e["args"].get("database") == "market"
                   and [(r.get("trade_date"), r.get("close_price"))
                        for r in e["result"].get("rows", [])] == expected
                   and all(r.get("ticker") == "D05" for r in e["result"].get("rows", []))]
        if not matches:
            errors.append("Cited SQL evidence differs from the original five price rows")
        if any(date not in answer or str(price) not in answer for date, price in expected):
            errors.append("Answer omitted or changed a source date/price")
    else:
        from docx import Document
        original = Document(Path(documents_dir)/"docx/company/D05_Investment_Committee_Note.docx")
        expected = {r.cells[0].text: r.cells[1].text for r in original.tables[0].rows[1:]
                    if r.cells[0].text in ("NIM", "ROE", "CET1")}
        docs = [e for e in evidence.values() if e["tool"] == "inspect_document"
                and e["id"] in cited and e["result"].get("name") == "D05_Investment_Committee_Note.docx"]
        if not docs:
            errors.append("No cited original DBS document inspection")
        for label, value in expected.items():
            if label not in answer or value not in answer:
                errors.append("Answer missing source metric: " + label + "=" + value)
            if not any(value in e["result"].get("content", "") and e["result"].get("units") for e in docs):
                errors.append("Metric absent from located document evidence: " + label)
    return {"passed": not errors, "errors": errors, "expected": expected}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=QUERIES, required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:8001")
    p.add_argument("--market-db", default="data/market_data/market.db")
    p.add_argument("--documents-dir", default="data/documents")
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    path = Path("test_results")/f"live_{args.case}.json"
    if args.verify_only:
        record = json.loads(path.read_text(encoding="utf-8"))
    else:
        token = os.environ["UQL_API_TOKEN"]
        request = Request(args.base_url.rstrip("/")+"/v1/chat",
                          data=json.dumps({"message": QUERIES[args.case]}).encode(),
                          headers={"Authorization": "Bearer "+token, "Content-Type": "application/json"})
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=1800) as f:
                status, response = f.status, json.load(f)
        except HTTPError as e:
            status, response = e.code, {"status": "HTTP_ERROR", "detail": e.read().decode()}
        record = {"query": QUERIES[args.case], "http_status": status,
                  "elapsed_seconds": time.perf_counter()-started, "response": response}
    record["verification"] = verify(args.case, record["response"], args.market_db, args.documents_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "status": record["response"].get("status"),
                      "elapsed_seconds": record["elapsed_seconds"],
                      "verification": record["verification"]}, indent=2))
    raise SystemExit(0 if record["verification"]["passed"] else 1)


if __name__ == "__main__":
    main()
