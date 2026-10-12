"""Step 6 CLI: JEV -> resolver -> UQL -> read-only evidence acquisition."""
import argparse
import json
import sys
from pathlib import Path
from understanding.jev import parse_query
from terminology.resolver import ConceptResolver
from planning.uql import build_plan
from retrieval.executor import acquire


def main():
    p = argparse.ArgumentParser(description='Execute bounded Step 5 retrieval plan; no investment reasoning')
    p.add_argument('query', nargs='*')
    p.add_argument('--plan', type=Path, help='Use saved Step 5 JSON plan instead of regenerating it')
    p.add_argument('--offline', action='store_true', help='Disable Ollama when generating a plan')
    p.add_argument('--max-sql-rows', type=int, default=5000)
    p.add_argument('--max-document-units', type=int, default=20)
    p.add_argument('--max-document-hits', type=int, default=3)
    p.add_argument('--output', type=Path, help='Write complete evidence JSON to this file')
    args = p.parse_args()
    if args.plan:
        from core.models import RetrievalPlan
        obj = json.loads(args.plan.read_text(encoding='utf-8-sig'))
        plan = RetrievalPlan.model_validate(obj.get('plan', obj))
        deferred = obj.get('deferred_agendas', [])
    else:
        if not args.query:
            p.error('Provide a query or --plan path')
        jev = parse_query(' '.join(args.query), use_llm=not args.offline)
        graph = ConceptResolver().enrich_graph(jev.graph)
        planned = build_plan(graph, temporal_scope=jev.temporal_scope)
        plan, deferred = planned.plan, planned.deferred_agendas
        print(f'JEV parser: {jev.parser}; fallback_reason: {jev.fallback_reason}', file=sys.stderr)
    result = acquire(plan, max_sql_rows=args.max_sql_rows,
                     max_document_units=args.max_document_units,
                     max_document_hits=args.max_document_hits)
    result.deferred_agendas = deferred
    rendered = result.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
        print(f'Evidence saved: {args.output}', file=sys.stderr)
        print(json.dumps({'plan_id': result.plan_id, 'evidence_count': len(result.evidence),
                          'task_results': result.task_results, 'warnings': result.warnings,
                          'deferred_agendas': deferred}, indent=2))
    else:
        print(rendered)


if __name__ == '__main__':
    main()
