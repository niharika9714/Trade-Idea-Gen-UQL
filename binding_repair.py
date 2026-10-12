"""Generic, fail-closed, schema-aware logical-to-physical binding.

This module does not execute the final research query. Its proof objects must be
recorded in the agent evidence ledger before the SQL phase is enabled.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
import json
import hashlib

class BindingRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _columns(schema: list[dict], table_name: str) -> set[str]:
    for table in schema:
        if table.get('table') == table_name:
            return {c['name'] for c in table.get('columns', [])}
    raise BindingRejected('UNKNOWN_TABLE:' + str(table_name))


@dataclass(frozen=True)
class VerifiedBinding:
    database: str
    table: str
    filters: dict[str, Any]
    date_column: str | None
    value_column: str
    filter_sources: dict[str, list[str]]
    proofs: tuple[dict, ...]
    requirement_fingerprint: str

    def to_dict(self) -> dict:
        return {
            'database': self.database, 'table': self.table,
            'filters': self.filters, 'date_column': self.date_column,
            'value_column': self.value_column,
            'filter_sources': self.filter_sources,
            'proofs': list(self.proofs),
            'requirement_fingerprint': self.requirement_fingerprint,
        }


class SchemaAwareBinder:
    """Verify model-proposed mappings against actual schema and source values.

    probe(database, table, column, value) -> bool:
        Must query the physical source and return True ONLY for an exact match.

    relation(database, lookup_table, alias_column, alias_value,
             identifier_column, identifier_value) -> bool:
        Must return True ONLY if one source record connects both values.
        A mere independent existence check is insufficient.

    Both callbacks should be implemented with parameterized, read-only queries,
    and their results recorded in the evidence ledger by the caller.
    """
    def __init__(self, schema: list[dict], probe: Callable, relation: Callable):
        self.schema, self.probe, self.relation = schema, probe, relation

    def verify(self, req: dict, proposal: dict) -> VerifiedBinding:
        if not isinstance(proposal, dict):
            raise BindingRejected('INVALID_RESPONSE_TYPE')
        if proposal.get('unresolved'):
            raise BindingRejected('MODEL_REPORTED_UNRESOLVED')
        database = req.get('database')
        table = proposal.get('table')
        cols = _columns(self.schema, table)
        filters = proposal.get('filters')
        sources = proposal.get('filter_sources')
        if not isinstance(filters, dict) or not filters:
            raise BindingRejected('INVALID_OR_EMPTY_FILTERS')
        if not isinstance(sources, dict) or set(sources) != set(filters):
            raise BindingRejected('INVALID_FILTER_SOURCES_KEYS')
        unknown = set(filters) - cols
        if unknown:
            raise BindingRejected('UNKNOWN_FILTER_COLUMNS:' + ','.join(sorted(unknown)))
        value_column = proposal.get('value_column')
        date_column = proposal.get('date_column')
        if value_column not in cols:
            raise BindingRejected('UNKNOWN_VALUE_COLUMN')
        if (req.get('boundary') or req.get('temporal_scope')) and date_column not in cols:
            raise BindingRejected('UNKNOWN_DATE_COLUMN')
        originals = req.get('filters', {})
        if not isinstance(originals, dict) or not originals:
            raise BindingRejected('NO_LOGICAL_FILTERS')
        bridges = proposal.get('identity_bridges', [])
        if not isinstance(bridges, list):
            raise BindingRejected('INVALID_IDENTITY_BRIDGES')
        proofs: list[dict] = []
        consumed: set[str] = set()
        for column, physical_value in filters.items():
            logical_keys = sources[column]
            if not isinstance(logical_keys, list) or not logical_keys:
                raise BindingRejected('INVALID_FILTER_SOURCE_REFERENCES:' + column)
            if any(k not in originals for k in logical_keys):
                raise BindingRejected('UNKNOWN_LOGICAL_FILTER_SOURCE:' + column)
            if len(logical_keys) != len(set(logical_keys)) or consumed.intersection(logical_keys):
                raise BindingRejected('REUSED_LOGICAL_FILTER_SOURCE:' + column)
            # A source-value probe establishes the physical value is present.
            if not self.probe(database, table, column, physical_value):
                raise BindingRejected('UNVERIFIED_PHYSICAL_VALUE:' + column)
            proofs.append({'type': 'source_value', 'database': database,
                           'table': table, 'column': column, 'value': physical_value})
            for key in logical_keys:
                if str(originals[key]) == str(physical_value):
                    consumed.add(key)
                    continue
                # Different literals (e.g. descriptive name and identifier) require
                # source-backed, same-record identity evidence, never model assertion.
                matched = False
                for bridge in bridges:
                    if not isinstance(bridge, dict):
                        continue
                    if bridge.get('logical_key') != key or bridge.get('physical_column') != column:
                        continue
                    lookup_table = bridge.get('table')
                    alias_col = bridge.get('alias_column')
                    identifier_col = bridge.get('identifier_column')
                    lookup_cols = _columns(self.schema, lookup_table)
                    if alias_col not in lookup_cols or identifier_col not in lookup_cols:
                        raise BindingRejected('UNKNOWN_IDENTITY_BRIDGE_COLUMN')
                    if not self.relation(database, lookup_table, alias_col, originals[key],
                                         identifier_col, physical_value):
                        raise BindingRejected('IDENTITY_RELATION_NOT_VERIFIED:' + key)
                    proofs.append({'type': 'identity_relation', 'database': database,
                                   'table': lookup_table, 'alias_column': alias_col,
                                   'alias_value': originals[key],
                                   'identifier_column': identifier_col,
                                   'identifier_value': physical_value})
                    matched = True
                    break
                if not matched:
                    raise BindingRejected('UNRESOLVED_LOGICAL_ALIAS:' + key)
                consumed.add(key)
        if consumed != set(originals):
            raise BindingRejected('UNCONSUMED_LOGICAL_FILTERS:' + ','.join(sorted(set(originals)-consumed)))
        return VerifiedBinding(database, table, dict(filters), date_column,
                               value_column, dict(sources), tuple(proofs), fingerprint(req))


class BindingRepairSession:
    """Bounded repair with precise error feedback and duplicate detection."""
    def __init__(self, binder: SchemaAwareBinder, requirement: dict, max_attempts: int = 2):
        self.binder, self.requirement = binder, requirement
        self.max_attempts = max_attempts
        self.rejections: list[dict] = []
        self.seen: set[str] = set()

    def next_prompt(self) -> dict:
        return {'task': 'resolve_row_bindings', 'requirement': self.requirement,
                'schema': self.binder.schema,
                'previous_rejections': self.rejections,
                'instruction': (
                    'Return a physical binding using ONLY discovered columns. '
                    'Preserve every logical filter. When two logical identifiers '
                    'refer to one physical value, supply an identity_bridges entry '
                    'pointing to a source table and its alias and identifier columns. '
                    'Never invent source relationships. Do not repeat rejected proposals. '
                    'Return database, table, filters, date_column, value_column, '
                    'and filter_sources. filter_sources maps EACH physical filter '
                    'column to a list of original logical filter keys it preserves. '
                    'Use identity_bridges only for source-backed alias conversions. '
                    'Do not add filters for dates in temporal_scope; the runtime '
                    'applies those bounds separately. Each original logical filter '
                    'key may be consumed only once; never repurpose it for unrelated '
                    'columns or add unrequested constraints. '
                    'Return {"unresolved":true} if no verifiable mapping exists.'
                )}

    def submit(self, proposal: dict) -> VerifiedBinding | None:
        if len(self.rejections) >= self.max_attempts:
            raise BindingRejected('BINDING_REPAIR_BUDGET_EXHAUSTED')
        fp = fingerprint(proposal)
        if fp in self.seen:
            raise BindingRejected('REPEATED_INVALID_BINDING_PROPOSAL')
        self.seen.add(fp)
        try:
            return self.binder.verify(self.requirement, proposal)
        except BindingRejected as exc:
            self.rejections.append({'reason': exc.reason, 'proposal': proposal})
            return None
