import argparse, json
from understanding.jev import parse_query

def main():
    p=argparse.ArgumentParser(description="Step 3 JEV query understanding (no retrieval)")
    p.add_argument("query",nargs="+",help="Investment research question")
    p.add_argument("--offline",action="store_true",help="Use deterministic fallback without Ollama")
    args=p.parse_args()
    result=parse_query(" ".join(args.query),use_llm=not args.offline)
    print(result.model_dump_json(indent=2))
if __name__=="__main__": main()
