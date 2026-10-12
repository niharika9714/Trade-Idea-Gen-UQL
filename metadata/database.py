from __future__ import annotations
from contextlib import closing
import sqlite3
from pathlib import Path
from app.config import METADATA_DB_PATH

SCHEMA = r'''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources (
 source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', authority TEXT NOT NULL,
 freshness_class TEXT NOT NULL, expected_latency_ms INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
 capabilities_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}',
 last_catalogued_at TEXT
);
CREATE TABLE IF NOT EXISTS sql_tables (
 source_id TEXT NOT NULL, table_name TEXT NOT NULL, table_type TEXT NOT NULL DEFAULT 'table',
 business_description TEXT, row_count INTEGER, date_columns_json TEXT NOT NULL DEFAULT '[]',
 last_profiled_at TEXT, PRIMARY KEY(source_id,table_name),
 FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS sql_columns (
 source_id TEXT NOT NULL, table_name TEXT NOT NULL, column_name TEXT NOT NULL,
 ordinal_position INTEGER, data_type TEXT, not_null INTEGER NOT NULL DEFAULT 0,
 default_value TEXT, is_primary_key INTEGER NOT NULL DEFAULT 0, business_description TEXT,
 aliases_json TEXT NOT NULL DEFAULT '[]', min_value TEXT, max_value TEXT,
 PRIMARY KEY(source_id,table_name,column_name),
 FOREIGN KEY(source_id,table_name) REFERENCES sql_tables(source_id,table_name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS sql_relationships (
 relationship_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
 from_table TEXT NOT NULL, from_column TEXT NOT NULL, to_table TEXT NOT NULL, to_column TEXT NOT NULL,
 relationship_type TEXT NOT NULL DEFAULT 'FOREIGN_KEY', UNIQUE(source_id,from_table,from_column,to_table,to_column)
);
CREATE TABLE IF NOT EXISTS sql_indexes (
 source_id TEXT NOT NULL, table_name TEXT NOT NULL, index_name TEXT NOT NULL,
 is_unique INTEGER NOT NULL DEFAULT 0, columns_json TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(source_id,table_name,index_name)
);
CREATE TABLE IF NOT EXISTS sql_value_samples (
 source_id TEXT NOT NULL, table_name TEXT NOT NULL, column_name TEXT NOT NULL,
 sample_values_json TEXT NOT NULL DEFAULT '[]', sampled_at TEXT,
 PRIMARY KEY(source_id,table_name,column_name)
);
CREATE TABLE IF NOT EXISTS files (
 file_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 file_name TEXT NOT NULL, file_type TEXT NOT NULL, category TEXT,
 size_bytes INTEGER, created_at TEXT, modified_at TEXT, document_date TEXT, author TEXT,
 page_count INTEGER, slide_count INTEGER, summary TEXT, key_highlights_json TEXT NOT NULL DEFAULT '[]',
 content_hash TEXT, ingestion_status TEXT NOT NULL DEFAULT 'DISCOVERED', metadata_generated_at TEXT,
 UNIQUE(source_id,relative_path)
);
CREATE TABLE IF NOT EXISTS file_entities (
 file_id TEXT NOT NULL, entity TEXT NOT NULL, entity_type TEXT, weight REAL NOT NULL DEFAULT 1.0,
 PRIMARY KEY(file_id,entity,entity_type)
);
CREATE TABLE IF NOT EXISTS file_terms (
 file_id TEXT NOT NULL, term TEXT NOT NULL, term_type TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0,
 frequency INTEGER, PRIMARY KEY(file_id,term,term_type)
);
CREATE TABLE IF NOT EXISTS file_sections (
 section_id TEXT PRIMARY KEY, file_id TEXT NOT NULL, section_order INTEGER,
 locator_json TEXT NOT NULL DEFAULT '{}', title TEXT, summary TEXT, entities_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS file_objects (
 object_id TEXT PRIMARY KEY, file_id TEXT NOT NULL, object_type TEXT NOT NULL,
 locator_json TEXT NOT NULL DEFAULT '{}', title TEXT, description TEXT, entities_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS api_endpoints (
 endpoint_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, name TEXT NOT NULL, business_purpose TEXT,
 method TEXT, endpoint_path TEXT, request_schema_json TEXT NOT NULL DEFAULT '{}',
 response_schema_json TEXT NOT NULL DEFAULT '{}', freshness_class TEXT, expected_latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS api_fields (
 endpoint_id TEXT NOT NULL, direction TEXT NOT NULL, field_name TEXT NOT NULL,
 data_type TEXT, description TEXT, required INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(endpoint_id,direction,field_name)
);
CREATE TABLE IF NOT EXISTS terminology (
 term_id TEXT PRIMARY KEY, term TEXT NOT NULL, canonical_term TEXT NOT NULL,
 term_scope TEXT NOT NULL, context TEXT, description TEXT, UNIQUE(term,canonical_term,term_scope,context)
);
CREATE TABLE IF NOT EXISTS concept_relationships (
 relationship_id INTEGER PRIMARY KEY AUTOINCREMENT, source_concept TEXT NOT NULL,
 target_concept TEXT NOT NULL, relationship_type TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0,
 source TEXT NOT NULL DEFAULT 'metadata', UNIQUE(source_concept,target_concept,relationship_type,source)
);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_type_category ON files(file_type,category);
CREATE INDEX IF NOT EXISTS idx_file_entities_entity ON file_entities(entity);
CREATE INDEX IF NOT EXISTS idx_file_terms_term ON file_terms(term);
CREATE INDEX IF NOT EXISTS idx_sql_columns_name ON sql_columns(column_name);
'''

def connect(path: Path | None = None) -> sqlite3.Connection:
    db = Path(path or METADATA_DB_PATH); db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); return con

def initialize(path: Path | None = None) -> Path:
    db = Path(path or METADATA_DB_PATH)
    with closing(connect(db)) as con: con.executescript(SCHEMA)
    return db
