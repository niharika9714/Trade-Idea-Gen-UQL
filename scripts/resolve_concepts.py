"""CLI: query understanding followed by Step 4 terminology enrichment."""
import argparse
import json
from understanding.jev import parse_query
from terminology.resolver import ConceptResolver

def main():
    p=argparse.ArgumentParser()
    p.add_argument('query')
    p.add_argument('--offline',action='store_true',help='Use deterministic JEV parser, no Ollama')
    args=p.parse_args()
    jev=parse_query(args.query,use_llm=not args.offline)
    graph=ConceptResolver().enrich_graph(jev.graph)
    print(json.dumps({'parser':jev.parser,'temporal_scope':jev.temporal_scope,'graph':graph.model_dump(mode='json')},indent=2))
if __name__=='__main__': main()
