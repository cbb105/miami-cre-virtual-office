import asyncio
import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .domain import ROLES, Settings
from .providers import OpenAI, Tavily
from .research import Research
from .store import Store

load_dotenv()
store = Store()
tasks = set()
lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    # A process restart cannot resume a provider call safely. Preserve history and report interruption.
    for cycle in store.cycles():
        if cycle['status'] in ('running', 'queued'):
            store.cycle(cycle['id'], 'interrupted', {**cycle['data'], 'error': 'Server restarted. Run research again; completed evidence is preserved.'})
    yield
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title='MIAMI CRE VIRTUAL OFFICE', lifespan=lifespan)


@app.middleware('http')
async def security(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        token = os.getenv('OFFICE_ACCESS_TOKEN')
        if token and not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + token):
            return JSONResponse({'detail': 'Office access token required'}, status_code=401)
        if request.method not in ('GET', 'HEAD'):
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
                return JSONResponse({'detail': 'Cross-origin request rejected'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/status')
def status():
    configured = bool(os.getenv('OPENAI_API_KEY') and os.getenv('TAVILY_API_KEY'))
    return {'configured': configured, 'providers': {'model': 'OpenAI', 'search': 'Tavily', 'model_configured': bool(os.getenv('OPENAI_API_KEY')), 'search_configured': bool(os.getenv('TAVILY_API_KEY'))}, 'models': {'routine': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), 'strong': os.getenv('OPENAI_STRONG_MODEL', 'gpt-4.1')}, 'cycles': store.cycles(), 'roles': ROLES, 'running': lock.locked()}


@app.get('/api/settings')
def settings():
    return store.settings()


@app.put('/api/settings')
def save_settings(value: Settings):
    store.save_settings(value)
    return value


@app.get('/api/reports')
def reports():
    return store.reports()


@app.get('/api/cycles/{cycle}/events')
def events(cycle: str):
    return store.events(cycle)


async def run(id):
    try:
        await Research(store, OpenAI(), Tavily(), id).execute()
    finally:
        lock.release()


@app.post('/api/research', status_code=202)
async def start():
    if not os.getenv('OPENAI_API_KEY') or not os.getenv('TAVILY_API_KEY'):
        raise HTTPException(503, 'Real research is not configured. Add OPENAI_API_KEY and TAVILY_API_KEY to .env, then restart. No agents have run.')
    if lock.locked():
        raise HTTPException(409, 'Research is already running')
    await lock.acquire()
    id = str(uuid4())
    store.cycle(id, 'queued', {})
    task = asyncio.create_task(run(id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {'cycle_id': id}


STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')
