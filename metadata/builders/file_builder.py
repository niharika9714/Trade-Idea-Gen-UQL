from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from core.enums import Authority, FreshnessClass, SourceType
from core.models import SourceDescriptor
from metadata.catalog import MetadataCatalog
from metadata.database import connect

SUPPORTED={'.pdf':'pdf','.pptx':'pptx','.docx':'docx','.png':'png','.jpg':'jpeg','.jpeg':'jpeg','.msg':'msg'}
def iso(ts):
    try:return datetime.fromtimestamp(ts,timezone.utc).isoformat()
    except:return None
class FileMetadataBuilder:
    def __init__(self, source_id='research_documents'): self.source_id=source_id
    def build(self, root:Path|str):
        root=Path(root); MetadataCatalog().register_source(SourceDescriptor(source_id=self.source_id,source_type=SourceType.FILE,name='Research Documents',description='Internal PDF/PPTX/DOCX/images/MSG research documents',authority=Authority.INTERNAL_RESEARCH,freshness_class=FreshnessClass.EVENT_DRIVEN,expected_latency_ms=100,capabilities=['metadata_discovery','document_retrieval','page_section_retrieval'],metadata={'root':str(root)}))
        n=0; now=datetime.now(timezone.utc).isoformat()
        with connect() as c:
            for p in root.rglob('*') if root.exists() else []:
                if not p.is_file() or p.suffix.lower() not in SUPPORTED: continue
                st=p.stat(); rel=p.relative_to(root).as_posix(); parts=list(p.relative_to(root).parts[:-1]); ft=SUPPORTED[p.suffix.lower()]
                category='/'.join(parts[1:] if parts and parts[0].lower()==ft else parts) or 'uncategorized'
                fid=hashlib.sha256(f'{self.source_id}:{rel}'.encode()).hexdigest()[:24]
                c.execute('''INSERT INTO files(file_id,source_id,relative_path,file_name,file_type,category,size_bytes,created_at,modified_at,ingestion_status,metadata_generated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,relative_path) DO UPDATE SET file_name=excluded.file_name,file_type=excluded.file_type,category=excluded.category,size_bytes=excluded.size_bytes,created_at=excluded.created_at,modified_at=excluded.modified_at,ingestion_status=CASE WHEN files.modified_at != excluded.modified_at OR files.size_bytes != excluded.size_bytes THEN 'DISCOVERED' ELSE files.ingestion_status END''',(fid,self.source_id,rel,p.name,ft,category,st.st_size,iso(st.st_ctime),iso(st.st_mtime),'DISCOVERED',now)); n+=1
        return {'source_id':self.source_id,'files':n,'root':str(root)}
