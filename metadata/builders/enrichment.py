from __future__ import annotations
import collections, hashlib, json, os, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from metadata.database import connect

STOP=set('the and for with from this that have will would should were which their into about these those our your are has was its can also not but via than over under between during each all per one two three they them being more most such only very what when where while using report research analysis company group data financial market table figure source page document note investment performance'.split())
ALIASES={'USD':['US dollar','dollar','greenback'],'D05':['DBS','DBS Group'],'O39':['OCBC'],'U11':['UOB'],'SGD':['Singapore dollar'],'FX':['foreign exchange'],'NIM':['net interest margin'],'ROE':['return on equity'],'Fed':['Federal Reserve'],'BoJ':['Bank of Japan']}

def chunks(text, n=12000):
    return [text[i:i+n] for i in range(0,len(text),n)] or ['']

def extract(path):
    ext=path.suffix.lower(); sections=[]; objects=[]; author=None; date=None; pages=None; slides=None
    if ext=='.pdf':
        from pypdf import PdfReader
        pdf=PdfReader(str(path));pages=len(pdf.pages); meta=pdf.metadata
        if meta: author=meta.author;date=str(meta.creation_date) if meta.creation_date else None
        for i,page in enumerate(pdf.pages,1):
            text=page.extract_text() or ''
            sections.append((i,{'page':i},text))
            for j,_ in enumerate(page.images): objects.append(('image',{'page':i,'index':j+1},'Embedded PDF image'))
    elif ext=='.pptx':
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        prs=Presentation(str(path));slides=len(prs.slides);author=prs.core_properties.author or None
        for i,slide in enumerate(prs.slides,1):
            parts=[]
            for j,shape in enumerate(slide.shapes,1):
                if shape.has_text_frame: parts.append(shape.text)
                if shape.has_table:
                    parts.extend(' | '.join(cell.text for cell in row.cells) for row in shape.table.rows)
                    objects.append(('table',{'slide':i,'shape':j},shape.name))
                if shape.has_chart: objects.append(('chart',{'slide':i,'shape':j},shape.name))
                if shape.shape_type==MSO_SHAPE_TYPE.PICTURE: objects.append(('image',{'slide':i,'shape':j},shape.name))
            sections.append((i,{'slide':i},'\n'.join(parts)))
    elif ext=='.docx':
        from docx import Document
        doc=Document(str(path));author=doc.core_properties.author or None
        body=[]
        for para in doc.paragraphs:
            if para.text.strip(): body.append(para.text)
        for i,table in enumerate(doc.tables,1):
            rows=[' | '.join(cell.text for cell in row.cells) for row in table.rows]
            body.append('\n'.join(rows));objects.append(('table',{'table':i},'DOCX table'))
        for i,_ in enumerate(doc.inline_shapes,1): objects.append(('image',{'image':i},'DOCX inline image'))
        # DOCX pagination is layout-dependent; do not invent a page count.
        for i,text in enumerate(chunks('\n'.join(body)),1): sections.append((i,{'section':i},text))
    elif ext in ('.png','.jpeg','.jpg'):
        from PIL import Image
        with Image.open(path) as im:
            objects.append(('image',{'image':1},f'{im.width}x{im.height} {im.format}'))
            sections.append((1,{'image':1},f'Image {path.stem.replace("_"," ")}; {im.width} by {im.height} pixels'))
    elif ext=='.msg':
        try:
            import extract_msg
        except ImportError as exc: raise RuntimeError('MSG_REQUIRES_EXTRACT_MSG: pip install extract-msg') from exc
        msg=extract_msg.Message(str(path))
        author=msg.sender;date=msg.date
        content='\n'.join([f'Subject: {msg.subject or ""}',f'From: {msg.sender or ""}',f'To: {msg.to or ""}',f'Date: {msg.date or ""}',msg.body or ''])
        sections=[(i,{'message':1,'section':i},part) for i,part in enumerate(chunks(content),1)]
        for i,att in enumerate(msg.attachments,1): objects.append(('attachment',{'attachment':i},getattr(att,'longFilename',None) or getattr(att,'shortFilename',None) or 'attachment'))
    return sections,objects,author,date,pages,slides

def llm_json(prompt,model=None):
    if os.getenv('INVESTMENT_CHATBOT_ENABLE_LLM','0')!='1': return None
    payload=json.dumps({'model':model or os.getenv('INVESTMENT_CHATBOT_MODEL','qwen3:8b'),'stream':False,'format':'json','options':{'temperature':0},'messages':[{'role':'user','content':prompt}]}).encode()
    req=urllib.request.Request(os.getenv('INVESTMENT_CHATBOT_OLLAMA_URL','http://127.0.0.1:11434/api/chat'),data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=int(os.getenv('INVESTMENT_CHATBOT_LLM_TIMEOUT','180'))) as r:
        response=json.load(r)
    return json.loads(response['message']['content'])

