"""Inspect or execute a bounded Step 13B skill plan."""
import argparse,json
from pathlib import Path
from skills.planner import SKILLS,plan_skills,run_supported

def main():
    p=argparse.ArgumentParser()
    p.add_argument('query',nargs='*')
    p.add_argument('--catalog',action='store_true')
    p.add_argument('--as-of')
    p.add_argument('--execute',action='store_true',help='Run only a supported single skill via existing pipeline')
    p.add_argument('--offline',action='store_true')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.catalog and not args.query: p.error('Supply a query or --catalog')
    if args.catalog and args.execute: p.error('--catalog cannot execute')
    result=([vars(s) for s in SKILLS] if args.catalog else
            run_supported(' '.join(args.query),as_of=args.as_of,offline=args.offline) if args.execute else
            plan_skills(' '.join(args.query),as_of=args.as_of))
    payload=json.dumps(result,indent=2,ensure_ascii=False,default=str)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(payload,encoding='utf-8')
if __name__=='__main__':main()
