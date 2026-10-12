"""Step 8 CLI: controlled follow-up retrieval and reassessment."""
import argparse
import json
from pathlib import Path
from gap_retrieval.loop import run_gap_loop


def load(path):
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'))


def main():
    p = argparse.ArgumentParser(description='Bounded gap-driven retrieval; no investment reasoning')
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--max-rounds', type=int, default=2)
    args = p.parse_args()
    result = run_gap_loop(load(args.plan), load(args.evidence), max_rounds=args.max_rounds)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'initial_status': result['initial_assessment']['status'], 'final_status': result['final_assessment']['status'],
                      'rounds': result['rounds'], 'unresolved_gaps': result['unresolved_gaps'],
                      'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
