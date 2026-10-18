import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Protocol
import httpx


class ProviderError(RuntimeError):
    pass


class LimitExceeded(RuntimeError):
    pass


class ModelProvider(Protocol):
    async def reason(self, role: str, system: str, payload: dict, budget): ...


class SearchProvider(Protocol):
    async def search(self, query: str, budget): ...


@dataclass
class Budget:
    settings: object
    model_calls: int = 0
    search_calls: int = 0
    tokens: int = 0
    cost_usd: float = 0
    tasks: int = 0
    started: float = 0

    def __post_init__(self):
        self.started = time.monotonic()

    def check(self):
        if time.monotonic() - self.started >= self.settings.max_runtime_seconds:
            raise LimitExceeded('Research runtime limit reached')

    def reserve(self, kind, tokens=0, cost=0):
        self.check()
        if self.tokens + tokens > self.settings.max_tokens or self.cost_usd + cost > self.settings.max_cost_usd:
            raise LimitExceeded('Token or estimated cost limit reached')
        if kind == 'model':
            if self.model_calls >= self.settings.max_model_calls:
                raise LimitExceeded('Model call limit reached')
            self.model_calls += 1
        if kind == 'search':
            if self.search_calls >= self.settings.max_search_calls:
                raise LimitExceeded('Search call limit reached')
            self.search_calls += 1
        self.tokens += tokens
        self.cost_usd += cost

    def task(self):
        self.check()
        if self.tasks >= self.settings.max_tasks:
            raise LimitExceeded('Task limit reached')
        self.tasks += 1

    def usage(self):
        return {'model_calls': self.model_calls, 'search_calls': self.search_calls, 'reserved_tokens': self.tokens, 'estimated_cost_usd': round(self.cost_usd, 4), 'tasks': self.tasks, 'elapsed_seconds': round(time.monotonic() - self.started)}


async def request(client, url, headers, body, reserve):
    for attempt in range(3):
        reserve()  # Every attempt, including retries, consumes budget.
        try:
            response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError:
            if attempt == 2:
                raise ProviderError('Provider network failure; check connectivity and credentials') from None
            await asyncio.sleep(.5 * 2**attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 2:
                await asyncio.sleep(.5 * 2**attempt)
                continue
        if response.status_code >= 400:
            raise ProviderError(f'Provider request failed (HTTP {response.status_code}); no credentials or response body logged')
        try:
            return response.json()
        except ValueError:
            raise ProviderError('Provider returned invalid JSON') from None
    raise ProviderError('Provider retries exhausted')


class OpenAI:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient(timeout=75)

    async def reason(self, role, system, payload, budget):
        model = os.getenv('OPENAI_STRONG_MODEL', 'gpt-4.1') if role in {'Head of Research', 'Deep Research', 'Verification', 'Lead Analyst'} else os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
        text = json.dumps(payload, ensure_ascii=False)
        # Conservative reservation: UTF-8 bytes upper-bound input tokens, plus system and output.
        tokens = len((system + text).encode()) + 4500
        rate = float(os.getenv('LLM_BUDGET_USD_PER_MILLION_TOKENS', '12'))
        body = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}], 'response_format': {'type': 'json_object'}, 'max_completion_tokens': 4000}
        result = await request(self.client, 'https://api.openai.com/v1/chat/completions', {'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}, body, lambda: budget.reserve('model', tokens, tokens * rate / 1e6))
        usage = result.get('usage', {})
        actual = usage.get('total_tokens')
        if isinstance(actual, int) and 0 <= actual <= tokens:
            budget.tokens -= tokens - actual
            budget.cost_usd -= (tokens - actual) * rate / 1e6
        try:
            return json.loads(result['choices'][0]['message']['content'])
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError('Model returned invalid structured output') from None

    async def close(self):
        await self.client.aclose()


class Tavily:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient(timeout=60)

    async def search(self, query, budget):
        body = {'query': query, 'search_depth': 'basic', 'max_results': 5, 'include_raw_content': True}
        result = await request(self.client, 'https://api.tavily.com/search', {'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY']}, body, lambda: budget.reserve('search', cost=float(os.getenv('SEARCH_BUDGET_USD_PER_CALL', '.01'))))
        if not isinstance(result.get('results'), list):
            raise ProviderError('Search provider returned invalid results')
        return result['results']

    async def close(self):
        await self.client.aclose()
