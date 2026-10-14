"""Tuned fork, fix 3: offline, scripted model (the same style as test_core_regression.py)."""
import json, sqlite3, tempfile, unittest
from pathlib import Path
from agent_api.core import Config, ResearchAgent
from agent_api.output_contracts import response_format


class Scripted:
    """A document plan; tool choices replayed from `decisions`; a final answer when asked for one."""
    def __init__(self, decisions, audit_covered=True, repair=None):
        self.decisions, self.audit_covered, self.repair, self.payloads = list(decisions), audit_covered, repair, []
    def ask(self, system, payload):
        self.payloads.append(payload)
        if 'tools' in payload and 'query' in payload and not payload.get('task'):
            return {"jev": {"user_intent": "find", "concepts": ["x"], "temporal_scope": None, "ambiguities": [],
                            "evidence_goals": ["Locate the term sheet", "State its coupon"]},
                    "uql_plan": {k: [] for k in ("research_questions", "dependent_tasks", "proposed_tools",
                                                  "validation_requirements")},
                    "requirements": [{"id": "r1", "kind": "source", "description": "find it", "tool": "search_documents"}]}
        if payload.get('task') == 'audit_plan_completeness':
            n = len(payload['jev']['evidence_goals'])
            return {"coverage": [{"goal_index": i, "requirement_ids": ["r1"], "covered": self.audit_covered or i == 0,
                                  "goal_type": "content"} for i in range(n)], "missing_goals": []}
        if payload.get('task') == 'repair_incomplete_plan':
            return self.repair if self.repair is not None else {"added_requirements": []}
        if 'required_citation_ids' in payload:
            return {"action": "final", "answer": "done", "evidence_ids": payload['required_citation_ids'], "limitations": []}
        return self.decisions.pop(0) if self.decisions else {"action": "final", "answer": "x"}


class Fix3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        from metadata.database import SCHEMA
        md = d / "metadata.db"; con = sqlite3.connect(md); con.executescript(SCHEMA); con.commit(); con.close()
        mk = d / "market.db"; sqlite3.connect(mk).close()
        (d / "docs").mkdir()
        self.cfg = Config(market_db=str(mk), metadata_db=str(md), documents_dir=str(d / "docs"), max_rounds=6)
    def tearDown(self):
        self.tmp.cleanup()

    def test_the_tool_choice_step_has_a_schema(self):
        f = response_format({"missing_requirements": [], "tool_catalog": [{"name": "search_documents"}]})
        tool = f["anyOf"][0]["properties"]
        self.assertEqual(tool["action"], {"const": "tool"})
        self.assertEqual(tool["tool"], {"enum": ["search_documents"]})
        self.assertNotIn("final", json.dumps(f))

    def test_two_bad_replies_no_longer_end_the_turn_and_the_reason_is_shown(self):
        bad = {"action": "final", "answer": "too early"}
        good = {"action": "tool", "tool": "search_documents", "args": {"query": "term sheet"}}
        model = Scripted([bad, bad, good])
        out = ResearchAgent(self.cfg, model=model).run("find the term sheet")
        self.assertEqual([t.get("tool") for t in out["trace"] if t.get("tool")], ["search_documents"])
        rejected = [t for t in out["trace"] if t.get("error") == "INVALID_ACTION_OR_PREMATURE_FINAL"]
        self.assertEqual(len(rejected), 2)
        self.assertIn("tool_catalog", rejected[0]["reason"])
        # the next decision saw the reason
        later = [p for p in model.payloads if "prior_actions" in p][-1]
        self.assertTrue(any("reason" in a for a in later["prior_actions"]))

    def test_three_bad_replies_still_stop(self):
        bad = {"action": "final", "answer": "too early"}
        out = ResearchAgent(self.cfg, model=Scripted([bad, bad, bad, bad])).run("find the term sheet")
        self.assertEqual(sum(t.get("error") == "INVALID_ACTION_OR_PREMATURE_FINAL" for t in out["trace"]), 3)

    def test_an_uncovered_goal_in_a_document_plan_becomes_a_search_obligation(self):
        good = {"action": "tool", "tool": "search_documents", "args": {"query": "term sheet coupon"}}
        out = ResearchAgent(self.cfg, model=Scripted([good, good], audit_covered=False)).run("coupon of the term sheet")
        self.assertNotEqual(out["status"], "BLOCKED_INCOMPLETE_RESEARCH_PLAN")
        fb = [t for t in out["trace"] if t.get("phase") == "PLAN_GOAL_FALLBACK"]
        self.assertEqual(fb[0]["goals"], ["State its coupon"])
        added = [r for r in out["requirements"] if r["id"] in fb[0]["added"]]
        self.assertEqual([(r["kind"], r["tool"]) for r in added], [("source", "search_documents")])


if __name__ == "__main__":
    unittest.main()
