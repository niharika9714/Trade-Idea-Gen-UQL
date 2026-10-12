import sqlite3, tempfile, unittest
from pathlib import Path
from contextlib import closing
from scripts.create_demo_dataset import create
from agent_api.core import Config, ResearchAgent
from agent_api.metadata_retrieval import MetadataRetrieval

class Stub:
    def __init__(self):self.calls=[]
    def ask(self,system,payload):
        self.calls.append(payload)
        task=payload.get('task')
        if task=='audit_plan_completeness':
            return {'coverage':[{'goal_index':0,'requirement_ids':['r2'],'covered':True}],'missing_goals':[]}
        if task=='resolve_row_bindings':
            return {'table':'daily_prices','filters':{'ticker':'D05'},'date_column':'trade_date',
                    'value_column':'close_price','filter_sources':{'ticker':['instrument']}}
        if 'query' in payload and 'tools' in payload:
            return {'jev':{'evidence_goals':['First five D05 January 2024 prices']},
                    'uql_plan':{'dependent_tasks':['discover','retrieve']},
                    'requirements':[{'id':'r1','kind':'schema','database':'market'},
                    {'id':'r2','kind':'rows','database':'market','table':'unresolved',
                     'filters':{'instrument':'D05'},'value_column':'close_price',
                     'date_column':'trade_date','count':5,'boundary':'first',
                     'temporal_scope':{'start':'2024-01-01','end':'2024-01-31'}}]}
        if 'evidence_log' in payload:
            ids=[e['id'] for e in payload['evidence_log']]
            return {'action':'final','answer':'Five source-verified observations '+' '.join('['+i+']' for i in ids),
                    'evidence_ids':ids,'limitations':['Synthetic fixture']}
        raise AssertionError(('Unexpected model prompt',task,payload.keys()))

class Integration(unittest.TestCase):
    def test_sql_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'market.db'
            with closing(sqlite3.connect(p)) as c:
                c.execute('CREATE TABLE daily_prices(ticker TEXT,trade_date TEXT,close_price REAL)')
                c.executemany('INSERT INTO daily_prices VALUES (?,?,?)',
                    [('D05',f'2024-01-{i:02}',float(i)) for i in range(1,8)])
                c.commit()
            create(Path(d)/'catalog')
            metadata=str(Path(d)/'catalog'/'metadata.db')
            out=ResearchAgent(Config(market_db=str(p),metadata_db=metadata,max_rounds=6),model=Stub()).run('First five D05 January 2024 closing prices')
            self.assertEqual(out['status'],'COMPLETED',out.get('limitations'))
            sql=[e for e in out['evidence'] if e['tool']=='read_sql']
            self.assertEqual(len(sql),1)
            self.assertEqual([r['close_price'] for r in sql[0]['result']['rows']],[1.,2.,3.,4.,5.])
            self.assertEqual(out['requirements'][1]['filters'],{'instrument':'D05'})
    def test_metadata_semantic_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            create(Path(d))
            metadata=Path(d)/'metadata.db'
            with closing(sqlite3.connect(metadata)) as c:
                c.execute("INSERT INTO files(file_id,source_id,relative_path,file_name,file_type,summary) VALUES ('doc1','market_sql','D05.txt','D05.txt','txt','D05 research')")
                c.commit()
            cat=MetadataRetrieval(metadata)
            self.assertTrue(cat.search_sql('closing price')['tables'])
            self.assertTrue(cat.search_documents('D05')['files'])

if __name__=='__main__':unittest.main()
