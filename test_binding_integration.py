import sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from binding_integration import resolve_verified_binding, assert_sql_binding_ready
from binding_repair import BindingRejected
from test_binding_repair import REQ, BAD, GOOD, SCHEMA

class Model:
    def __init__(self, replies):
        self.replies=iter(replies)
        self.calls=[]
    def ask(self,system,payload):
        self.calls.append(payload)
        return next(self.replies)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'market.db'
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('CREATE TABLE daily_prices(ticker TEXT,trade_date TEXT,close_price REAL)')
            c.execute('CREATE TABLE companies(ticker TEXT,company_name TEXT)')
            c.execute('INSERT INTO daily_prices VALUES (?,?,?)',('D05','2024-01-02',29.0))
            c.execute('INSERT INTO companies VALUES (?,?)',('D05','DBS'))
            c.commit()
        self.ledger=[{'id':'e1','tool':'discover_schema','args':{'database':'market'},
                      'result':{'database':'market','tables':SCHEMA}}]
    def run_binding(self, replies):
        model=Model(replies)
        result=resolve_verified_binding(model=model,requirement=REQ,
              schema_evidence=self.ledger[0]['result'],db_paths={'market':str(self.path)},
              query='first five prices',jev={},uql_plan={},evidence_ledger=self.ledger)
        return result,model
    def test_invalid_then_repaired_with_evidence(self):
        result,model=self.run_binding([BAD,GOOD])
        self.assertTrue(assert_sql_binding_ready(REQ,result))
        self.assertEqual(model.calls[1]['previous_rejections'][0]['reason'],
                         'UNKNOWN_FILTER_COLUMNS:code')
        self.assertEqual([e['tool'] for e in self.ledger],
                         ['discover_schema','verify_binding_source','verify_binding_source'])
    def test_identical_bad_binding_blocked(self):
        with self.assertRaisesRegex(BindingRejected,'REPEATED_INVALID_BINDING_PROPOSAL'):
            self.run_binding([BAD,BAD])
        self.assertEqual(len(self.ledger),1)
    def test_sql_blocked_without_binding(self):
        with self.assertRaisesRegex(BindingRejected,'ROW_BINDING_NOT_VERIFIED'):
            assert_sql_binding_ready(REQ,None)
    def test_sql_blocked_after_requirement_mutation(self):
        binding,_=self.run_binding([GOOD])
        altered={**REQ,'count':7}
        with self.assertRaisesRegex(BindingRejected,'BINDING_REQUIREMENT_CHANGED'):
            assert_sql_binding_ready(altered,binding)

if __name__=='__main__': unittest.main()
