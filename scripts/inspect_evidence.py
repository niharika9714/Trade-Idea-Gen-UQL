"""Inspect bounded evidence supporting a Step 12B citation marker."""
import argparse
import json
from pathlib import Path
from provenance.resolver import inspect_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--marker', required=True, help='For example [F1]')
    parser.add_argument('--max-rows', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.max_rows <= 20:
        parser.error('--max-rows must be between 1 and 20')
    obj = json.loads(args.result.read_text(encoding='utf-8-sig'))
    print(json.dumps(inspect_evidence(obj, args.marker, max_rows=args.max_rows), indent=2))


if __name__ == '__main__':
    main()
