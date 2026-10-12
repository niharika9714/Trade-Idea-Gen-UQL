"""Step 3: JSON Evidence View (JEV) query understanding. No evidence retrieval."""
from __future__ import annotations
import json, os, re, sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from core.enums import AgendaMode, ActionType, EvidenceType
from core.models import Agenda, AgendaGraph, Action, Concept, EvidenceRequirement
from app.config import METADATA_DB_PATH, MODEL_NAME

class JEVResult(BaseModel):
    graph: AgendaGraph
    temporal_scope: dict = Field(default_factory=dict)
    source_preferences: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    parser: str = "fallback"
    @model_validator(mode="after")
    def check(self):
        if self.clarification_needed and not self.clarification_question:
            raise ValueError("Clarification question required")
        return self

def validate_graph(graph: AgendaGraph):
    if not graph.agendas:
        raise ValueError("At least one agenda required")
    ids = {a.agenda_id for a in graph.agendas}
    color = {}
    edges = {a.agenda_id: a.depends_on for a in graph.agendas}
    def visit(node):
        if color.get(node) == 1:
            raise ValueError("Cyclic agenda dependency")
        if color.get(node) == 2:
            return
        color[node] = 1
        for dep in edges[node]:
            if dep not in ids:
                raise ValueError("Unknown dependency")
            visit(dep)
        color[node] = 2
    for node in ids:
        visit(node)
    for a in graph.agendas:
        concept_ids = [c.concept_id for c in a.concepts]
        action_ids = [x.action_id for x in a.actions]
        req_ids = [x.requirement_id for x in a.evidence_requirements]
        if len(concept_ids)!=len(set(concept_ids)) or len(action_ids)!=len(set(action_ids)) or len(req_ids)!=len(set(req_ids)):
            raise ValueError("Duplicate child IDs")
        for x in a.actions:
            if set(x.targets)-set(concept_ids):
                raise ValueError("Action targets must reference concept IDs")
        for x in a.evidence_requirements:
            if set(x.concepts)-set(concept_ids):
                raise ValueError("Evidence concepts must reference concept IDs")
    return graph

