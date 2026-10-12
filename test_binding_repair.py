import unittest
from binding_repair import BindingRejected, BindingRepairSession, SchemaAwareBinder

SCHEMA = [
    {'table':'daily_prices','columns':[{'name':x} for x in ('ticker','trade_date','close_price')]},
    {'table':'companies','columns':[{'name':x} for x in ('ticker','company_name')]},
]
REQ = {'id':'r2','kind':'rows','database':'market','table':'unknown',
       'filters':{'instrument':'DBS','code':'D05'},'date_column':'date',
       'value_column':'closing_price','boundary':'first','count':5,
       'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}}
BAD = {'table':'daily_prices','filters':{'ticker':'DBS','code':'D05'},
       'date_column':'trade_date','value_column':'close_price',
       'filter_sources':{'ticker':['instrument'],'code':['code']}}
GOOD = {'table':'daily_prices','filters':{'ticker':'D05'},
        'date_column':'trade_date','value_column':'close_price',
        'filter_sources':{'ticker':['instrument','code']},
        'identity_bridges':[{'logical_key':'instrument','physical_column':'ticker',
                             'table':'companies','alias_column':'company_name',
                             'identifier_column':'ticker'}]}

class Tests(unittest.TestCase):
    def binder(self, linked=True, present=True):
        return SchemaAwareBinder(SCHEMA,
            lambda db,t,c,v: present and (t,c,v)==('daily_prices','ticker','D05'),
            lambda db,t,a,av,i,iv: linked and (t,a,av,i,iv)==
                ('companies','company_name','DBS','ticker','D05'))
    def test_unknown_column_is_rejected_before_probe(self):
        binder = SchemaAwareBinder(SCHEMA, lambda *args: self.fail('probe must not run'),
                                   lambda *args: self.fail('relation must not run'))
        with self.assertRaisesRegex(BindingRejected, 'UNKNOWN_FILTER_COLUMNS:code'):
            binder.verify(REQ, BAD)
    def test_verified_bridge_succeeds(self):
        result = self.binder().verify(REQ, GOOD)
        self.assertEqual(result.filters, {'ticker':'D05'})
        self.assertEqual([p['type'] for p in result.proofs], ['source_value','identity_relation'])
        self.assertEqual(REQ['table'], 'unknown')  # immutable logical obligation
    def test_unverified_alias_rejected(self):
        with self.assertRaisesRegex(BindingRejected, 'IDENTITY_RELATION_NOT_VERIFIED'):
            self.binder(linked=False).verify(REQ, GOOD)
    def test_missing_physical_value_rejected(self):
        with self.assertRaisesRegex(BindingRejected, 'UNVERIFIED_PHYSICAL_VALUE'):
            self.binder(present=False).verify(REQ, GOOD)
    def test_repair_feedback_and_duplicate_guard(self):
        session=BindingRepairSession(self.binder(), REQ)
        self.assertIsNone(session.submit(BAD))
        self.assertEqual(session.next_prompt()['previous_rejections'][0]['reason'],
                         'UNKNOWN_FILTER_COLUMNS:code')
        with self.assertRaisesRegex(BindingRejected, 'REPEATED_INVALID_BINDING_PROPOSAL'):
            session.submit(BAD)
    def test_repair_accepts_corrected_proposal(self):
        session=BindingRepairSession(self.binder(), REQ)
        self.assertIsNone(session.submit(BAD))
        self.assertEqual(session.submit(GOOD).filters, {'ticker':'D05'})

if __name__=='__main__': unittest.main()
