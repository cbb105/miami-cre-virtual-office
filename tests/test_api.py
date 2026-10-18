import importlib
from fastapi.testclient import TestClient


def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'api.sqlite'))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('TAVILY_API_KEY',raising=False)
    monkeypatch.delenv('OFFICE_ACCESS_TOKEN',raising=False)
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


def test_frontend_and_unconfigured_state(tmp_path,monkeypatch):
    with client(tmp_path,monkeypatch) as c:
        assert c.get('/').status_code==200
        assert 'MIAMI CRE' in c.get('/').text
        assert c.get('/static/app.js').status_code==200
        assert c.get('/static/style.css').status_code==200
        assert not c.get('/api/status').json()['configured']
        assert c.post('/api/research').status_code==503
        assert c.get('/api/reports').json()==[]
        assert len(c.get('/api/status').json()['roles'])==9
        assert c.get('/').headers['content-security-policy']


def test_settings_validation_auth_and_csrf(tmp_path,monkeypatch):
    with client(tmp_path,monkeypatch) as c:
        settings=c.get('/api/settings').json()
        assert c.put('/api/settings',json={**settings,'max_prospects':100}).status_code==422
        assert c.put('/api/settings',json={**settings,'min_sf':8000}).status_code==200
        assert c.get('/api/settings').json()['min_sf']==8000
        assert c.put('/api/settings',json=settings,headers={'Origin':'https://attacker.example'}).status_code==403
        monkeypatch.setenv('OFFICE_ACCESS_TOKEN','private-test-token')
        assert c.get('/api/status').status_code==401
        assert c.get('/api/status',headers={'Authorization':'Bearer private-test-token'}).status_code==200
