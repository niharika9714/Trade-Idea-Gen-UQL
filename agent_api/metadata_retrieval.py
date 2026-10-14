"""Read-only metadata-first semantic discovery for SQL and registered documents."""
import json, math, re, sqlite3
from contextlib import closing
from pathlib import Path

class MetadataRetrieval:
    def __init__(self, path):
        self.path = Path(path).resolve()
    def _connect(self):
        if not self.path.is_file(): raise FileNotFoundError(self.path)
        c = sqlite3.connect(f'file:{self.path.as_posix()}?mode=ro', uri=True, timeout=3)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        return c
    def search_sql(self, query, limit=12):
        words = list(dict.fromkeys(w.lower() for w in re.findall(r'[\w]+', query) if len(w)>1))[:24]
        with closing(self._connect()) as c:
            tables=[dict(r) for r in c.execute('SELECT * FROM sql_tables LIMIT 100')]
            columns=[dict(r) for r in c.execute('SELECT * FROM sql_columns LIMIT 500')]
            samples=[dict(r) for r in c.execute('SELECT * FROM sql_value_samples LIMIT 500')]
            relationships=[dict(r) for r in c.execute('SELECT * FROM sql_relationships LIMIT 200')]
        by_table={}
        for t in tables:
            key=(t['source_id'],t['table_name'])
            by_table[key]={**t,'columns':[],'relationships':[],'score':0}
        for col in columns:
            key=(col['source_id'],col['table_name'])
            if key not in by_table: continue
            aliases=json.loads(col.get('aliases_json') or '[]')
            desc=' '.join(str(x or '') for x in [col['column_name'],col.get('business_description'),*aliases]).lower()
            col['aliases']=aliases
            col['score']=sum(3 if w in aliases else (2 if w in desc else 0) for w in words)
            by_table[key]['columns'].append(col)
            by_table[key]['score']+=col['score']
        for t in by_table.values():
            desc=(t['table_name']+' '+str(t.get('business_description') or '')).lower()
            t['score']+=sum(3 for w in words if w in desc)
            t['columns'].sort(key=lambda x:-x['score'])
        for s in samples:
            key=(s['source_id'],s['table_name'])
            if key in by_table:
                for col in by_table[key]['columns']:
                    if col['column_name']==s['column_name']:
                        col['sample_values']=json.loads(s.get('sample_values_json') or '[]')[:20]
                        break
        for rel in relationships:
            for key,t in by_table.items():
                if key[0]==rel['source_id'] and key[1] in (rel['from_table'],rel['to_table']):
                    t['relationships'].append(rel)
        ranked=sorted(by_table.values(),key=lambda t:(-t['score'],t['table_name']))
        return {'query':query,'tables':ranked[:max(1,min(limit,30))], 'metadata_only':True,
                'warning':'Catalog hints require live schema and source-value verification'}
    def search_documents(self,query,limit=12):
        words=list(dict.fromkeys(w.lower() for w in re.findall(r'[\w]+',query) if len(w)>1))[:24]
        with closing(self._connect()) as c:
            # Tuned fork (fix 1): every spelling of each market, product or tenor the query names, from the catalog's
            # terminology table, so "one-year USD/SGD double-no-touch" also searches "12m", "usdsgd", "dnt".
            try:
                vocab=[{'term':r['term'],'canonical':r['canonical_term']} for r in c.execute('SELECT term,canonical_term FROM terminology')]
            except sqlite3.Error:
                vocab=[]
            if vocab:
                from metadata import terminology
                words=list(dict.fromkeys(words+terminology.expand(query,terminology.groups(vocab))))[:64]
            files=[dict(r) for r in c.execute('SELECT file_id,source_id,relative_path,file_name,file_type,summary,document_date,ingestion_status FROM files LIMIT 2000')]
            scores={f['file_id']:0. for f in files}
            for f in files:
                text=(str(f['file_name'])+' '+str(f['summary'] or '')).lower()
                scores[f['file_id']]+=sum(1.5 for w in words if w in text)
            if words:
                marks=','.join('?' for _ in words)
                # Tuned fork (fix 5): BM25 on the body terms. The unedited score added each matched term's frequency
                # (x3 for finance words) with no regard to length, so one long deck that mentions every product was
                # listed first for 6 of 15 mail questions. Now a match counts by how rare the word is across the
                # catalog, saturates with repetition, and is tempered by the document's length against the average.
                n_docs=max(1,len(files))
                dl={r[0]:float(r[1] or 0) for r in c.execute('SELECT file_id,SUM(coalesce(frequency,1)) FROM file_terms GROUP BY file_id')}
                avgdl=(sum(dl.values())/len(dl)) if dl else 1.0
                df={r[0]:r[1] for r in c.execute(f'SELECT lower(term),COUNT(DISTINCT file_id) FROM file_terms WHERE lower(term) IN ({marks}) GROUP BY lower(term)',words)}
                k1,b=1.2,0.75
                for r in c.execute(f'SELECT file_id,lower(term) t,frequency FROM file_terms WHERE lower(term) IN ({marks})',words):
                    if r['file_id'] not in scores: continue
                    tf=float(r['frequency'] or 1); L=dl.get(r['file_id'],avgdl)
                    idf=math.log(1+(n_docs-df.get(r['t'],0)+0.5)/(df.get(r['t'],0)+0.5))
                    scores[r['file_id']]+=idf*tf*(k1+1)/(tf+k1*(1-b+b*L/avgdl))
                # entity tags count by rarity too: a tag most documents carry (USD, FX) says little
                edf={r[0]:r[1] for r in c.execute(f'SELECT lower(entity),COUNT(DISTINCT file_id) FROM file_entities WHERE lower(entity) IN ({marks}) GROUP BY lower(entity)',words)}
                for r in c.execute(f'SELECT DISTINCT file_id,lower(entity) e FROM file_entities WHERE lower(entity) IN ({marks})',words):
                    if r['file_id'] in scores:
                        scores[r['file_id']]+=2.0*math.log(1+(n_docs-edf.get(r['e'],0)+0.5)/(edf.get(r['e'],0)+0.5))
            # Tuned fork (fix 6): a mail and its attachments share their best score, and each result lists the others.
            links={}
            try:
                for r in c.execute("SELECT source_concept,target_concept FROM concept_relationships WHERE relationship_type='has_attachment'"):
                    a,t=str(r[0])[5:],str(r[1])[5:]
                    links.setdefault(a,set()).add(t); links.setdefault(t,set()).add(a)
            except sqlite3.Error:
                pass
            base=dict(scores)
            for fid,others in links.items():
                if fid in scores:
                    scores[fid]=max(base[fid],0.9*max((base.get(o,0.) for o in others),default=0.))
            names={f['file_id']:f['file_name'] for f in files}
            ranked=sorted((f for f in files if scores[f['file_id']]>0),key=lambda f:-scores[f['file_id']])[:max(1,min(limit,30))]
            for f in ranked:
                f['score']=round(scores[f['file_id']],3)
                if f['file_id'] in links:
                    f['linked_files']=[{'file_id':o,'file_name':names.get(o)} for o in sorted(links[f['file_id']])]
                f['sections']=[dict(r) for r in c.execute('SELECT section_id,section_order,locator_json,title,summary FROM file_sections WHERE file_id=? ORDER BY section_order LIMIT 30',(f['file_id'],))]
                f['objects']=[dict(r) for r in c.execute('SELECT object_id,object_type,locator_json,title,description FROM file_objects WHERE file_id=? LIMIT 30',(f['file_id'],))]
        return {'query':query,'files':ranked,'metadata_only':True}
    def document_units(self,file_id,limit=100):
        with closing(self._connect()) as c:
            f=c.execute('SELECT file_id,relative_path,file_name,file_type,document_date,summary FROM files WHERE file_id=?',(file_id,)).fetchone()
            if f is None: raise ValueError('UNKNOWN_FILE_ID')
            sections=[dict(r) for r in c.execute('SELECT * FROM file_sections WHERE file_id=? ORDER BY section_order LIMIT ?',(file_id,min(200,max(1,limit))))]
            objects=[dict(r) for r in c.execute('SELECT * FROM file_objects WHERE file_id=? LIMIT ?',(file_id,min(200,max(1,limit))))]
        return {'file':dict(f),'sections':sections,'objects':objects,'citation':'metadata:file:'+file_id,'metadata_only':True}
