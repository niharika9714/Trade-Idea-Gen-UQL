import sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from binding_repair import SchemaAwareBinder, BindingRejected
from sqlite_binding_adapter import SQLiteBindingAdapter
from test_binding_repair import SCHEMA, REQ, GOOD

class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name)/'market.db'
        with closing(sqlite3.connect(path)) as c:
            c.execute('CREATE TABLE daily_prices(ticker TEXT, trade_date TEXT, close_price REAL)')
            c.execute('CREATE TABLE companies(ticker TEXT, company_name TEXT)')
            c.execute('INSERT INTO daily_prices VALUES (?,?,?)',('D05','2024-01-02',29.0))
            c.execute('INSERT INTO companies VALUES (?,?)',('D05','DBS'))
            c.commit()
        self.adapter = SQLiteBindingAdapter({'market':str(path)})
    def test_real_database_binding(self):
        binder=SchemaAwareBinder(SCHEMA,self.adapter.probe,self.adapter.relation)
        binding=binder.verify(REQ, GOOD)
        self.assertEqual(binding.table,'daily_prices')
    def test_nonexistent_identifier_rejected(self):
        binder=SchemaAwareBinder(SCHEMA,self.adapter.probe,self.adapter.relation)
        proposal={**GOOD,'filters':{'ticker':'O39'}}
        with self.assertRaisesRegex(BindingRejected,'UNVERIFIED_PHYSICAL_VALUE'):
            binder.verify(REQ,proposal)
    def test_alias_mismatch_rejected(self):
        with closing(sqlite3.connect(self.adapter.database_paths['market'])) as c:
            c.execute("UPDATE companies SET company_name='DBS Group'")
            c.commit()
        binder=SchemaAwareBinder(SCHEMA,self.adapter.probe,self.adapter.relation)
        with self.assertRaisesRegex(BindingRejected,'IDENTITY_RELATION_NOT_VERIFIED'):
            binder.verify(REQ,GOOD)

if __name__=='__main__': unittest.main()
