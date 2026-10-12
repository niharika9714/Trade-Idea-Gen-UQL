"""Step 5 CLI: JEV -> Step 4 resolver -> metadata-only UQL plan."""
import argparse
from understanding.jev import parse_query
from terminology.resolver import ConceptResolver
from planning.uql import build_plan

def main():
    p=argparse.ArgumentParser(description='Build metadata-grounded UQL plan (no retrieval)')
    p.add_argument('query',nargs='+')
    p.add_argument('--offline',action='store_true',help='Disable Ollama for deterministic JEV')
    p.add_argument('--max-tasks',type=int,default=12)
    args=p.parse_args()
    jev=parse_query(' '.join(args.query),use_llm=not args.offline)
    graph=ConceptResolver().enrich_graph(jev.graph)
    result=build_plan(graph,temporal_scope=jev.temporal_scope,max_tasks=args.max_tasks)
    print(result.model_dump_json(indent=2))
    print(f'\nJEV parser: {jev.parser}; fallback_reason: {jev.fallback_reason}',file=__import__('sys').stderr)

if __name__=='__main__': main()
