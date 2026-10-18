# MIAMI CRE VIRTUAL OFFICE

An evidence-led research office for a South Florida tenant-representation broker. Open **Daily Report**, read why a company may need office space, inspect sources and uncertainty, and decide whether to call. No CRM, outreach automation, contact database or manual task orchestration.

**Implementation status:** real OpenAI and Tavily adapters and the research pipeline are implemented. Automated tests use synthetic fixtures and mocked HTTP. No real research cycle has been verified in the build environment: it has no provider secrets and its network policy does not permit the provider hosts. Phase 1 is **not yet operationally accepted**. A successful live run must produce at least five real, independently verified companies; there is no seeded report or fake activity.

## Start in GitHub Codespaces (owner instructions)

1. Open this repository on GitHub. Select branch **phase-1-real-virtual-office** (until the PR is reviewed and merged).
2. Click **Code → Codespaces → Create codespace on phase-1-real-virtual-office**. A 2-core machine is sufficient for the application; paid research happens at external providers.
3. Wait for container setup. It creates `.venv`, installs dependencies and copies `.env.example` to `.env`. Port **8000** opens automatically. Keep the port **Private** in the Ports panel.
4. Open `.env` in the editor. Add the two keys described below. Do not put keys in source files, Settings, screenshots or chat.
5. In the terminal, stop the automatically started server with `pkill -f 'uvicorn app.main:app'`, then run `bash scripts/start.sh`. You must restart after changing `.env`. If the server is already stopped, just run the launch command.
6. In **Ports**, click the browser/globe icon beside **8000**. You should see Daily Report and, once keys are present, an enabled **Run research now** button.

If automatic setup fails, run `bash scripts/setup.sh`, then `bash scripts/start.sh`. Local setup is the same, with Python 3.12 and Node 22 installed. Node is used only for JavaScript syntax checks. The server runs at http://localhost:8000. No frontend bundler or separate production build is needed; FastAPI serves the production HTML, CSS and JavaScript directly.

Codespaces normally allows outbound HTTPS. A managed environment with a restrictive policy must allow **api.openai.com** and **api.tavily.com** through its supported network configuration. Do not bypass that policy.

## Create the API keys

### OpenAI (model reasoning)

1. Visit https://platform.openai.com/ and sign in/create an account.
2. Select or create an API project. Open **Billing** and add a payment method or API credits. A ChatGPT subscription does not include API usage.
3. Open https://platform.openai.com/api-keys and choose **Create new secret key** in that project. Give it permission to call Chat Completions and use the selected models. Copy it once.
4. Set `OPENAI_API_KEY=your-key` in `.env`.
5. Defaults: `OPENAI_MODEL=gpt-4.1-mini` for routine specialists and `OPENAI_STRONG_MODEL=gpt-4.1` for senior judgment roles. Your project must have access to these models. Change these variables to other Chat Completions models supporting JSON objects if needed; adjust budget rates for their pricing. This adapter does not implement provider-managed browsing or model tool calls.
6. Set provider project usage alerts/limits as an additional billing safeguard.

### Tavily (live web research)

1. Visit https://app.tavily.com/ and create/sign in to an account.
2. Open the API keys dashboard and copy an API key. Choose a plan/credits sufficient for your usage; free credits may be available, but verify your current allowance and pricing.
3. Set `TAVILY_API_KEY=your-key` in `.env`.
4. Restart the server. Settings reports key presence; a real run tests connectivity and authorization.

Tavily's basic Search API returns result URLs, excerpts and raw content where available. The app retains the actual returned text and provenance. It does not scrape LinkedIn, bypass login/robots controls or directly fetch arbitrary source URLs. Original source links may be inaccessible or paywalled for the broker; review accessible source material before relying on it.

For access outside a private Codespace, configure a strong `OFFICE_ACCESS_TOKEN` in `.env` and use HTTPS behind a trusted host. The UI asks for this token and keeps it in session storage. Do not expose an unprotected server publicly.

## Run the first real research cycle