def enrich(root, force=False):
    root=Path(root); now=datetime.now(timezone.utc).isoformat(); counts=collections.Counter()
    with connect() as c:
        rows=c.execute('SELECT * FROM files ORDER BY relative_path').fetchall()
        for row in rows:
            if row['ingestion_status']=='ENRICHED' and not force: counts['unchanged']+=1;continue
            path=root/row['relative_path'];fid=row['file_id']
            if not path.exists(): counts['missing']+=1;continue
            try:
                sections,objects,author,date,pages,slides=extract(path)
                full='\n'.join(t for _,_,t in sections)
                # Index full extracted text; never infer image content from filenames.
                freq=collections.Counter(re.findall(r'[A-Za-z][A-Za-z0-9_\-]{2,}',full.lower()))
                finance={'nim','roe','roa','cet1','npl','eps','valuation','earnings','dividend','yield','margin','capital','liquidity','credit','spread','duration','inflation','monetary-policy','volume','turnover','revenue','risk','fx','sgd','usd','d05','o39','u11','pe','pb'}
                boilerplate=STOP|{'synthetic','prototype','dataset','testing','generated','event','events','latest','following','additional','questions','figure','image','pixels','history','historical','source','table','json','agent','document','file','market.db'}
                selected_terms=[(term,n) for term,n in freq.items() if term not in boilerplate and (term in finance or len(term)>3)]
                selected_terms.sort(key=lambda x:(0 if x[0] in finance else 1,-x[1],x[0]))
                # Preserve all distinctive terms, including rare ones, without arbitrary top-N loss.
                entities=[]
                for key,aliases in ALIASES.items():
                    if any(re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',full,re.I) for x in [key]+aliases): entities.append(key)
                # Financial metrics and company identifiers should be discoverable at document level.
                entities=list(dict.fromkeys(entities+[t.upper() for t in ('nim','roe','roa','cet1','npl','eps','d05','o39','u11') if re.search(r'(?<!\w)'+t+r'(?!\w)',full,re.I)]))
                # Deterministic extractive summaries are labeled as such; do not claim synthesis.
                sentences=re.split(r'(?<=[.!?])\s+|\n+',full)
                candidates=[re.sub(r'\s+',' ',x).strip() for x in sentences if len(x.strip())>=35 and not any(b in x.lower() for b in ('synthetic dataset','prototype testing','artificially generated'))]
                scored=sorted(enumerate(candidates),key=lambda z:(-sum(3 for t in finance if re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',z[1],re.I)),-min(len(z[1]),300),z[0]))
                highlights=[]
                for _,candidate in scored:
                    candidate=candidate[:350]
                    if candidate not in highlights: highlights.append(candidate)
                    if len(highlights)>=5: break
                synopsis=('Extractive overview: '+' '.join(highlights[:3]))[:1800] if highlights else ('Extracted text: '+full[:800])
                if path.suffix.lower() in ('.png','.jpeg','.jpg'):
                    synopsis='Image inventory only: '+(sections[0][2] if sections else path.name)+'; visual interpretation not performed'
                    highlights=[]
                if os.getenv('INVESTMENT_CHATBOT_ENABLE_LLM','0')=='1' and full.strip() and path.suffix.lower() not in ('.png','.jpeg','.jpg'):
                    sample=full[:12000]+('\n[MIDDLE]\n'+full[len(full)//2:len(full)//2+5000] if len(full)>15000 else '')+('\n[END]\n'+full[-5000:] if len(full)>22000 else '')
                    try:
                        result=llm_json('Return JSON keys summary (string), highlights (list of strings), entities (list of strings). Write a concise finance-focused synthesis; include key metrics, catalysts and risks only when present. No speculation. Document: '+sample)
                        if isinstance(result,dict):
                            synopsis=str(result.get('summary') or synopsis)[:4000]
                            highlights=[str(x)[:400] for x in result.get('highlights',highlights) if isinstance(x,str)][:8]
                            entities=list(dict.fromkeys(entities+[str(x)[:80] for x in result.get('entities',[]) if isinstance(x,str)]))[:50]
                    except Exception as exc:
                        counts['llm_fallback']+=1
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                c.execute('DELETE FROM file_entities WHERE file_id=?',(fid,));c.execute('DELETE FROM file_terms WHERE file_id=?',(fid,));c.execute('DELETE FROM file_sections WHERE file_id=?',(fid,));c.execute('DELETE FROM file_objects WHERE file_id=?',(fid,))
                for entity in entities: c.execute('INSERT OR IGNORE INTO file_entities VALUES(?,?,?,?)',(fid,entity,'financial',1.0))
                for term,n in selected_terms:
                    band='low_frequency' if n<=2 else ('medium_frequency' if n<=10 else 'high_frequency')
                    c.execute('INSERT OR REPLACE INTO file_terms VALUES(?,?,?,?,?)',(fid,term,band,float(n)*(3 if term in finance else 1),n))
                for i,loc,t in sections:
                    sid=hashlib.sha256(f'{fid}:{i}'.encode()).hexdigest()[:24]
                    c.execute('INSERT INTO file_sections(section_id,file_id,section_order,locator_json,title,summary,entities_json) VALUES(?,?,?,?,?,?,?)',(sid,fid,i,json.dumps(loc),t.strip().split('\n')[0][:150],t[:1200],json.dumps([e for e in entities if re.search(r'(?<!\w)'+re.escape(e)+r'(?!\w)',t,re.I)])))
                for i,(typ,loc,title) in enumerate(objects,1):
                    oid=hashlib.sha256(f'{fid}:{typ}:{i}'.encode()).hexdigest()[:24]
                    c.execute('INSERT INTO file_objects(object_id,file_id,object_type,locator_json,title,description,entities_json) VALUES(?,?,?,?,?,?,?)',(oid,fid,typ,json.dumps(loc),title,title,'[]'))
                c.execute('UPDATE files SET document_date=?,author=?,page_count=?,slide_count=?,summary=?,key_highlights_json=?,content_hash=?,ingestion_status=?,metadata_generated_at=? WHERE file_id=?',(str(date) if date else None,author,pages,slides,synopsis,json.dumps(highlights),digest,'ENRICHED',now,fid))
                counts['enriched']+=1
            except Exception as exc:
                c.execute('UPDATE files SET ingestion_status=? WHERE file_id=?',('ERROR:'+str(exc)[:180],fid));counts['errors']+=1
    return dict(counts)
