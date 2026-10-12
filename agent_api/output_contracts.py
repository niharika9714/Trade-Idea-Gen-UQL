"""JSON output contracts for live model planning; source checks stay authoritative."""


def planner_format(tools):
    def obj(properties, required):
        return {"type": "object", "properties": properties,
                "required": required, "additionalProperties": False}

    string = {"type": "string"}
    strings = {"type": "array", "items": string}
    common = {"id": {"type": "string", "pattern": "^r[0-9]+$"},
              "description": string}

    def requirement(kind, fields, required):
        return obj({**common, "kind": {"const": kind}, **fields},
                   ["id", "kind", "description", *required])

    nullable_string = {"type": ["string", "null"]}
    date = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
    rows = requirement("rows", {
        "database": {"enum": ["market", "metadata"]}, "table": string,
        "filters": {"type": "object", "additionalProperties": {
            "type": ["string", "number", "boolean"]}},
        "date_column": nullable_string, "value_column": nullable_string,
        "boundary": {"enum": ["first", "last", None]},
        "count": {"type": "integer", "minimum": 1, "maximum": 100},
        "temporal_scope": {"anyOf": [
            {"type": "null"}, obj({"start": date, "end": date}, ["start", "end"])]},
    }, ["database", "table", "filters", "date_column", "value_column",
        "boundary", "count", "temporal_scope"])
    variants = [rows,
        requirement("schema", {"database": {"enum": ["market", "metadata"]}}, ["database"]),
        requirement("source", {"tool": {"enum": [t["name"] for t in tools]}}, ["tool"]),
        requirement("calculation", {
            "operation": {"enum": ["add", "subtract", "multiply", "divide",
                                    "percent_change", "difference_pp", "mean"]},
            "input_requirements": strings}, ["operation", "input_requirements"])]
    return obj({
        "jev": obj({"user_intent": string, "concepts": strings,
                    "temporal_scope": nullable_string, "ambiguities": strings,
                    "evidence_goals": {"type": "array", "items": string, "minItems": 1}},
                   ["user_intent", "concepts", "temporal_scope", "ambiguities", "evidence_goals"]),
        "uql_plan": obj({key: strings for key in (
            "research_questions", "dependent_tasks", "proposed_tools", "validation_requirements")},
            ["research_questions", "dependent_tasks", "proposed_tools", "validation_requirements"]),
        "requirements": {"type": "array", "minItems": 1, "maxItems": 20,
                         "items": {"anyOf": variants}},
    }, ["jev", "uql_plan", "requirements"])


def response_format(payload):
    """Constrain protocol shapes, without supplying source facts or decisions."""
    if "query" in payload and "tools" in payload and not payload.get("task"):
        return planner_format(payload["tools"])
    if payload.get('task') == 'resolve_row_bindings':
        keys = list(payload['requirement'].get('filters', {}))
        columns = list(dict.fromkeys(col.get('name', col.get('column_name'))
            for table in payload['schema'] for col in table.get('columns', [])))
        binding = {"type": "object", "additionalProperties": False,
            "required": ["database", "table", "filters", "date_column", "value_column", "filter_sources"],
            "properties": {
                "database": {"const": payload['requirement']['database']},
                "table": {"enum": [t.get('table', t.get('table_name')) for t in payload['schema']]},
                "filters": {"type": "object", "minProperties": 1, "maxProperties": len(keys),
                    "additionalProperties": False,
                    "properties": {col: {"type": ["string", "number"]} for col in columns}},
                "date_column": {"enum": [*columns, None]},
                "value_column": {"enum": columns},
                "filter_sources": {"type": "object", "minProperties": 1, "maxProperties": len(keys),
                    "additionalProperties": False,
                    "properties": {col: {"type": "array", "minItems": 1,
                        "uniqueItems": True, "items": {"enum": keys}} for col in columns}},
                "identity_bridges": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["logical_key", "physical_column", "table", "alias_column", "identifier_column"],
                    "properties": {key: {"type": "string"} for key in (
                        'logical_key', 'physical_column', 'table', 'alias_column', 'identifier_column')}}}}}
        return {"anyOf": [binding, {"type": "object", "additionalProperties": False,
            "required": ["unresolved"], "properties": {"unresolved": {"const": True}}}]}
    if payload.get("task") == "audit_plan_completeness":
        count = len(payload["jev"]["evidence_goals"])
        ids = [r["id"] for r in payload["requirements"]]
        return {"type": "object", "additionalProperties": False,
                "required": ["coverage", "missing_goals"], "properties": {
            "coverage": {"type": "array", "minItems": count, "maxItems": count,
                "items": {"type": "object", "additionalProperties": False,
                    "required": ["goal_index", "requirement_ids", "covered", "goal_type"],
                    "properties": {
                        "goal_index": {"type": "integer", "minimum": 0, "maximum": count-1},
                        "requirement_ids": {"type": "array", "items": {"enum": ids}},
                        "covered": {"type": "boolean"},
                        "goal_type": {"enum": ["schema", "content"]}}}},
            "missing_goals": {"type": "array", "items": {
                "type": "integer", "minimum": 0, "maximum": count-1}}}}
    if payload.get("task") == "repair_incomplete_plan" and "tools" in payload:
        variants = planner_format(payload["tools"])["properties"]["requirements"]
        return {"type": "object", "additionalProperties": False,
                "required": ["added_requirements"],
                "properties": {"added_requirements": variants}}
    if "required_citation_ids" in payload:
        known = [e['id'] for e in payload['evidence_log']]
        return {"type": "object", "additionalProperties": False,
                "required": ["action", "answer", "evidence_ids", "limitations"],
                "properties": {
                    "action": {"const": "final"}, "answer": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"enum": known},
                                     "minItems": len(payload['required_citation_ids']),
                                     "uniqueItems": True},
                    "limitations": {"type": "array", "items": {"type": "string"}}}}
    return "json"
