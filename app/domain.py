from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


def now():
    return datetime.now(timezone.utc).isoformat()


class Settings(BaseModel):
    counties: list[str] = Field(default_factory=lambda: ['Miami-Dade'])
    submarkets: list[str] = Field(default_factory=lambda: ['Brickell', 'Downtown Miami', 'Coral Gables', 'Coconut Grove', 'Wynwood', 'Miami Beach', 'Aventura', 'Doral', 'Waterford / Airport', 'Blue Lagoon'])
    min_sf: int = Field(default=5000, ge=0, le=1000000)
    emphasize: str = 'Financial services, technology, professional services'
    exclude: str = ''
    max_prospects: int = Field(default=10, ge=5, le=15)
    max_companies: int = Field(default=8, ge=5, le=15)
    depth: int = Field(default=1, ge=0, le=2)
    max_tasks: int = Field(default=100, ge=10, le=250)
    max_model_calls: int = Field(default=90, ge=10, le=250)
    max_search_calls: int = Field(default=45, ge=5, le=150)
    max_tokens: int = Field(default=250000, ge=5000, le=1000000)
    max_cost_usd: float = Field(default=5, ge=.1, le=50)
    max_runtime_seconds: int = Field(default=1800, ge=60, le=7200)


class Source(BaseModel):
    id: str
    url: HttpUrl
    title: str
    content: str
    source_date: str | None = None
    retrieved_at: str = Field(default_factory=now)


class Finding(BaseModel):
    company: str
    claim: str
    source_ids: list[str] = Field(min_length=1)
    quote: str
    kind: Literal['fact', 'inference', 'speculation']
    confidence: Literal['High', 'Medium', 'Low']
    source_date: str | None = None
    agent: str = ''
    timestamp: str = Field(default_factory=now)


class Opportunity(BaseModel):
    company: str
    domain: str
    location: str
    county: str
    estimated_sf: int | None = Field(default=None, ge=0)
    size_basis: str
    need: str
    timing: str
    lease_expiration: str = 'UNKNOWN'
    why_call: str
    call_angle: str
    priority: Literal['HIGH', 'MEDIUM', 'LOW']
    confidence: Literal['High', 'Medium', 'Low']
    rationale: list[str]
    risks: list[str]
    finding_indices: list[int] = Field(min_length=1)


ROLES = {
    'Head of Research': 'Plan focused South Florida tenant research. Select strongest candidate domains and bounded specialist follow-up questions. Reject weak candidates and duplication.',
    'Company Discovery': 'Find real companies with plausible office leasing needs, not merely a Miami presence. Return canonical company name and company website domain. Favor fresh expansion, funding, hiring, acquisitions and headquarters signals.',
    'Lease Intelligence': 'Find lease announcements, actual footprint, addresses, terms and dates. Expiration is UNKNOWN unless explicitly published. Historical lease age alone is not a trigger.',
    'Company Growth': 'Investigate local hiring, funding, acquisitions, business growth or contraction. Distinguish global growth from local office demand.',
    'Location / Occupancy': 'Establish evidenced current South Florida offices, buildings and footprint. Never infer occupancy from a directory alone. Flag closed or superseded locations.',
    'Signal & News': 'Find recent material local corporate events. Compare publication dates. Reject stale announcements presented as current. Focus on triggers that change office demand.',
    'Deep Research': 'Synthesize office demand thesis across specialist evidence. Identify contradictions and request narrow follow-ups only when they can resolve material uncertainty.',
    'Verification': 'Act as skeptical independent verifier. Check every cited quote against provided source text, dates, geographic relevance, company identity and contradictions. Reject unsupported facts and speculative leads. Require evidence of plausible office need, not just local presence.',
    'Lead Analyst': 'Rank verified opportunities by evidenced office requirement, target geography, material trigger, freshness, timing and confidence. Explain positives and negatives without fake precision. Omit weak candidates. Never force a minimum count.',
}
