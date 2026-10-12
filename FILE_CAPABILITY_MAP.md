# File map for metadata construction and chatbot API

Audited from the current local Python imports, including imports inside functions, on 2026-10-12. No files were removed.

Entry points: `python -m scripts.build_metadata` and `uvicorn agent_api.server:app`. API requirements include every currently exposed tool, including optional `get_jev_context`, and PDF/DOCX/PPTX/MSG inspection.

## Required source files

| File | Metadata build | Chatbot API |
| --- | --- | --- |
| `agent_api/__init__.py` | No | Keep |
| `agent_api/core.py` | No | Keep |
| `agent_api/metadata_retrieval.py` | No | Keep |
| `agent_api/output_contracts.py` | No | Keep |
| `agent_api/server.py` | No | Keep |
| `app/__init__.py` | Keep | Keep |
| `app/config.py` | Keep | Keep |
| `binding_integration.py` | No | Keep |
| `binding_repair.py` | No | Keep |
| `core/__init__.py` | Keep | Keep |
| `core/enums.py` | Keep | Keep |
| `core/models.py` | Keep | Keep |
| `metadata/__init__.py` | Keep | No |
| `metadata/builders/__init__.py` | Keep | No |
| `metadata/builders/enrichment.py` | Keep | No |
| `metadata/builders/file_builder.py` | Keep | No |
| `metadata/builders/sql_builder.py` | Keep | No |
| `metadata/catalog.py` | Keep | No |
| `metadata/database.py` | Keep | No |
| `retrieval/__init__.py` | No | Keep |
| `retrieval/executor.py` | No | Keep |
| `scripts/__init__.py` | Keep | No |
| `scripts/build_metadata.py` | Keep | No |
| `sqlite_binding_adapter.py` | No | Keep |
| `understanding/__init__.py` | No | Keep |
| `understanding/jev.py` | No | Keep |

Package `__init__.py` files are retained as part of the existing package layout. The API reads `metadata.db` using its own metadata retrieval module; it does not import the metadata-building package.

## Supporting utilities

| Files | Purpose |
| --- | --- |
| `scripts/show_catalog.py`, `scripts/show_document_metadata.py` | Inspect and troubleshoot the generated catalog. Recommended to retain. |
| `scripts/validate_live_chat.py` | Reproduce the live SQL and DOCX acceptance checks. Recommended to retain. |
| `scripts/create_demo_dataset.py` | Synthetic fixture generator; used by retained integration tests. |
| `requirements_complete.txt` | Existing combined dependency list covering builder and API. Keep for the combined project. |
| `requirements.txt`, `requirements_agent_api.txt` | Alternative dependency lists. The API-specific list alone omits document parsing packages. Consolidate before dropping alternatives. |
| `LIVE_VALIDATION.md`, `TEST_STATUS.md`, `START_HKELI.md`, `PROJECT_STATE.md`, `README_METADATA_INSPECTION.md`, `README_STEP2B.md` | Useful operational and validation documentation. |

## Outside the two runtime dependency closures

The following source files are not imported by either entry point above. They are candidates for archiving if you retire their separate CLI workflows. Their tests and fixtures also depend on them; removing them while retaining the full test suite breaks test collection or execution. This is a runtime dependency classification, not a statement that they have no future value.

- `adapters/__init__.py`
- `capabilities/__init__.py`
- `capabilities/benchmark.py`
- `capabilities/catalog.py`
- `core/exceptions.py`
- `evidence/__init__.py`
- `gap_retrieval/__init__.py`
- `gap_retrieval/loop.py`
- `narrative/__init__.py`
- `narrative/engine.py`
- `orchestration/__init__.py`
- `orchestration/jev_cache.py`
- `orchestration/pipeline.py`
- `planning/__init__.py`
- `planning/uql.py`
- `provenance/__init__.py`
- `provenance/resolver.py`
- `quality/__init__.py`
- `quality/gate.py`
- `reasoning/__init__.py`
- `reasoning/engine.py`
- `scripts/acquire_evidence.py`
- `scripts/assess_evidence.py`
- `scripts/bind_skills.py`
- `scripts/create_demo_credentials.py`
- `scripts/generate_narrative.py`
- `scripts/inspect_capabilities.py`
- `scripts/inspect_coverage.py`
- `scripts/inspect_evidence.py`
- `scripts/plan_skills.py`
- `scripts/plan_uql.py`
- `scripts/reason_evidence.py`
- `scripts/research_chat.py`
- `scripts/resolve_concepts.py`
- `scripts/resolve_gaps.py`
- `scripts/run_guarded_research.py`
- `scripts/understand_query.py`
- `scripts/validate_skill_contract.py`
- `skills/__init__.py`
- `skills/binding.py`
- `skills/contracts.py`
- `skills/entitlements.py`
- `skills/guarded.py`
- `skills/planner.py`
- `source_coverage/__init__.py`
- `source_coverage/report.py`
- `temporal/__init__.py`
- `temporal/gate.py`
- `terminology/__init__.py`
- `terminology/resolver.py`

## Tests to retain for these capabilities

- `tests/conftest.py`, `tests/test_metadata.py`, `tests/test_step2b.py`, `tests/test_models.py`.
- `tests/test_agent_api.py`, `tests/test_complete_integration.py`, `tests/test_live_planner_contract.py`.
- Root tests: `test_core_regression.py`, `test_metadata_end_to_end.py`, `test_binding_repair.py`, `test_sqlite_binding_adapter.py`, `test_binding_integration.py`.
- `tests/test_step6_retrieval.py` and its referenced fixtures remain useful because the API reuses document readers from `retrieval/executor.py`.
- `tests/test_step3_jev.py` remains useful for the optional exposed JEV context tool.
- Preserve fixture directories referenced by the tests you retain. Other staged tests exercise their corresponding staged modules.

## Data and generated artifacts

- Keep `data/metadata.db`, the configured market database, and registered source documents. The builder reads market/document sources; the API reads those same sources as evidence.
- Do not remove document assets referenced by retained source documents merely because they are not Python imports.
- Source-reference files may be meaningful dataset assets even when no current runtime imports them.
- `shared_conversation*.html` / `shared_conversation*.txt`, historical output JSON, `logs/`, `test_results/`, and `__pycache__/` are not runtime source dependencies. Archive useful evidence/logs before cleanup.
- `.venv/` is the installed local environment, not application source. Removing it requires reinstalling dependencies.
- Preserve current acceptance artifacts until you have validated a reduced checkout.

## Configuration distinction

The builder uses `INVESTMENT_CHATBOT_*` environment variables through `app/config.py`. The API uses `UQL_*` variables in `agent_api/server.py`. Set both sets consistently if source locations change. Some reused helper modules import `app/config.py`, so keep it even in an API-only checkout.

## Recommended decision

Keep the union of the Required source files table, useful inspection/live-validation utilities, combined dependencies, operational docs, sources, and matching tests. Archive staged research/skills workflows and their matching tests together. Validate the reduced project before deleting the archive. No restructuring or deletion has been performed.