1. Open **Settings**. Confirm both providers have keys configured. Set counties/submarkets, minimum estimated SF, industry focus/exclusions, and limits. Defaults prioritize Miami-Dade and approximately 5,000+ SF; unknown footprint can still qualify if the model finds a credible requirement. Save.
2. Click **Run research now** once. It incurs API usage. The office runs without asking you to assign individual tasks.
3. **Virtual Office** shows genuine persisted task events and useful findings. Agents work sequentially in Phase 1 to keep budgets and dependencies predictable; “multi-agent” means separate model roles with structured handoffs, not simultaneous workers.
4. Wait for completion, normally several minutes. The page refreshes every five seconds. The server must stay running; closing the browser is fine, stopping the Codespace is not.
5. Open **Daily Report**. Click a company name to read its intelligence memo, factual findings, inferences, citations, source dates, risks and call angle. **Print brief** produces a printable report. Previous Reports preserves earlier briefs and evidence.
6. A run with fewer than five new verified opportunities is explicitly marked `insufficient_evidence`. A failed provider/budget run publishes no report; the last successful report stays available. Inspect Virtual Office for its failure message. Never treat a previous report as the result of a failed run.
7. For an opt-in paid command-line acceptance check, run `.venv/bin/python -m scripts.live_check`. It uses the same pipeline and persistent report store. Run this only while no UI research cycle is active. A nonzero exit means live Phase 1 acceptance is not met. A second unchanged run can correctly suppress already-seen companies and fail the five-new-company threshold.

## Exact research architecture

| Agent | Responsibility | Default model |
| --- | --- | --- |
| Head of Research | Chooses discovery queries, selects candidates, approves bounded material follow-ups | gpt-4.1 |
| Company Discovery | Extracts actual candidate company identities and evidenced office-demand theses | gpt-4.1-mini |
| Lease Intelligence | Researches historical leases, terms, footprint and unknown expiration | gpt-4.1-mini |
| Company Growth | Investigates local hiring, expansion, acquisitions and contraction | gpt-4.1-mini |
| Location / Occupancy | Establishes supported South Florida locations and footprint | gpt-4.1-mini |
| Signal & News | Investigates recent material local triggers and staleness | gpt-4.1-mini |
| Deep Research | Synthesizes specialists and requests targeted follow-ups | gpt-4.1 |
| Verification | Challenges findings against retrieved material; separately verifies final memo claims | gpt-4.1 |
| Lead Analyst | Selects and ranks supported opportunities, with qualitative priority and explanations | gpt-4.1 |

**All nine roles call real models when a live cycle runs.** They have distinct system responsibilities and output contracts. No hard-coded ranking engine is labeled AI. Python handles validation, search requests, arithmetic, budgets, lifecycle, persistence and duplicate suppression.

Flow: Head plan → Tavily discovery searches → Discovery candidates → Head selection → four specialists per selected company (each receives live search evidence) → Deep Research → optional Head-approved specialist follow-up (depth 0–2) → skeptical Verification → Lead Analyst → final Verification per memo → source/quote/index/size/geography validation → evidence-change deduplication → report.

`ModelProvider` and `SearchProvider` protocols allow replacements; only OpenAI Chat Completions and Tavily Search are implemented. Provider requests retry transient network/429/5xx failures at most twice. Each attempted request consumes a call/cost allowance. Permanent failures stop the run. The manager cannot create unlimited work: code caps candidate count, search/model attempts, agent tasks, follow-up depth, token allowance, estimated cost and total elapsed time.

Every finding includes company, claim, source IDs, verbatim quote, source date if known, role, confidence, fact/inference/speculation and timestamp. Code rejects invented IDs and quotes absent from retained source text. Verification independently judges semantic support, contradictory/stale evidence and geography. Final memos are checked again against cited material. Model verification can still be wrong: this is decision support, not a guarantee of accuracy. Unknown expiration defaults to `UNKNOWN`; timing and office demand remain hypotheses unless explicitly reported.

## Stack and persistent memory

