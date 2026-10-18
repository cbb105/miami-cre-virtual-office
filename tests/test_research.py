"""Mocked provider tests. These never establish live-provider acceptance."""
import asyncio
import json
import httpx
import pytest
from app.domain import Settings, Source
from app.providers import Budget, LimitExceeded, OpenAI, Tavily, ProviderError, request
from app.research import Research, canonical_domain
from app.store import Store


def run(coro):
    return asyncio.run(coro)


class Search:
    async def search(self, query, budget):
        budget.reserve('search', cost=.01)
        return [{'url': 'https://example.org/research', 'title': 'Synthetic test fixture', 'content': 'Synthetic Company announced 35 new Miami office positions in 2026 and a potential expanded office requirement.', 'published_date': '2026-10-01'}]


class Model:
    def __init__(self):
        self.roles = []

    async def reason(self, role, system, p, budget):
        budget.reserve('model', 100, .001)
        self.roles.append(role)
        source = 'e7'  # overwritten by discovery sources
        if role == 'Head of Research':
            if 'candidates' in p:
                return {'selected_domains': [c['domain'] for c in p['candidates']]}
            if 'request' in p:
                return {'approve': True}
            return {'queries': ['test Miami expansion']}
        if role == 'Company Discovery':
            source = p['sources'][0]['id']
            return {'companies': [{'company': f'Synthetic Company {i}', 'domain': f'synthetic{i}.example', 'source_ids': [source]} for i in range(5)] + [{'company':'Duplicate', 'domain':'www.synthetic0.example', 'source_ids':[source]}]}
        if role in ('Lease Intelligence','Company Growth','Location / Occupancy','Signal & News'):
            return {'findings': [{'claim': 'Synthetic test claim about new Miami positions.', 'source_ids': [p['sources'][0]['id']], 'quote': p['sources'][0]['content'], 'kind': 'fact', 'confidence': 'Medium', 'source_date': '2026-10-01'}]}
        if role == 'Deep Research':
            return {'thesis':'Test only', 'risks':['Unknown expiration'], 'follow_up':{'role':'Company Growth','question':'test followup'}}
        if role == 'Verification':
            return {'approved': True, 'accepted_indices': list(range(len(p.get('findings',[])))), 'risks':['Unknown expiration']}
        if role == 'Lead Analyst':
            return {'prospects':[{'company': v['company']['company'], 'domain':v['company']['domain'], 'location':'Miami', 'county':'Miami-Dade', 'estimated_sf':None,'size_basis':'Unknown', 'need':'Potential expansion', 'timing':'UNKNOWN', 'why_call':'Synthetic test thesis', 'call_angle':'Synthetic test only', 'priority':'MEDIUM', 'confidence':'Medium','rationale':['Mocked evidence'], 'risks':['Unknown expiration'], 'finding_indices':[0]} for v in p['verified']]}
        raise AssertionError(role)


def test_full_pipeline_memory_dedup_and_archive(tmp_path):
    store = Store(str(tmp_path/'test.sqlite'))
    model = Model()
    run(Research(store, model, Search(), 'one').execute())
    report = store.reports()[0]
    assert report['status'] == 'completed'
    assert len(report['prospects']) == 5
    assert len(store.memory()) == 5
    assert len(set(model.roles)) == 9
    assert report['prospects'][0]['lease_expiration'] == 'UNKNOWN'
    assert report['prospects'][0]['sources'][0]['url'] == 'https://example.org/research'
    assert report['prospects'][0]['findings'][0]['source_ids'][0] == report['prospects'][0]['sources'][0]['id']
    assert report['usage']['model_calls'] > 30
    run(Research(store, Model(), Search(), 'two').execute())
    assert len(store.reports()) == 2
    assert store.reports()[0]['status'] == 'insufficient_evidence'
    assert store.reports()[0]['prospects'] == []


def test_quote_and_citation_validation(tmp_path):
    r=Research(Store(str(tmp_path/'db')), Model(), Search(), 'one')
    r.sources['a']=Source(id='a',url='https://example.org/a',title='Test',content='This is a genuinely long exact quote from the synthetic source.')
    base={'claim':'Test', 'source_ids':['a'], 'quote':'This is a genuinely long exact quote', 'kind':'fact','confidence':'High'}
    assert len(r.accept_findings('Test','Company Growth',[base]))==1
    assert not r.accept_findings('Test','Company Growth',[{**base,'source_ids':['made-up']}])
    assert not r.accept_findings('Test','Company Growth',[{**base,'quote':'A fabricated quotation that is not in the source material'}])


def test_budget_and_runtime():
    b=Budget(Settings(max_model_calls=10,max_tokens=5000))
    with pytest.raises(LimitExceeded): b.reserve('model',6000)
    for _ in range(10): b.reserve('model')
    with pytest.raises(LimitExceeded): b.reserve('model')
    b.started-=10000
    with pytest.raises(LimitExceeded): b.check()
    b=Budget(Settings(max_cost_usd=.1))
    with pytest.raises(LimitExceeded): b.reserve('search',cost=.11)


def test_failure_never_publishes_report(tmp_path):
    class Broken(Model):
        async def reason(self,*args): raise ProviderError('Provider unavailable')
    store=Store(str(tmp_path/'db'))
    run(Research(store,Broken(),Search(),'broken').execute())
    assert not store.reports()
    assert store.cycles()[0]['status']=='failed'
    assert store.events('broken')[-1]['status']=='failed'


def test_real_adapter_contracts_mocked_http(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-secret')
    monkeypatch.setenv('TAVILY_API_KEY','test-search-secret')
    seen=[]
    def handler(req):
        seen.append(req)
        if req.url.host=='api.openai.com':
            assert json.loads(req.content)['response_format']=={'type':'json_object'}
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"queries":["Miami"]}'}}]})
        return httpx.Response(200,json={'results':[{'url':'https://example.org','content':'test'}]})
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            b=Budget(Settings())
            assert (await OpenAI(c).reason('Head of Research','JSON',{},b))['queries']==['Miami']
            assert len(await Tavily(c).search('Miami',b))==1
            assert b.model_calls==1 and b.search_calls==1
    run(check())
    assert seen[0].headers['Authorization']=='Bearer test-secret'
    assert seen[1].headers['Authorization']=='Bearer test-search-secret'


def test_retry_is_bounded_and_budgeted():
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(503 if len(calls)<3 else 200,json={'ok':True})
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            b=Budget(Settings())
            result=await request(c,'https://example.org',{}, {},lambda:b.reserve('search',cost=.01))
            assert result['ok'] and b.search_calls==3
    run(check())


def test_invalid_provider_json_and_auth_error(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','secret')
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(401,text='secret'))) as c:
            with pytest.raises(ProviderError,match='HTTP 401') as exc:
                await OpenAI(c).reason('Verification','JSON',{},Budget(Settings()))
            assert 'secret' not in str(exc.value)
    run(check())


def test_rejection_produces_honest_insufficient_report(tmp_path):
    class Skeptic(Model):
        async def reason(self,role,*args):
            if role=='Verification': return {'approved':False,'accepted_indices':[]}
            return await super().reason(role,*args)
    store=Store(str(tmp_path/'db'))
    run(Research(store,Skeptic(),Search(),'rejected').execute())
    assert store.reports()[0]['status']=='insufficient_evidence'
    assert not store.reports()[0]['prospects']


def test_company_canonicalization():
    assert canonical_domain('https://www.Example.com/about')=='example.com'
    with pytest.raises(ValueError): canonical_domain('invalid')
