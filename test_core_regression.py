"""Deterministic, offline integration tests: actual SQLite tools, scripted LLM.
Run: python -m unittest -v test_core_regression.py
"""
import json, sqlite3, tempfile, unittest, os, unittest.mock
from contextlib import closing
from pathlib import Path
from agent_api.core import Config, ResearchAgent, Tools

class ScriptedModel:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []
    def ask(self, system, payload):
        self.calls.append(payload)
        if 'tools' in payload and 'query' in payload and 'requirements' not in payload:
            return self.plan
        if payload.get('task') == 'audit_plan_completeness':
            reqs = payload['requirements']
            # Existing regression fixtures use a generic evidence goal. Their
            # specified obligations are intentionally the test oracle.
            ids = [r['id'] for r in reqs if r['kind'] != 'schema']
            if not ids:
                ids = [r['id'] for r in reqs]
                goal_type = 'schema'
            else:
                goal_type = 'observations'
            return {'coverage':[{'goal_index':i,'requirement_ids':ids,
                     'covered':True,'goal_type':goal_type,'reason':'scripted test oracle'}
                     for i,_ in enumerate(payload['jev']['evidence_goals'])]}
        if payload.get('task') == 'resolve_row_bindings':
            return {'table':'daily_prices', 'filters':{'ticker':'D05'},
                    'date_column':'trade_date','value_column':'close_price',
                    'filter_sources':{'ticker':['instrument', 'identifier' if 'identifier' in payload['requirement'].get('filters', {}) else 'code']}}
        if 'missing_requirements' in payload and 'tool_catalog' in payload:
            missing = payload['missing_requirements']
            req = missing[0]
            kind = req['kind']
            if kind == 'schema':
                return {'action':'tool','tool':'discover_schema','args':{'database':req['database']}}
            if kind == 'rows' and req.get('table') == 'unresolved':
                return {'action':'tool','tool':'discover_schema','args':{'database':req['database']}}
            if kind == 'rows':
                order = 'DESC' if req.get('boundary') == 'last' else 'ASC'
                sql = f"SELECT ticker, trade_date, close_price FROM {req['table']} WHERE ticker = ? AND trade_date >= ? AND trade_date <= ? ORDER BY trade_date {order} LIMIT {req['count']}"
                return {'action':'tool','tool':'read_sql','args':{'database':'market','sql':sql,'parameters':[req['filters']['ticker'],'2024-01-01','2024-01-31']}}
            if kind == 'calculation':
                coverage = payload['requirement_coverage']
                ids = [x for dep in req['input_requirements'] for x in coverage[dep]['evidence_ids']]
                by_id = {e['id']:e for e in payload['evidence_log']}
                vals = []
                for dep in req['input_requirements']:
                    d = next(x for x in payload['requirements'] if x['id'] == dep)
                    eid = coverage[dep]['evidence_ids'][0]
                    if d['kind'] == 'rows':
                        vals.append(by_id[eid]['result']['rows'][0]['close_price'])
                    else:
                        vals.append(by_id[eid]['result']['result'])
                return {'action':'tool','tool':'calculate','args':{'operation':req['operation'],'values':vals,'source_evidence_ids':ids}}
            raise AssertionError(req)
        if 'missing_requirements' in payload and 'evidence_log' in payload:
            ids = [x['id'] for x in payload['evidence_log']]
            return {'action':'final','answer':'Verified synthetic observations and calculations ' + ' '.join('['+i+']' for i in ids), 'evidence_ids':ids,'limitations':['Synthetic dataset; not exchange-certified.']}
        raise AssertionError(payload)