- Python 3.12 / FastAPI / Pydantic; HTTPX adapters; responsive vanilla JavaScript/CSS frontend.
- SQLite WAL at `data/office.sqlite`: settings, cycles, task events, findings, source texts, companies, report snapshots and prior opportunity states. Company records contain prior report intelligence and first/last surfaced dates; source records are URL-keyed. Findings from all completed specialist work persist even if the run fails.
- Full evidence stays in report snapshots. Memory supplied to planning contains the latest 150 surfaced companies. Discovery can revisit them; unchanged evidence/priority/timing fingerprints suppress repeat recommendations. New evidence URLs or source dates, priority changes, or timing changes can resurface a company. Archives display first surfaced and previous priority/timing. This is a baseline heuristic; paraphrased timing or equivalent alternate URLs can still cause repeats, while content updates at an unchanged URL/date may be missed.
- Single application process (`--workers 1`) and one in-process run lock. Settings apply at cycle start. No external task queue or production scheduler. A process restart marks active cycles interrupted; it does not resume partially completed model calls. Back up the database and keep the Codespace to retain memory. Deleting a Codespace deletes local data unless you back it up.
- Future weekday scheduling can invoke the same research service or authenticated POST `/api/research` while the server stays up. Production needs a durable job queue, cross-process lock, managed authentication and storage migration. No scheduling is enabled in this version.

## Cost controls and expected spend

Defaults: 8 companies, up to 10 published prospects, 1 follow-up depth, 90 model attempts, 45 search attempts, 100 agent tasks, 250,000 budgeted tokens, 30-minute deadline, and **$5 estimated cycle cap**. Failed/insufficient runs can still incur charges. The system can stop before finishing if limits are too low; raise limits deliberately after reviewing usage.

There is no verified normal-cycle bill because no live integration was run. A planning scenario with **100k–250k total tokens and 35–45 Tavily basic calls** reserves approximately **$1.55–$3.45** using the configured conservative blended rate of **$12/million tokens** and **$0.01/search**. These are configurable budgeting assumptions, **not current provider price quotes**. Actual routine-model charges are likely lower; verify prices at https://openai.com/api/pricing/ and https://tavily.com/#pricing before paying.

Before each request, input UTF-8 bytes plus output allowance reserve a conservative token/cost amount. Successful OpenAI responses reconcile the final attempt to returned total token usage at the configured blended rate; failures and ambiguous retries retain their reservations. Search attempts reserve the configured per-call rate. An attempt is refused before exceeding an allowance. Settings and cycle activity show estimated cost. This controls *estimated* spend, not a contractual dollar ceiling: rates must cover your chosen models and provider billing rules. Set provider-side billing limits too. Hosting/Codespaces charges are separate; the application has no paid database dependency.

## Tests and production verification

Run `bash scripts/check.sh` after setup. It runs pytest, Python compilation, and JavaScript syntax validation. CI runs the same checks. There is no frontend compilation step because assets are served directly.

Tests cover nine-role orchestration, bounded follow-ups, real adapter request contracts over **mocked HTTP**, quote/source preservation, citation mapping, domain deduplication, persistent company memory, unchanged-report suppression, qualitative priority storage, report generation, skeptical rejection, insufficient evidence, provider errors/retries, token/search/model/cost/runtime limits, API settings validation, access token enforcement, origin protection, HTML/static asset serving and unconfigured UI/API behavior. Synthetic company fixtures appear only in tests, never as application data.

**Not verified:** paid live providers, five real callable companies, browser rendering/interaction across devices, current provider pricing, autonomous weekdays, production hosting. Static/API smoke tests and syntax checks are not a browser test. The research adapters rely on provider-returned excerpts/raw content; there is no independent full-page retrieval or deterministic semantic fact checker. Industry and submarket fit are model judgments, county and known-footprint thresholds are also checked in code. Global company mergers/aliases and repeated evidence need future refinement.

## Repository and review

Work is on `phase-1-real-virtual-office` from `origin/main`. Review the draft pull request before merging. The implementation can be reviewed now, but keep Phase 1 acceptance pending until the paid live check and broker review succeed. No automatic merge or outreach is performed.
