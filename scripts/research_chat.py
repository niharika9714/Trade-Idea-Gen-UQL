"""Step 11 single-query and interactive terminal research assistant."""
import argparse
import json
from pathlib import Path
from orchestration.pipeline import run_query


def read_json(path):
    raw=Path(path).read_bytes()
    return json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description='Evidence-grounded research chatbot, Steps 3–10')
    p.add_argument('query',nargs='*')
    p.add_argument('--offline',action='store_true',help='Deterministic JEV and narrative; no Ollama')
    p.add_argument('--no-ollama',action='store_true',help='Disable narrative LLM only')
    p.add_argument('--model',default='qwen3:8b')
    p.add_argument('--timeout',type=int,default=180)
    p.add_argument('--jev-cache-dir',type=Path,help='Opt-in local cache for query understanding only; do not use for sensitive queries')
    p.add_argument('--jev-cache-ttl-hours',type=float,default=24)
    p.add_argument('--as-of')
    p.add_argument('--max-gap-rounds',type=int,default=2)
    p.add_argument('--max-sql-rows',type=int,default=5000)
    p.add_argument('--plan',type=Path,help='Replay a saved plan; requires --evidence')
    p.add_argument('--evidence',type=Path,help='Replay saved evidence; requires --plan')
    p.add_argument('--output',type=Path,help='Save JSON response')
    p.add_argument('--full-trace',action='store_true',help='Include large intermediate artifacts in JSON')
    args=p.parse_args()
    if bool(args.plan)!=bool(args.evidence): p.error('--plan and --evidence must be supplied together')
    saved_plan=read_json(args.plan) if args.plan else None
    saved_evidence=read_json(args.evidence) if args.evidence else None
    def ask(q):
        result=run_query(q,offline=args.offline,use_ollama=not(args.offline or args.no_ollama),
                         model=args.model,timeout=args.timeout,as_of_date=args.as_of,
                         max_gap_rounds=args.max_gap_rounds,max_sql_rows=args.max_sql_rows,
                         saved_plan=saved_plan,saved_evidence=saved_evidence,
                         include_intermediates=args.full_trace,
                         jev_cache_dir=args.jev_cache_dir,jev_cache_ttl_hours=args.jev_cache_ttl_hours)
        print('\n'+result['answer'])
        print(f"\n[{result['status']}] evidence={result.get('counts',{}).get('evidence',0)} "
              f"method={result.get('generation_method')} assessment={result.get('assessment_status')}")
        if result.get('error'): print('Error:',result['error'])
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print('Saved:',args.output)
        return result
    if args.query:
        ask(' '.join(args.query))
    else:
        print('AI INVESTMENT RESEARCH ASSISTANT — Step 11\nType exit to quit. Each question is independent; no conversation memory yet.')
        while True:
            try: q=input('\nYou: ').strip()
            except (EOFError,KeyboardInterrupt): break
            if q.lower() in ('exit','quit'): break
            if q: ask(q)

if __name__=='__main__':main()
