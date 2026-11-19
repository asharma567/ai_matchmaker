# 0racle

0racle is an experimental AI dating assistant built around WhatsApp conversations and phone-based onboarding. It explores how conversational intake, profile context and coaching can help people navigate dating with less friction.

This repository contains a Python/FastAPI prototype. The product direction later expanded toward matchmaking: learn about someone, understand their preferences, suggest introductions and help coordinate dates.

## What is in the code

- A Twilio WhatsApp webhook with signature validation.
- Text and media handling, profile onboarding and command routing.
- PostgreSQL profile/message storage and Redis onboarding state.
- A separate voice service with call endpoints and an audio WebSocket.
- LLM/prompt support, scheduling code and automated test files.

These are code capabilities, not a claim that every flow currently works end to end. Live messaging, voice, database and model-provider services have not been validated in this documentation pass.

## Product direction

The July 2025 matchmaker roadmap proposes:

1. **Onboarding:** social screenshots and typed or voice Q&A produce a profile and readable bio.
2. **Preference discovery:** relationship history and reference photos inform a matching schema.
3. **Curated introductions:** three to five suggestions per week, with a reason for each match.
4. **Date coordination:** scheduling, venue suggestions and reminders; MVP reservations are manual.
5. **Feedback:** mutual second-date interest, post-date feedback and coaching/profile refinement.

This is a roadmap, not a shipped-feature checklist. Background checks, live social scraping and booking APIs are outside that MVP scope. This inspection does not establish a working candidate pool, matching service or reservation system.

## Code map

| Files | Role |
| --- | --- |
| `main.py` | Messaging webhook, health endpoint and voice/scheduler entry points |
| `handlers.py`, `services.py` | Command routing and application services |
| `onboarding.py` | Onboarding flow/state |
| `voice.py` | Voice application and audio WebSocket |
| `messaging.py`, `llm_utils.py`, `prompts/` | Messaging and LLM/prompt support |
| `db.py`, `models.py`, `db_utils.py` | Database models/access |
| `config.py`, `scheduler.py` | Configuration and scheduling |
| `start_staging.py`, `tests/`, `conftest.py` | Historical launcher and test code |

The latest commit message mentions Telegram, but the inspected application entry points are WhatsApp/Twilio. A Telegram runtime is not documented here as implemented.

## Developer setup and readiness

The historical entry point is `python start_staging.py`. It loads `.env.staging`, initializes database tables, starts a voice process and launches the main app on port 8000. This is **not yet a verified quick start**: dependencies, service configuration and voice routing need reconciliation first.

Use isolated development accounts, databases and test recipients. Starting the app can create tables or schedule work; call routes can initiate outbound activity. Do not point a trial run at a production WhatsApp account.

Configuration names read by the inspected code:

| Area | Variables |
| --- | --- |
| Environment | `ENVIRONMENT` (set explicitly to `staging`) |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `WHATSAPP_NUMBER` |
| Database | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`; `main.py` also reads `DATABASE_URL` |
| Model/voice | `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY` |
| Routing | `VOICE_API_BASE_URL` |
| Validation | `SKIP_TWILIO_VALIDATION`; keep validation enabled on externally accessible endpoints |

Supply credentials privately. Onboarding currently points Redis at `redis://localhost:6379`; reconcile that fixed local dependency and any additional provider settings before running it.

Known setup gaps:

- `requirements.txt` is mostly unpinned and includes an unexplained `radis` entry. The code directly imports `websocket` (`websocket-client`) and `yaml` (`PyYAML`), neither explicitly declared there. A clean installation and dependency resolution have not been verified.
- `config.py` defaults to `production`, while the staging launcher defaults its displayed environment to `staging`; set the actual environment explicitly.
- The launcher tells you to tunnel port 8000 and use `/voice-greeting`, but the main app exposes `/voice/voice-greeting`. `/voice-greeting` exists on the separate voice service on port 8002. Reconcile public routing, signature forwarding and WebSocket routing before testing calls; neither configuration is verified here.
- `pytest.ini` has a nonstandard `[tool:pytest]` section and coverage options needing review. Test files do not establish a passing suite.
- Review hardcoded endpoints, test recipients and credential-handling files before publishing or running this inherited prototype. The repository is not certified for unchanged redistribution.

## Lessons and status

The earlier coach's postmortem identified weak differentiation from general-purpose chat tools and account/profile-storage friction. The later direction focused on intake, introductions and coordination. These are documented lessons and plans, not evidence of current adoption or launch success.

A current public launch, supported demo URL, production readiness and active-user metrics have not been verified. No license granting redistribution was verified in this handoff.

Useful feedback: which part is valuable enough to revisit—onboarding, coaching, finding suitable people or arranging dates—and what would make it substantially better than a general-purpose chat assistant?

## Documentation basis

Prepared November 11, 2026 from local snapshot `114b2e0` and existing Drive materials. The source inventory and independent review are kept with the handoff. Private conversation notes, contact details, credentials and user data are excluded from this README.
