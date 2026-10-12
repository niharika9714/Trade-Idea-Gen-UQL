import argparse,json
from capabilities.catalog import inspect_capabilities,CATALOG
from capabilities.benchmark import run_benchmark

def main():
    p=argparse.ArgumentParser()
    p.add_argument('query',nargs='*')
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--catalog',action='store_true')
    p.add_argument('--output')
    args=p.parse_args()
    if args.benchmark: result=run_benchmark()
    elif args.catalog: result={'capabilities':CATALOG}
    elif args.query: result=inspect_capabilities(' '.join(args.query))
    else: p.error('Provide a query, --catalog, or --benchmark')
    data=json.dumps(result,indent=2)
    print(data)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(data,encoding='utf-8')
if __name__=='__main__': main()
