"""Create entirely synthetic demo market and metadata databases for a smoke test."""
from pathlib import Path
import sqlite3, argparse
from contextlib import closing
from metadata.database import initialize

def create(root: Path):
    root=Path(root); market=root/'market_data'/'market.db'; meta=root/'metadata.db';market.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(market)) as c:
        c.execute('CREATE TABLE IF NOT EXISTS daily_prices (ticker TEXT, trade_date TEXT, close REAL, published_at TEXT)')
        c.execute('DELETE FROM daily_prices')
        c.executemany('INSERT INTO daily_prices VALUES (?,?,?,?)',[
          ('D05','2024-01-02',30.0,'2024-01-02T17:00:00+08:00'),
          ('D05','2024-01-31',32.0,'2024-01-31T17:00:00+08:00'),
          ('O39','2024-01-02',12.0,'2024-01-02T17:00:00+08:00'),
          ('O39','2024-01-31',11.5,'2024-01-31T17:00:00+08:00')])
        c.commit()
    initialize(meta)
    with closing(sqlite3.connect(meta)) as c:
        c.execute("INSERT OR REPLACE INTO sources(source_id,source_type,name,description,authority,freshness_class,enabled) VALUES ('market_sql','SQL','Synthetic market','Synthetic Singapore bank prices','INTERNAL','DAILY',1)")
        c.execute("INSERT OR REPLACE INTO sql_tables(source_id,table_name,business_description) VALUES ('market_sql','daily_prices','Historical bank prices with publication timestamps')")
        for idx,(col,typ) in enumerate([('ticker','TEXT'),('trade_date','TEXT'),('close','REAL'),('published_at','TEXT')]):
            c.execute('INSERT OR REPLACE INTO sql_columns(source_id,table_name,column_name,ordinal_position,data_type) VALUES (?,?,?,?,?)',('market_sql','daily_prices',col,idx,typ))
        for term,canonical in [('DBS','D05'),('OCBC','O39'),('D05','D05'),('O39','O39')]:
            c.execute('INSERT OR REPLACE INTO terminology(term_id,term,canonical_term,term_scope) VALUES (?,?,?,?)',(term,term,canonical,'instrument'))
        c.commit()
    print('Demo market:',market,'\nDemo metadata:',meta)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',default='demo_data');args=p.parse_args();create(Path(args.data_dir))
