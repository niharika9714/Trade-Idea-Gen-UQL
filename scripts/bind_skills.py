"""Read-only Step 13C inspection command."""
import argparse,json
from pathlib import Path
from skills.binding import bind_skill_plan,load_metadata_snapshot

def main():
    p=argparse.ArgumentParser(description='Inspect candidate skill input bindings from metadata')
    p.add_argument('query',nargs='+')
    p.add_argument('--as-of')
    p.add_argument('--metadata-snapshot',type=Path,help='Optional exported metadata snapshot JSON')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    result=bind_skill_plan(' '.join(a.query),load_metadata_snapshot(a.metadata_snapshot),as_of=a.as_of)
    out=json.dumps(result,indent=2,ensure_ascii=False)
    print(out)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(out,encoding='utf-8')
if __name__=='__main__':main()
