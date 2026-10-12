"""Inspect a Step 12D JSON result without fetching sources or using an LLM."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Inspect Step 12D coverage diagnostics')
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--gap', help='Optional exact gap key, e.g. rates')
    args = parser.parse_args()
    raw = args.result.read_bytes()
    data = json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'))
    coverage = data.get('source_coverage')
    if not isinstance(coverage, dict):
        parser.error('JSON does not contain source_coverage; rerun with Step 12D installed')
    if args.gap:
        gaps = [g for g in coverage['gaps'] if g['key'] == args.gap]
        if not gaps:
            parser.error(f'No unresolved gap named {args.gap!r}')
        coverage = {'gap': gaps[0], 'assessment_status': coverage['assessment_status']}
    print(json.dumps(coverage, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
