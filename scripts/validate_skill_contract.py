"""Step 13D preflight CLI; fail closed without a trusted entitlement adapter."""
import argparse,json
from pathlib import Path
from skills.binding import load_metadata_snapshot
from skills.contracts import validate_source_contract

def main():
    p=argparse.ArgumentParser(description='Read-only skill source-contract preflight')
    p.add_argument('query',nargs='+')
    p.add_argument('--as-of',required=True)
    p.add_argument('--metadata-snapshot',type=Path)
    p.add_argument('--source-db',type=Path,help='Read-only SQLite path for market_sql; not an entitlement grant')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    # Intentionally no CLI entitlement override: requires a trusted service integration.
    result=validate_source_contract(' '.join(a.query),load_metadata_snapshot(a.metadata_snapshot),
        as_of=a.as_of,source_paths={'market_sql':str(a.source_db)} if a.source_db else {})
    payload=json.dumps(result,indent=2)
    print(payload)
    if a.output:
        a.output.write_text(payload,encoding='utf-8')
if __name__=='__main__':main()
