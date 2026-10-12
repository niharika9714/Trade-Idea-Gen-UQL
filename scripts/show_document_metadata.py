"""Inspect enriched metadata, including related tables, for a file or all files."""
import argparse, json
from metadata.database import connect, initialize

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--file',default='',help='Substring of filename/path or exact file_id')
    p.add_argument('--limit',type=int,default=10)
    p.add_argument('--terms',type=int,default=30)
    p.add_argument('--band',choices=['all','low_frequency','medium_frequency','high_frequency'],default='all')
    args=p.parse_args()
    initialize()
    with connect() as c:
        c.row_factory=__import__('sqlite3').Row
        rows=c.execute('SELECT * FROM files WHERE (?="" OR file_name LIKE ? OR relative_path LIKE ? OR file_id=?) ORDER BY modified_at DESC LIMIT ?', (args.file,'%'+args.file+'%','%'+args.file+'%',args.file,args.limit)).fetchall()
        output=[]
        for row in rows:
            d=dict(row)
            try:d['key_highlights']=json.loads(d.pop('key_highlights_json') or '[]')
            except ValueError:d['key_highlights']=[]
            fid=d['file_id']
            for key,sql in {
                'entities':'SELECT entity,entity_type,weight FROM file_entities WHERE file_id=?',
                'terms':'SELECT term,term_type,frequency,weight FROM file_terms WHERE file_id=? AND (?="all" OR term_type=?) ORDER BY weight DESC,frequency ASC,term LIMIT ?',
                'sections':'SELECT section_order,locator_json,title,summary,entities_json FROM file_sections WHERE file_id=? ORDER BY section_order',
                'objects':'SELECT object_type,locator_json,title,description FROM file_objects WHERE file_id=?'
            }.items():
                params=(fid,args.band,args.band,args.terms) if key=='terms' else (fid,)
                d[key]=[dict(r) for r in c.execute(sql,params)]
            output.append(d)
    print(json.dumps({'count':len(output),'documents':output},indent=2,default=str))
if __name__=='__main__':main()
