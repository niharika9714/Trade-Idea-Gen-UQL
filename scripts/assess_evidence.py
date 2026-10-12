"""Step 7: assess existing Step 5 plan and Step 6 evidence without re-running retrieval."""
import argparse
import json
from pathlib import Path
from quality.gate import assess


def main():
    parser = argparse.ArgumentParser(description='Conservative evidence sufficiency gate')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    def load_json(path):
        raw = path.read_bytes()
        encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
        return json.loads(raw.decode(encoding))
    plan = load_json(args.plan)
    evidence = load_json(args.evidence)
    result = assess(plan, evidence)
    output = result.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(output, encoding='utf-8')
        print(json.dumps({'status': result.status, 'requirements': {r.key:r.status for r in result.requirements},
                          'gaps': [g.key for g in result.gaps], 'permitted_operations': result.permitted_operations}, indent=2))
    else:
        print(output)

if __name__ == '__main__':
    main()
