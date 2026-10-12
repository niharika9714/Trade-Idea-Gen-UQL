"""FastAPI service. Start with: uvicorn agent_api.server:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from .core import Config, ResearchAgent, AgentError

app=FastAPI(title='UQL / JEV LLM-Native Research API',version='0.1.0')

class ChatRequest(BaseModel):
    message:str=Field(min_length=1,max_length=5000)
    as_of:str|None=None

@app.get('/health')
def health():return {'status':'ok','mode':'synthetic-only','llm':os.getenv('UQL_MODEL','qwen3:8b')}

@app.post('/v1/chat')
def chat(req:ChatRequest,authorization:str|None=Header(default=None)):
    # Demo token is configured only by trusted server operator; not a bank SSO identity.
    token=os.getenv('UQL_API_TOKEN')
    if not token or authorization!='Bearer '+token:raise HTTPException(401,'Unauthorized')
    if os.getenv('UQL_SYNTHETIC_ONLY','true').lower()!='true':
        raise HTTPException(403,'This prototype is restricted to synthetic data')
    cfg=Config(market_db=os.getenv('UQL_MARKET_DB','data/market_data/market.db'),
               metadata_db=os.getenv('UQL_METADATA_DB','data/metadata.db'),
               documents_dir=os.getenv('UQL_DOCUMENTS_DIR','data/documents'),
               model=os.getenv('UQL_MODEL','qwen3:8b'),
               ollama_url=os.getenv('UQL_OLLAMA_URL','http://127.0.0.1:11434/api/chat'),
               max_rounds=min(12,max(1,int(os.getenv('UQL_MAX_ROUNDS','7')))))
    try:return ResearchAgent(cfg).run(req.message,as_of=req.as_of)
    except AgentError as exc:raise HTTPException(503,str(exc)) from exc
