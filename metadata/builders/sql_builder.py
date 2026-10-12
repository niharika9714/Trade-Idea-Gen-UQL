from __future__ import annotations
import json, sqlite3, re
from datetime import datetime, timezone
from pathlib import Path
from core.enums import Authority, FreshnessClass, SourceType
from core.models import SourceDescriptor
from metadata.catalog import MetadataCatalog
from metadata.database import connect

TABLE_MEANINGS={'companies':'Company master data including sector and reporting currency','instruments':'Tradable instrument identifiers, tickers, exchange and currency','daily_prices':'Daily OHLC security prices and daily returns','daily_volume':'Daily trading volume and turnover','fundamentals':'Reported company financial metrics, profitability and valuation','dividends':'Dividend payments and ex-dividend dates','sector_prices':'Sector-level price and return history'}
COLUMN_MEANINGS={'ticker':('Trading symbol identifying a security',['symbol','stock code','instrument ticker']),'trade_date':('Trading session date',['market date','pricing date']),'currency':('ISO or source-defined currency code',['ccy','denomination']),'close_price':('Closing market price',['close','last price','closing price']),'adjusted_close':('Closing price adjusted for corporate actions',['adjusted price','adj close']),'daily_return':('Daily price return, using the units stored in source',['daily performance','return']),'net_interest_margin':('Net interest margin',['NIM']),'roe':('Return on equity',['ROE']),'roa':('Return on assets',['ROA']),'cet1_ratio':('Common Equity Tier 1 capital ratio',['CET1','capital adequacy']),'npl_ratio':('Non-performing loan ratio',['NPL','bad loan ratio']),'pe_ratio':('Price to earnings ratio',['P/E','PE']),'pb_ratio':('Price to book ratio',['P/B','PB']),'eps':('Earnings per share',['EPS']),'ex_date':('Dividend ex-date',['ex-dividend date']),'dividend_per_share':('Cash dividend per share',['DPS']),'volume':('Number of units traded',['trading volume'])}
def explain_column(table, name, datatype):
    if name in COLUMN_MEANINGS: return COLUMN_MEANINGS[name]
    label=name.replace('_',' ')
    aliases=[label] if label != name else []
    if name.endswith('_id'): return (f'Identifier for {label[:-3].strip()} records',aliases)
    if name.endswith('_date'): return (f'Date of {label[:-5].strip()} event',aliases)
    return (f'{label.capitalize()} field in {table}; business definition requires validation',aliases)

SAMPLE_HINTS=('ticker','symbol','currency','type','category','exchange','instrument','name','sector','country')
DATE_HINTS=('date','time','timestamp')
def qid(x:str)->str: return '"'+x.replace('"','""')+'"'

class SQLMetadataBuilder:
    def __init__(self, source_id='market_sql', db_path:Path|str=None): self.source_id=source_id; self.db_path=Path(db_path) if db_path else None
    def build(self, db_path:Path|str=None):
        path=Path(db_path or self.db_path)
        MetadataCatalog().register_source(SourceDescriptor(source_id=self.source_id,source_type=SourceType.SQL,name='Market Database',description='Structured market and fundamental data',authority=Authority.INTERNAL_STRUCTURED,freshness_class=FreshnessClass.DAILY,expected_latency_ms=20,capabilities=['structured_query','schema_discovery','market_data'],metadata={'database_path':str(path)}))
        src=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True); src.row_factory=sqlite3.Row
        now=datetime.now(timezone.utc).isoformat()
        tables=[r['name'] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        with connect() as dst:
            for table in tables:
                cols=src.execute(f'PRAGMA table_info({qid(table)})').fetchall()
                row_count=src.execute(f'SELECT COUNT(*) n FROM {qid(table)}').fetchone()['n']
                date_cols=[r['name'] for r in cols if any(h in r['name'].lower() for h in DATE_HINTS)]
                dst.execute('''INSERT INTO sql_tables(source_id,table_name,business_description,row_count,date_columns_json,last_profiled_at) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,table_name) DO UPDATE SET business_description=COALESCE(NULLIF(sql_tables.business_description,''),excluded.business_description),row_count=excluded.row_count,date_columns_json=excluded.date_columns_json,last_profiled_at=excluded.last_profiled_at''',(self.source_id,table,TABLE_MEANINGS.get(table,f'Structured {table.replace(chr(95),chr(32))} records; business definition requires validation'),row_count,json.dumps(date_cols),now))
                for r in cols:
                    mn=mx=None
                    if r['name'] in date_cols:
                        try: mn,mx=src.execute(f'SELECT MIN({qid(r["name"])}),MAX({qid(r["name"])}) FROM {qid(table)}').fetchone()
                        except sqlite3.Error: pass
                    description, aliases=explain_column(table,r['name'],r['type'])
                    dst.execute('''INSERT INTO sql_columns(source_id,table_name,column_name,ordinal_position,data_type,not_null,default_value,is_primary_key,business_description,aliases_json,min_value,max_value) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,table_name,column_name) DO UPDATE SET data_type=excluded.data_type,not_null=excluded.not_null,default_value=excluded.default_value,is_primary_key=excluded.is_primary_key,business_description=COALESCE(NULLIF(sql_columns.business_description,''),excluded.business_description),aliases_json=CASE WHEN sql_columns.aliases_json IS NULL OR sql_columns.aliases_json='[]' THEN excluded.aliases_json ELSE sql_columns.aliases_json END,min_value=excluded.min_value,max_value=excluded.max_value''',(self.source_id,table,r['name'],r['cid'],r['type'],r['notnull'],r['dflt_value'],r['pk'],description,json.dumps(aliases),mn,mx))
                    if any(h in r['name'].lower() for h in SAMPLE_HINTS):
                        try:
                            vals=[x[0] for x in src.execute(f'SELECT DISTINCT {qid(r["name"])} FROM {qid(table)} WHERE {qid(r["name"])} IS NOT NULL LIMIT 20')]
                            dst.execute('''INSERT INTO sql_value_samples(source_id,table_name,column_name,sample_values_json,sampled_at) VALUES(?,?,?,?,?) ON CONFLICT(source_id,table_name,column_name) DO UPDATE SET sample_values_json=excluded.sample_values_json,sampled_at=excluded.sampled_at''',(self.source_id,table,r['name'],json.dumps(vals,default=str),now))
                        except sqlite3.Error: pass
                for fk in src.execute(f'PRAGMA foreign_key_list({qid(table)})'):
                    dst.execute('''INSERT OR IGNORE INTO sql_relationships(source_id,from_table,from_column,to_table,to_column) VALUES(?,?,?,?,?)''',(self.source_id,table,fk['from'],fk['table'],fk['to']))
                for idx in src.execute(f'PRAGMA index_list({qid(table)})'):
                    cols_i=[x['name'] for x in src.execute(f'PRAGMA index_info({qid(idx["name"])})')]
                    dst.execute('''INSERT INTO sql_indexes(source_id,table_name,index_name,is_unique,columns_json) VALUES(?,?,?,?,?) ON CONFLICT(source_id,table_name,index_name) DO UPDATE SET is_unique=excluded.is_unique,columns_json=excluded.columns_json''',(self.source_id,table,idx['name'],idx['unique'],json.dumps(cols_i)))
        src.close(); return {'source_id':self.source_id,'tables':len(tables),'database':str(path)}
