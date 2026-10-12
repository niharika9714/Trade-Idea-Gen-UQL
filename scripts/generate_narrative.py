"""CLI for Step 10 narrative generation."""
import argparse
from narrative.engine import narrative_file


def main():
    p = argparse.ArgumentParser(description='Generate verified narrative from Step 9 JSON')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--ollama', action='store_true', help='Attempt local Ollama formatting (validated; fail-closed)')
    p.add_argument('--model', default='qwen3:8b')
    p.add_argument('--timeout', type=int, default=180, help='Ollama HTTP timeout in seconds (default: 180)')
    args = p.parse_args()
    result = narrative_file(args.input, args.output, use_ollama=args.ollama, model=args.model, timeout=args.timeout)
    print(f'Status: {result["assessment_status"]}; method: {result["generation_method"]}; citations: {len(result["source_ledger"])}; output: {args.output}')
    for w in result['warnings']:
        if 'fallback' in w: print('WARNING:', w)


if __name__ == '__main__':
    main()