def metadata_hints(db_path=METADATA_DB_PATH, max_items=60):
    """Read ONLY metadata catalog labels; never market data or document contents."""
    path=Path(db_path)
    if not path.is_file():
        return []
    result=[]
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True,timeout=2) as con:
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table,field in (("sql_columns","column_name"),("sql_tables","table_name"),("file_terms","term")):
                if table not in tables: continue
                cols={r[1] for r in con.execute(f"PRAGMA table_info({table})")}
                if field not in cols: continue
                rows=con.execute(f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL LIMIT ?",(max_items,)).fetchall()
                result.extend(str(r[0])[:90] for r in rows)
    except (sqlite3.Error,OSError):
        return []
    return list(dict.fromkeys(result))[:max_items]

def _mode(q):
    if re.search(r"\b(trade idea|strategy|recommend|propose|construct|generate|create)\b",q,re.I): return AgendaMode.CREATE
    if re.search(r"\b(compare|versus|vs\.?|why|explain|analy[sz]e|performance|impact|difference|trend)\b",q,re.I): return AgendaMode.ANALYZE
    return AgendaMode.FIND

def fallback(query):
    q=query.strip()
    if not q: raise ValueError("Empty query")
    mode=_mode(q)
    matches=re.findall(r"\b(?:D05|O39|U11|STAN|HSBA|DBS|OCBC|UOB|HSBC|ROE|ROA|NIM|CET1|NPL|EPS|P/E|P/B|revenue|dividends?|price|volume|earnings|valuation|interest rates?)\b",q,re.I)
    seen=set(); terms=[]
    for x in matches:
        if x.lower() not in seen: terms.append(x);seen.add(x.lower())
    if not terms: terms=[q[:100]]
    concepts=[Concept(concept_id=f"c{i}",surface_form=t,canonical=t.upper() if len(t)<=5 else t.lower(),concept_type="metric" if t.lower() in {"roe","roa","nim","cet1","npl","eps","price","volume","revenue","valuation"} else "entity_or_topic",weight=1.0 if i<2 else .8) for i,t in enumerate(terms,1)]
    temporal={}
    year=re.search(r"\b(20\d{2})\b",q)
    if year: temporal["year"]=int(year.group(1))
    month=re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",q,re.I)
    if month: temporal["month"]=month.group(1).lower()
    if re.search(r"\b(latest|current|today|recent)\b",q,re.I): temporal["relative"]="latest"
    requirements=[EvidenceRequirement(requirement_id="e1",description="Verify relevant primary-source observations and dates",evidence_types=[EvidenceType.FACT],concepts=[c.concept_id for c in concepts],freshness="latest" if temporal.get("relative") else None)]
    agendas=[Agenda(agenda_id="a1",objective="Find and verify primary evidence for: "+q,mode=AgendaMode.FIND,concepts=concepts,actions=[Action(action_id="act1",action=ActionType.FIND,targets=[c.concept_id for c in concepts])],evidence_requirements=requirements)]
    if mode!=AgendaMode.FIND:
        operation=ActionType.COMPARE if re.search(r"\b(compare|vs\.?|versus|difference)\b",q,re.I) else ActionType.EXPLAIN
        agendas.append(Agenda(agenda_id="a2",objective="Analyze verified evidence: "+q,mode=AgendaMode.ANALYZE,depends_on=["a1"],concepts=concepts,actions=[Action(action_id="act2",action=operation,targets=[c.concept_id for c in concepts])],evidence_requirements=[EvidenceRequirement(requirement_id="e2",description="Evidence-backed analysis and calculations",evidence_types=[EvidenceType.FACT,EvidenceType.DERIVED],concepts=[c.concept_id for c in concepts])]))
    if mode==AgendaMode.CREATE:
        agendas.append(Agenda(agenda_id="a3",objective="Form a conditional research hypothesis based on verified analysis: "+q,mode=AgendaMode.CREATE,depends_on=["a2"],concepts=concepts,actions=[Action(action_id="act3",action=ActionType.GENERATE_HYPOTHESIS,targets=[c.concept_id for c in concepts])],evidence_requirements=[EvidenceRequirement(requirement_id="e3",description="Hypothesis with evidence, assumptions and risks",evidence_types=[EvidenceType.FACT,EvidenceType.HYPOTHESIS],concepts=[c.concept_id for c in concepts])]))
    graph=validate_graph(AgendaGraph(original_query=q,agendas=agendas))
    return JEVResult(graph=graph,temporal_scope=temporal,parser="fallback")

SYSTEM="""You are the JEV query-understanding stage of a bank investment research assistant. Return ONLY a JSON object conforming to the provided JSON schema. Parse user intent into an agenda DAG: FIND evidence first; ANALYZE verified evidence next when requested; CREATE a conditional hypothesis only after analysis. Identify weighted concepts, actions, evidence requirements, dependencies, temporal scope and source preferences. Do not invent facts, market prices, conclusions, retrieved evidence, source availability or SQL. All action.targets and evidence_requirements.concepts must refer to concept_id in the same agenda. Each agenda ID unique, DAG acyclic. Preserve the original query exactly. For ambiguity, use clarification_needed and clarification_question. Prefer the user's exact financial terminology. Metadata hints are labels only, not facts."""

def parse_query(query, *, use_llm=True, model=MODEL_NAME, db_path=METADATA_DB_PATH, timeout=35):
    baseline=fallback(query)
    if not use_llm: return baseline
    hints=metadata_hints(db_path)
    payload={"model":model,"stream":False,"format":JEVResult.model_json_schema(),"options":{"temperature":0},"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps({"query":query,"metadata_labels":hints})}]}
    url=os.getenv("INVESTMENT_CHATBOT_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")+"/api/chat"
    try:
        req=Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=timeout) as response:
            result=json.loads(response.read())
        content=result["message"]["content"].strip()
        parsed=JEVResult.model_validate_json(content)
        if parsed.graph.original_query != query.strip(): raise ValueError("LLM modified original query")
        validate_graph(parsed.graph)
        parsed.parser="qwen"
        return parsed
    except (Exception) as exc:
        baseline.parser="fallback"
        return baseline
