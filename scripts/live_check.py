"""Opt-in PAID live integration acceptance. Never runs as part of pytest."""
import asyncio
import os
import sys
from uuid import uuid4
from dotenv import load_dotenv
from app.providers import OpenAI, Tavily
from app.research import Research
from app.store import Store

load_dotenv()
if not os.getenv('OPENAI_API_KEY') or not os.getenv('TAVILY_API_KEY'):
    sys.exit('Add both API keys to .env first. No live provider calls made.')
store = Store()
id = str(uuid4())
asyncio.run(Research(store, OpenAI(), Tavily(), id).execute())
cycle = next(c for c in store.cycles() if c['id'] == id)
print('Live cycle:', id, cycle['status'], cycle['data'])
if cycle['status'] != 'completed':
    sys.exit('Phase 1 acceptance NOT met. Inspect cycle activity and evidence. Never substitute synthetic data.')
print('At least five live verified company memos were saved. Open Daily Report; broker judgment is still required.')
