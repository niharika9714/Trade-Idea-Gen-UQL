"""Market, product and tenor vocabulary (tuned fork, fix 1).

The unedited catalog matched question words literally and its alias list held bank names only, so "one-year USD/SGD
double-no-touch" never met a document that writes "12M USDSGD double no touch". `data/terminology.json` (exported from
a market and product vocabulary built outside this repository) is written into the catalog's own `terminology` table at build time; each
document is tagged with the groups it mentions, and a search query is expanded to every member of each group it names.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "terminology.json"
CONTEXT = "tuned-vocabulary"


def norm(text: str) -> str:
    """Lower case, with / - _ read as spaces, so "USD/SGD", "usd-sgd" and "usd sgd" are one spelling."""
    return re.sub(r"\s+", " ", re.sub(r"[/_\-]+", " ", str(text or "").lower())).strip()


def load(path: Path = PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def groups(rows: list[dict]) -> dict[str, set[str]]:
    """canonical -> every spelling of it, the canonical included, normalised."""
    out: dict[str, set[str]] = {}
    for r in rows:
        c = norm(r.get("canonical") or r.get("canonical_term"))
        t = norm(r.get("term"))
        if c and t:
            out.setdefault(c, {c}).add(t)
    return out


_RX: dict[int, list[tuple[str, re.Pattern]]] = {}


def _patterns(g: dict[str, set[str]]) -> list[tuple[str, re.Pattern]]:
    key = id(g)
    if key not in _RX:
        _RX[key] = [(c, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(m) for m in sorted(ms, key=len, reverse=True))
                                   + r")(?!\w)")) for c, ms in g.items()]
    return _RX[key]


def found(text: str, g: dict[str, set[str]]) -> list[str]:
    """The canonical names of every group the text mentions."""
    t = norm(text)
    return [c for c, rx in _patterns(g) if rx.search(t)]


def expand(query: str, g: dict[str, set[str]]) -> list[str]:
    """Every spelling of every group the query names, so either spelling in a document matches."""
    out: list[str] = []
    for c in found(query, g):
        for m in sorted(g[c]):
            if m not in out:
                out.append(m)
    return out


def write_table(con, rows: list[dict]) -> int:
    """The vocabulary into the catalog's terminology table (replacing what an earlier build of it wrote)."""
    con.execute("DELETE FROM terminology WHERE context=?", (CONTEXT,))
    n = 0
    for r in rows:
        tid = hashlib.sha256(f"{r['term']}|{r['canonical']}|{r['scope']}".encode()).hexdigest()[:24]
        con.execute("INSERT OR IGNORE INTO terminology(term_id,term,canonical_term,term_scope,context,description) "
                    "VALUES(?,?,?,?,?,?)", (tid, r["term"], r["canonical"], r["scope"], CONTEXT,
                                            f"{r['scope']}: '{r['term']}' is written '{r['canonical']}' in documents"))
        n += 1
    return n
