from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from core.models import SourceDescriptor
from .database import connect, initialize

class MetadataCatalog:
    def __init__(self): initialize()
    def register_source(self, source: SourceDescriptor) -> None:
        with connect() as c:
            c.execute('''INSERT INTO sources(source_id,source_type,name,description,authority,freshness_class,expected_latency_ms,enabled,capabilities_json,metadata_json,last_catalogued_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET source_type=excluded.source_type,name=excluded.name,description=excluded.description,authority=excluded.authority,freshness_class=excluded.freshness_class,expected_latency_ms=excluded.expected_latency_ms,enabled=excluded.enabled,capabilities_json=excluded.capabilities_json,metadata_json=excluded.metadata_json,last_catalogued_at=excluded.last_catalogued_at''',
            (source.source_id,source.source_type.value,source.name,source.description,source.authority.value,source.freshness_class.value,source.expected_latency_ms,int(source.enabled),json.dumps(source.capabilities),json.dumps(source.metadata),datetime.now(timezone.utc).isoformat()))
    def snapshot(self) -> dict[str,Any]:
        with connect() as c:
            sources=[dict(r) for r in c.execute('SELECT * FROM sources ORDER BY source_id')]
            tables=[dict(r) for r in c.execute('SELECT * FROM sql_tables ORDER BY source_id,table_name')]
            columns=[dict(r) for r in c.execute('SELECT * FROM sql_columns ORDER BY source_id,table_name,ordinal_position')]
            rel=[dict(r) for r in c.execute('SELECT * FROM sql_relationships ORDER BY source_id,from_table')]
            files=[dict(r) for r in c.execute('SELECT file_id,source_id,relative_path,file_name,file_type,category,size_bytes,created_at,modified_at,document_date,author,page_count,slide_count,ingestion_status FROM files ORDER BY modified_at DESC')]
        return {'sources':sources,'sql':{'tables':tables,'columns':columns,'relationships':rel},'documents':{'total_files':len(files),'files':files}}
