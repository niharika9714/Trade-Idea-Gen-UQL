# HKELI consolidated research chatbot — Windows setup

This is a consolidated **source-code build** based on your uploaded HKELI project. Two live SQL and DOCX acceptance checks passed locally with Qwen; this remains a synthetic-data prototype. See LIVE_VALIDATION.md. The reconciled regression suite passes on Windows; see TEST_STATUS.md for the exact scope.

## 1. Replace code safely

Back up your existing HKELI folder. Extract `HKELI_consolidated_source.zip` to a new folder, e.g. `HKELI_consolidated`. Do **not** copy `.venv` or `.env` from any archive. This archive deliberately omits credentials and local virtual environments.

## 2. Configure source paths (PowerShell)

From the extracted folder, use the *real* absolute paths on your computer:

```powershell
$env:UQL_MARKET_DB = (Resolve-Path '.\data\market_data\market.db').Path
$env:UQL_METADATA_DB = (Resolve-Path '.\data\metadata.db').Path
$env:UQL_DOCUMENTS_DIR = (Resolve-Path '.\data\documents').Path
$env:UQL_API_TOKEN = 'token12345'
$env:UQL_SYNTHETIC_ONLY = 'true'
$env:UQL_MODEL = 'qwen3:8b'
$env:UQL_MAX_ROUNDS = '9'
```

**Important:** The market database included in the old project's `demo_data` is only a small fixture. Point `UQL_MARKET_DB` at your actual synthetic `market.db` containing the intended records. Document `relative_path` values in metadata must resolve under `UQL_DOCUMENTS_DIR`.

## 3. Install and run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt fastapi uvicorn httpx
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m unittest -v test_metadata_end_to_end.py test_binding_repair.py test_sqlite_binding_adapter.py test_binding_integration.py
.\.venv\Scripts\python.exe -m uvicorn agent_api.server:app --host 127.0.0.1 --port 8000
```

Ollama must be running on `http://127.0.0.1:11434`.

## 4. Query in a second PowerShell window

```powershell
$headers = @{ Authorization = 'Bearer token12345' }
$body = @{ message = 'Retrieve the first five available DBS (D05) closing prices in January 2024.' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/v1/chat' -Method Post -Headers $headers -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 15
```

Try document discovery with a question about a document you know is indexed in `metadata.db`. The agent can use `search_catalog`, `search_documents`, `get_document_units` and `inspect_document`; full visual chart/image interpretation and attachment traversal remain unsupported.

## Architecture

JEV → UQL → mandatory evidence obligations → metadata semantics / indexed document discovery → physical source verification → structured SQL or located document extraction → evidence coverage → cited synthesis.

For SQL row requirements, the runtime constructs parameterized SQL from verified bindings. It does not allow the LLM to execute arbitrary SQL in place of that requirement. Catalog value samples are hints, not proof. `as_of` publication-time certification is not automatically available for arbitrary historical SQL.

## Limitations

- Live Windows/Ollama/FastAPI SQL and DOCX checks passed; see LIVE_VALIDATION.md for exact scope and measured CPU latency.
- Source-verified identity bridging requires an exact source-backed alias relationship; a `DBS` vs `DBS Group` mismatch may still block. The agent must not invent the equivalence.
- PDF text, ordered DOCX blocks, PPTX text/tables and Outlook MSG body have locators. Embedded images and charts are **not visually interpreted**.
- The regression tests use simulated models and do not certify live Ollama behavior.
- Use only synthetic or explicitly permitted data; this prototype does not implement enterprise entitlement enforcement.