class Regression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root/'market.db'
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('CREATE TABLE daily_prices (ticker TEXT, trade_date TEXT, close_price REAL)')
            conn.execute('CREATE TABLE companies (ticker TEXT, name TEXT)')
            conn.execute('CREATE TABLE instruments (ticker TEXT)')
            conn.execute('CREATE TABLE daily_volume (ticker TEXT, trade_date TEXT, volume INTEGER)')
            conn.execute('CREATE TABLE fundamentals (ticker TEXT)')
            conn.execute('CREATE TABLE dividends (ticker TEXT)')
            conn.execute('CREATE TABLE sector_prices (sector TEXT)')
            for ticker, values in [('D05',[29.9162,29.561,29.0748,28.8106,29.3451,30.0]),('O39',[19.5594,19.4,19.3,19.2,19.1,20.0])]:
                for day, price in enumerate(values,1):
                    conn.execute('INSERT INTO daily_prices VALUES (?,?,?)',(ticker,f'2024-01-{day:02}',price))
            conn.commit()
        self.cfg = Config(market_db=str(self.db),metadata_db=str(root/'metadata.db'),max_rounds=12)
        self.base = {'jev':{'user_intent':'test','concepts':[],'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},'ambiguities':[],'evidence_goals':['requested result']}, 'uql_plan':{'research_questions':[],'dependent_tasks':['discover','retrieve','validate'],'proposed_tools':['discover_schema','read_sql','calculate'],'validation_requirements':['validate all requirements']}}
    def run_plan(self, requirements, query):
        model=ScriptedModel({**self.base,'requirements':requirements})
        result=ResearchAgent(self.cfg,model=model).run(query)
        return result,model
    def test_1_schema_discovery(self):
        result,_=self.run_plan([{'id':'r1','kind':'schema','database':'market','description':'tables'}],'What tables are available in the market database?')
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(len(result['evidence']),1)
        self.assertTrue(result['requirement_coverage']['r1']['satisfied'])
    def test_live_planner_nested_schema_binding(self):
        # Reproduces the exact contract mismatch observed with live Qwen.
        req = [{'id':'r1','kind':'schema','description':'Discover tables in the market database',
                'schema':'database','rows':{'database':'market','table':'tables','filters':{}}}]
        result,_ = self.run_plan(req, 'What tables are available in the market database?')
        self.assertEqual(result['status'], 'COMPLETED', result)
        self.assertEqual(result['requirements'][0]['database'], 'market')
        self.assertTrue(result['requirement_coverage']['r1']['satisfied'])
        self.assertEqual(result['requirement_coverage']['r1']['evidence_ids'], ['e1'])

    def test_schema_binding_conflict_is_rejected(self):
        with self.assertRaisesRegex(Exception, 'CONFLICTING_SCHEMA_DATABASE_BINDINGS'):
            ResearchAgent._requirements([{'id':'r1','kind':'schema',
                'database':'market','rows':{'database':'metadata'}}])

    def test_2_first_five_observations(self):
        req=[{'id':'r1','kind':'schema','database':'market','description':'schema'},
             {'id':'r2','kind':'rows','database':'market','table':'unresolved','filters':{'ticker':'D05'},'date_column':'trade_date','value_column':'close_price','boundary':'first','count':5,'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},'description':'five rows'}]
        result,_=self.run_plan(req,'Retrieve the first five available DBS (D05) closing prices in January 2024')
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(result['requirements'][1]['table'],'daily_prices')
        self.assertEqual(len(result['evidence'][1]['result']['rows']),5)
        self.assertTrue(all(x['satisfied'] for x in result['requirement_coverage'].values()))
    def test_live_nested_unresolved_row_contract(self):
        req = [
            {'id':'r1','kind':'schema','schema':'database',
             'rows':{'database':'market','table':'unresolved'}},
            {'id':'r2','kind':'rows','schema':'database',
             'rows':{'database':'market','table':'unresolved',
                     'filters':{'instrument':'DBS','identifier':'D05'},
                     'date_column':'date','value_column':'closing_price',
                     'boundary':'first','count':5,
                     'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}}}
        ]
        # DBS is a descriptive alias, not a physical column. A semantic binding
        # must preserve D05 but can resolve the alias through the JEV/UQL.
        model = ScriptedModel({**self.base, 'requirements':req})
        agent = ResearchAgent(self.cfg, model=model)
        result = agent.run('Retrieve first five DBS (D05) closes in January 2024')
        self.assertEqual(result['status'], 'COMPLETED', result)
        self.assertTrue(all(x['satisfied'] for x in result['requirement_coverage'].values()))
        self.assertEqual(result['requirements'][1]['table'], 'daily_prices')
        self.assertEqual(len(next(e for e in result['evidence'] if e['tool']=='read_sql')['result']['rows']), 5)

    def test_probe_rejects_unobserved_filter_literal(self):
        tools=Tools(self.cfg)
        result=tools.run('probe_column_values',{'database':'market','table':'daily_prices',
            'column':'ticker','candidates':['DBS']})
        self.assertEqual(result['values'],[])
        valid=tools.run('probe_column_values',{'database':'market','table':'daily_prices',
            'column':'ticker','candidates':['D05']})
        self.assertEqual(valid['values'],['D05'])

    def test_probe_rejects_unknown_physical_column(self):
        with self.assertRaisesRegex(Exception,'UNKNOWN_COLUMN'):
            Tools(self.cfg).run('probe_column_values',{'database':'market',
                'table':'daily_prices','column':'code','candidates':['D05']})

    def test_live_logical_alias_uses_source_verified_value(self):
        raw=[{'id':'r1','kind':'rows','schema':'market','rows':'prices',
              'filters':{'instrument':'DBS','code':'D05'},'date_column':'date',
              'value_column':'closing_price','boundary':'first','count':5,
              'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},
              'description':'first five closes'},
             {'id':'r2','kind':'schema','schema':'market','description':'discover schema'}]
        result,_=self.run_plan(raw,'Retrieve first five DBS D05 closing prices in January 2024')
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(result['requirements'][0]['filters'],{'ticker':'D05'})
        self.assertTrue(any(e['tool']=='probe_column_values' and e['result']['values']==['D05']
                            for e in result['evidence']))
        self.assertTrue(result['requirement_coverage']['r1']['satisfied'])

    def test_live_schema_as_database_and_rows_as_logical_collection(self):
        # Exact structural variant observed in the second live Qwen attempt.
        raw = [
            {'id':'r1','kind':'rows','description':'Retrieve DBS prices',
             'schema':'market','rows':'prices',
             'filters':{'instrument':'DBS','code':'D05'},
             'date_column':'date','value_column':'closing_price',
             'boundary':'first','count':5,
             'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}},
            {'id':'r2','kind':'schema','description':'Discover schema',
             'schema':'market','rows':'prices',
             'filters':{'instrument':'DBS','code':'D05'}}]
        requirements = ResearchAgent._requirements(raw)
        self.assertEqual(requirements[0]['database'], 'market')
        self.assertEqual(requirements[0]['table'], 'unresolved')
        self.assertEqual(requirements[0]['logical_collection'], 'prices')
        self.assertEqual(requirements[0]['filters'], {'instrument':'DBS','code':'D05'})
        self.assertEqual(requirements[0]['count'], 5)
        self.assertEqual(requirements[1]['database'], 'market')
        self.assertNotIn('rows', requirements[1])
        self.assertFalse(ResearchAgent(self.cfg, model=ScriptedModel(self.base))._coverage(requirements, [])['r1']['satisfied'])

    def test_live_schema_label_contract_end_to_end(self):
        raw = [
            {'id':'r1','kind':'rows','description':'Retrieve DBS prices',
             'schema':'market','rows':'prices',
             'filters':{'instrument':'DBS','code':'D05'},
             'date_column':'date','value_column':'closing_price',
             'boundary':'first','count':5,
             'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}},
            {'id':'r2','kind':'schema','description':'Discover schema',
             'schema':'market','rows':'prices',
             'filters':{'instrument':'DBS','code':'D05'}}]
        result,_ = self.run_plan(raw, 'Retrieve first five DBS D05 closing prices in January 2024')
        self.assertEqual(result['status'], 'COMPLETED', result)
        self.assertTrue(all(c['satisfied'] for c in result['requirement_coverage'].values()))
        self.assertEqual(result['requirements'][0]['filters'], {'ticker':'D05'})
        self.assertEqual(len(next(e for e in result['evidence'] if e['tool']=='read_sql')['result']['rows']), 5)

    def test_schema_database_conflict_from_schema_label(self):
        with self.assertRaisesRegex(Exception, 'CONFLICTING_SCHEMA_DATABASE_BINDINGS'):
            ResearchAgent._requirements([{'id':'r1','kind':'schema',
                'schema':'market','database':'metadata'}])

    def test_unverified_mapping_does_not_satisfy_rows(self):
        req = ResearchAgent._requirements([{'id':'r1','kind':'rows',
             'rows':{'database':'market','table':'unresolved',
                     'filters':{'identifier':'D05'},'date_column':'date',
                     'value_column':'closing_price','boundary':'first','count':5}}])
        agent = ResearchAgent(self.cfg, model=ScriptedModel(self.base))
        self.assertFalse(agent._coverage(req, [])['r1']['satisfied'])
        evidence=[{'id':'e1','tool':'discover_schema','result':{'database':'market',
            'tables':[{'table':'daily_prices','columns':[{'name':'ticker'},
                {'name':'trade_date'},{'name':'close_price'}]}]}}]
        self.assertFalse(agent._coverage(req, evidence)['r1']['satisfied'])

    def test_3_comparison_requires_four_boundaries_three_calculations(self):
        req=[{'id':'r1','kind':'schema','database':'market','description':'schema'}]
        for i,(ticker,boundary) in enumerate([('D05','first'),('D05','last'),('O39','first'),('O39','last')],2):
            req.append({'id':f'r{i}','kind':'rows','database':'market','table':'unresolved','filters':{'ticker':ticker},'date_column':'trade_date','value_column':'close_price','boundary':boundary,'count':1,'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},'description':f'{ticker} {boundary}'})
        req += [{'id':'r6','kind':'calculation','operation':'percent_change','input_requirements':['r2','r3'],'description':'first return'},
                {'id':'r7','kind':'calculation','operation':'percent_change','input_requirements':['r4','r5'],'description':'second return'},
                {'id':'r8','kind':'calculation','operation':'difference_pp','input_requirements':['r6','r7'],'description':'difference in pp'}]
        result,_=self.run_plan(req,'Compare DBS and OCBC January 2024 price performance and calculate percentage returns and percentage-point difference')
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(len(result['evidence']),8)
        self.assertTrue(all(x['satisfied'] for x in result['requirement_coverage'].values()))
        self.assertEqual(result['evidence'][-1]['result']['operation'],'difference_pp')
    def test_filter_proof_rejects_wrong_parameter_position(self):
        f=ResearchAgent._sql_filters_proven
        self.assertFalse(f('SELECT * FROM daily_prices WHERE ticker=? AND trade_date=?',['O39','D05'],{'ticker':'D05'}))
        self.assertTrue(f('SELECT * FROM daily_prices WHERE ticker=? AND trade_date=?',['D05','2024-01-01'],{'ticker':'D05'}))
    def test_no_false_completion_without_calculations(self):
        agent=ResearchAgent(self.cfg,model=ScriptedModel(self.base))
        requirements=[{'id':'r1','kind':'calculation','operation':'percent_change','input_requirements':['r2'],'description':'return'}]
        self.assertFalse(agent._coverage(requirements,[])['r1']['satisfied'])
    def test_temporal_window_requires_sql_predicates(self):
        sql = "SELECT ticker, trade_date, close_price FROM daily_prices WHERE ticker=? ORDER BY trade_date ASC LIMIT 5"
        self.assertFalse(ResearchAgent._sql_temporal_window_proven(sql, ['D05'], 'trade_date',
                         {'start':'2024-01-01','end':'2024-01-31'}))
        good = "SELECT * FROM daily_prices WHERE ticker=? AND trade_date>=? AND trade_date<=? ORDER BY trade_date ASC LIMIT 5"
        self.assertTrue(ResearchAgent._sql_temporal_window_proven(good,
                        ['D05','2024-01-01','2024-01-31'],'trade_date',
                        {'start':'2024-01-01','end':'2024-01-31'}))
        self.assertFalse(ResearchAgent._sql_temporal_window_proven(good,
                         ['D05','2023-01-01','2024-01-31'],'trade_date',
                         {'start':'2024-01-01','end':'2024-01-31'}))
    def test_no_unrequested_obligation_is_silently_waived(self):
        req = [
            {'id':'r1','kind':'schema','database':'market','description':'schema','mandatory':True},
            {'id':'r2','kind':'source','tool':'inspect_document','description':'unrequested inspection','mandatory':True},
        ]
        retained = ResearchAgent._reconcile_requirements('What tables are available?', req)
        self.assertEqual(len(retained),2)
        self.assertEqual(retained[1]['id'],'r2')
    def test_cannot_complete_without_required_evidence_citation(self):
        agent=ResearchAgent(self.cfg)
        coverage={'r1':{'satisfied':True,'evidence_ids':['e1']}}
        evidence=[{'id':'e1','tool':'discover_schema','result':{'database':'market','tables':[]}}]
        decision={'answer':'Some tables exist.', 'evidence_ids':[]}
        self.assertIsNotNone(agent._validate_final(decision,evidence,None,coverage))
    def test_schema_only_observation_plan_is_repaired_before_tools(self):
        base = dict(self.base)
        base['jev'] = dict(self.base['jev'], evidence_goals=['First five dated closing prices'])
        schema = {'id':'r1','kind':'schema','database':'market','description':'Discover schema'}
        row = {'id':'r2','kind':'rows','database':'market','table':'unresolved',
               'filters':{'ticker':'D05'},'date_column':'trade_date',
               'value_column':'close_price','boundary':'first','count':5,
               'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},
               'description':'First five prices'}
        class RepairModel(ScriptedModel):
            def ask(self, system, payload):
                if payload.get('task')=='audit_plan_completeness':
                    has_rows=any(r['kind']=='rows' for r in payload['requirements'])
                    return {'coverage':[{'goal_index':0,'requirement_ids':['r2'] if has_rows else ['r1'],
                        'goal_type':'observations','covered':has_rows,'reason':'rows required'}]}
                if payload.get('task')=='repair_incomplete_plan':
                    return {'added_requirements':[row]}
                return super().ask(system,payload)
        model=RepairModel({**base,'requirements':[schema]})
        result=ResearchAgent(self.cfg,model=model).run('Retrieve five prices')
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(len(result['requirements']),2)
        self.assertEqual(result['requirements'][0]['id'],'r1')
        self.assertTrue(all(x['satisfied'] for x in result['requirement_coverage'].values()))
        self.assertEqual(len([e for e in result['evidence'] if e['tool']=='read_sql'][0]['result']['rows']),5)

    def test_schema_only_observation_plan_blocks_if_repair_incomplete(self):
        base=dict(self.base)
        base['jev']=dict(self.base['jev'],evidence_goals=['First five prices'])
        schema={'id':'r1','kind':'schema','database':'market','description':'schema'}
        class NoRepair(ScriptedModel):
            def ask(self,system,payload):
                if payload.get('task')=='audit_plan_completeness':
                    return {'coverage':[{'goal_index':0,'requirement_ids':['r1'],
                            'goal_type':'observations','covered':False,'reason':'missing rows'}]}
                if payload.get('task')=='repair_incomplete_plan':
                    return {'added_requirements':[]}
                return super().ask(system,payload)
        result=ResearchAgent(self.cfg,model=NoRepair({**base,'requirements':[schema]})).run('five prices')
        self.assertEqual(result['status'],'BLOCKED_INCOMPLETE_RESEARCH_PLAN')
        self.assertEqual(result['trace'],[])
        self.assertEqual(result['evidence'],[])

    def test_audit_rejects_schema_only_claim_without_schema_goal_type(self):
        agent=ResearchAgent(self.cfg)
        class Fake:
            def ask(self,system,payload):
                return {'coverage':[{'goal_index':0,'requirement_ids':['r1'],
                                     'covered':True,'goal_type':'observations'}]}
        agent.model=Fake()
        missing=agent._check_plan_completeness('five prices',
            {'evidence_goals':['five prices']},{'dependent_tasks':[]},
            [{'id':'r1','kind':'schema','database':'market'}])
        self.assertEqual(missing,[0])

    def test_unverified_binding_never_reaches_read_sql_decision(self):
        req = [{'id':'r1','kind':'schema','database':'market','description':'schema'},
               {'id':'r2','kind':'rows','database':'market','table':'unknown',
                'filters':{'instrument':'DBS','code':'D05'},
                'date_column':'date','value_column':'closing_price',
                'boundary':'first','count':5,
                'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},
                'description':'five closes'}]
        class BadBinder(ScriptedModel):
            def ask(self, system, payload):
                if payload.get('task') == 'resolve_row_bindings':
                    self.calls.append(payload)
                    return {'table':'daily_prices','filters':{'code':'D05'},
                            'date_column':'trade_date','value_column':'close_price',
                            'filter_sources':{'code':['code','instrument']}}
                if 'tool_catalog' in payload and 'missing_requirements' in payload:
                    self.calls.append(payload)
                    if (any(r['kind']=='rows' for r in payload['missing_requirements'])
                            and any(e['tool']=='discover_schema' for e in payload.get('evidence_log',[]))):
                        raise AssertionError('Tool planner invoked with unbound row')
                return super().ask(system,payload)
        model=BadBinder({**self.base,'requirements':req})
        result=ResearchAgent(self.cfg,model=model).run('Retrieve five closes')
        self.assertEqual(result['status'],'BLOCKED_ROW_BINDING_UNRESOLVED',result)
        self.assertFalse(any(e['tool']=='read_sql' for e in result['evidence']))
        self.assertEqual(sum(t.get('error')=='BINDING_PROPOSAL_REJECTED'
                             for t in result['trace']),2)
        self.assertFalse(result['requirement_coverage']['r2']['satisfied'])

    def test_verified_binding_precedes_sql_execution(self):
        req = [{'id':'r1','kind':'schema','database':'market','description':'schema'},
               {'id':'r2','kind':'rows','database':'market','table':'unresolved',
                'filters':{'instrument':'DBS','code':'D05'},
                'date_column':'date','value_column':'closing_price',
                'boundary':'first','count':5,
                'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'},
                'description':'five closes'}]
        result,_=self.run_plan(req,'Retrieve first five D05 closes')
        self.assertEqual(result['status'],'COMPLETED',result)
        sequence=[e['tool'] for e in result['evidence']]
        self.assertLess(sequence.index('discover_schema'),sequence.index('probe_column_values'))
        self.assertLess(sequence.index('probe_column_values'),sequence.index('read_sql'))
        self.assertTrue(result['requirement_coverage']['r2']['satisfied'])

    def test_binding_rejection_reason_is_specific(self):
        schema = [{'table':'daily_prices','columns':[{'name':n} for n in
                   ('ticker','trade_date','close_price')]}]
        req = {'filters':{'instrument':'DBS','code':'D05'},
               'boundary':'first','temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}}
        bad = {'table':'daily_prices','filters':{'code':'D05'},
               'date_column':'trade_date','value_column':'close_price',
               'filter_sources':{'code':['code','instrument']}}
        self.assertEqual(ResearchAgent._binding_rejection(bad,req,schema),
                         'UNKNOWN_FILTER_COLUMNS:code')
        bad['filters']={'ticker':'D05'}
        bad['filter_sources']={'ticker':['code','instrument']}
        self.assertIsNone(ResearchAgent._binding_rejection(bad,req,schema))

    def test_diagnostic_file_records_request_and_exact_planner_output(self):
        from agent_api.core import _diagnostic, _request_id, _fingerprint
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td)/'agent_diagnostics.jsonl')
            with unittest.mock.patch.dict(os.environ, {'HKELI_DIAGNOSTICS_FILE':path}):
                token = _request_id.set('test-request')
                try:
                    _diagnostic('planner_output', plan={'requirements':[{'id':'r1'}]})
                finally:
                    _request_id.reset(token)
            records=[json.loads(line) for line in Path(path).read_text().splitlines()]
            self.assertEqual(records[0]['request_id'],'test-request')
            self.assertEqual(records[0]['plan']['requirements'][0]['id'],'r1')
            self.assertEqual(_fingerprint({'a':1,'b':2}),_fingerprint({'b':2,'a':1}))

    def test_methods_are_class_members(self):
        self.assertTrue(callable(ResearchAgent._matching_rows))
        self.assertTrue(callable(ResearchAgent._sql_filters_proven))

if __name__=='__main__': unittest.main()
