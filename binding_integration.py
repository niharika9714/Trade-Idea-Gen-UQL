"""Drop-in coordinator for the HKELI ResearchAgent row-binding phase.

Call only AFTER discover_schema evidence is available. The original mandatory
requirement remains unchanged. SQL may proceed only with a VerifiedBinding.
"""
from binding_repair import BindingRepairSession, SchemaAwareBinder, BindingRejected
from sqlite_binding_adapter import SQLiteBindingAdapter


def resolve_verified_binding(*, model, requirement, schema_evidence, db_paths,
                             query, jev, uql_plan, evidence_ledger,
                             max_attempts=2):
    """Return VerifiedBinding or raise BindingRejected; never run research SQL.

    schema_evidence: result dict from discover_schema, e.g.
      {'database':'market','tables':[...]}.
    evidence_ledger: mutable list; each successful proof is appended with an ID.
    """
    database = requirement.get('database')
    if schema_evidence.get('database') != database:
        raise BindingRejected('SCHEMA_DATABASE_MISMATCH')
    adapter = SQLiteBindingAdapter(db_paths)
    binder = SchemaAwareBinder(schema_evidence['tables'], adapter.probe, adapter.relation)
    session = BindingRepairSession(binder, requirement, max_attempts=max_attempts)
    for _ in range(max_attempts):
        payload = session.next_prompt()
        payload.update({'query':query, 'jev':jev, 'uql_plan':uql_plan})
        proposal = model.ask(
            'You are a schema-aware binding planner. Return JSON only. '
            'Never invent columns. For aliases use identity_bridges with '
            'a discovered lookup table, alias_column and identifier_column. '
            'Preserve all original logical filters.',
            payload)
        try:
            verified = session.submit(proposal)
        except BindingRejected:
            raise
        if verified is None:
            continue
        # The evidence ledger records the *verified* physical facts, not merely
        # the LLM's proposal. Proofs are separate from the immutable obligation.
        for proof in verified.proofs:
            evidence_ledger.append({
                'id': 'e'+str(len(evidence_ledger)+1),
                'tool': 'verify_binding_source',
                'args': dict(proof),
                'result': {'verified': True, 'proof': dict(proof)},
            })
        return verified
    reasons = [x['reason'] for x in session.rejections]
    raise BindingRejected('BINDING_REPAIR_EXHAUSTED:' + '|'.join(reasons))


def assert_sql_binding_ready(requirement, verified_binding):
    """Call immediately before the final read_sql dispatch."""
    from binding_repair import fingerprint
    if verified_binding is None:
        raise BindingRejected('ROW_BINDING_NOT_VERIFIED')
    if verified_binding.requirement_fingerprint != fingerprint(requirement):
        raise BindingRejected('BINDING_REQUIREMENT_CHANGED')
    if verified_binding.database != requirement.get('database'):
        raise BindingRejected('BINDING_DATABASE_MISMATCH')
    return True
