# CallSentry

**Every call answered. Every appointment booked. Nothing slips through.**

A self-hosted AI voice receptionist. It answers inbound calls 24/7, books
appointments against a real calendar, answers questions from documents you
upload, and hands off to a human when it should.

Local-first by design: speech recognition, the language model, speech synthesis,
and embeddings all run on your hardware. The only thing you pay for is the phone
number.

```
A 5-minute call costs about $0.05. All of it is Twilio.
```

---

## How it works

```
Inbound call
   ↓
Twilio ──────────────────► POST /webhooks/twilio
   │                            │ returns TwiML: <Connect><Stream>
   │                            ▼
   └── bidirectional audio ─► pipecat  (websocket, 8 kHz μ-law)
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        worker /stt        app /internal/turn   worker /tts
        Whisper.cpp        conversation state    Kokoro
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              intent detect   KB search     booking
              Ollama          pgvector      Cal.com
                                 │
                        call ends → transcript → summary
                        → sentiment → cost ledger → dashboard
```

The split matters: **`pipecat` owns audio, `app` owns decisions.** The voice
container is stateless per call and holds no conversation logic, so restarting
it costs you in-flight audio and nothing else. Every conversational rule lives
in `app/callsentry/agents/voice_agent.py`, where it is testable without a
microphone.

---

## Quick start

```bash
make bootstrap
```

That generates secrets, starts everything, migrates the database, pulls the
local models, and seeds a demo business.

```
Dashboard   http://localhost:3000     demo@callsentry.local / changeme
API docs    http://localhost:8000/docs
Providers   http://localhost:8000/settings/providers
```

The first `make models` pull is a few GB and the first call after boot loads
models lazily — run `curl -X POST localhost:8100/warmup` once to avoid paying
that latency on a real caller.

### Taking a real call

1. Expose the API publicly (Twilio must reach it):
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
2. Put that hostname in `.env` as `PUBLIC_BASE_URL`, and its `wss://`
   equivalent for the voice container as `PUBLIC_WS_URL`.
3. In the Twilio console, set the number's **A call comes in** webhook to
   `https://<your-host>/webhooks/twilio` and the status callback to
   `https://<your-host>/webhooks/twilio/status`.
4. Set `TWILIO_PHONE_NUMBER` in `.env` and restart: `make up`.
5. Call the number.

> `PUBLIC_WS_URL` must be `wss://` in production. Twilio will not open a
> plaintext media stream to a public host.

### If ports are already taken

Every host port is overridable — see the port block in `.env.example`:

```bash
APP_PORT=18000 DASHBOARD_PORT=13000 make up
```

---

## Local-first, and what that actually means

`CALLSENTRY_LOCAL_ONLY=1` (the default) is a hard switch, not a preference.
With it set, no paid inference API is called **even if the keys are present**.
Telephony is exempt, because a phone number has no local substitute.

| Component  | Local (free)              | Cloud fallback   | Degraded          |
|------------|---------------------------|------------------|-------------------|
| STT        | Whisper.cpp               | Deepgram         | empty transcript  |
| LLM        | Ollama (Llama 3.2)        | Claude Sonnet 5  | escalate to human |
| TTS        | Kokoro                    | ElevenLabs       | brief silence     |
| Embeddings | nomic-embed-text          | OpenAI           | zero vector       |
| Calendar   | Cal.com (self-hosted)     | Cal.com Cloud    | —                 |
| Telephony  | *(none exists)*           | **Twilio**       | —                 |

Each component walks `local → cloud → mock`. **The mock tier always
succeeds.** That is the whole point: a dead Whisper container must never drop a
live caller. The degradation is written to the call's `provider_log` and shown
in the dashboard, so it surfaces as a visible amber row rather than vanishing
into a stack trace.

Two of those fallbacks are deliberately conservative:

- **Embeddings degrade to a zero vector**, which has cosine similarity 0.0 with
  everything. It can never clear the confidence threshold, so the agent
  escalates instead of answering from a garbage retrieval.
- **The LLM mock returns an escalation**, never an improvised answer.

Watch it work: stop Ollama and call. The agent keeps answering, hands more
calls to a human, and the provider page turns amber.

---

## What keeps it from lying to callers

An AI receptionist that invents a price is worse than no receptionist. Three
mechanisms, none of which rely on asking the model nicely:

1. **Retrieval gate.** If the best-matching document chunk scores below
   `KB_CONFIDENCE_THRESHOLD`, the model is never even asked. There is nothing
   to ground an answer in, so the call escalates.
2. **Abstention token.** The prompt requires the literal string `INSUFFICIENT`
   when the retrieved text doesn't contain the answer. That is intercepted in
   code and converted to an escalation — it never reaches the caller.
3. **Templated compliance.** The opening line carrying the AI disclosure and
   recording notice is a template, not a generation. The model cannot
   accidentally omit it.

The clarifying-question budget (default 3) prevents the other failure mode:
an agent that loops forever instead of admitting it's stuck.

---

## Repository layout

```
app/          FastAPI backend — the brain
  callsentry/
    agents/       voice_agent (state machine), intent, kb, booking
    core/         db, security (AES-256-GCM), provider registry
    services/     llm, stt, tts, embeddings, calcom, sms, costs, retention
    api/routes/   auth, calls, appointments, kb, settings, webhooks, admin
worker/       Whisper.cpp + Kokoro inference over HTTP
pipecat/      Twilio Media Streams websocket — audio only
dashboard/    Next.js 15 operator console
caddy/        reverse proxy + automatic TLS
```

### A note on `pipecat/`

The directory is named for the role it plays. It implements the Twilio Media
Streams pipeline directly — μ-law codec, energy-based endpointing, barge-in,
paced playback — rather than depending on the Pipecat framework.

That was a deliberate trade. The pipeline is ~400 lines, has no version-pinning
risk against a fast-moving dependency, and the part most likely to break subtly
(the G.711 codec) is **verified bit-exact against the reference implementation
across all 65,536 possible samples**. A wrong codec sounds like static on a real
phone call and is miserable to debug; a test that compares against `audioop`
catches it in 150 ms. Swapping in the framework later means replacing one module
behind the same interface.

---

## Costs

Every provider interaction writes a `cost_entries` row — including the free
local ones, at $0.00. That is what lets the dashboard say "47 inference calls,
$0.00" beside "3.2 telephony minutes, $0.045" and make the argument concrete.

Per-call totals are **recomputed from the ledger**, never incremented in place,
so a retried Twilio webhook cannot double-bill.

| | Fully local | All cloud fallbacks |
|---|---|---|
| Twilio | $0.05 | $0.05 |
| Everything else | $0.00 | ~$0.80–1.05 |
| **5-minute call** | **~$0.05** | **~$0.85–1.10** |

---

## Compliance

- AI identity and recording consent disclosed in every opening line (templated).
- Recordings deleted on a per-row `recording_expires_at` stamp written at
  ingest — changing the retention policy never retroactively destroys media a
  business still expects to have.
- Transcripts expire on their own, longer schedule.
- Per-business credentials encrypted with AES-256-GCM, with the business ID
  bound in as additional authenticated data — a ciphertext copied between
  tenant rows fails to decrypt rather than silently authenticating the wrong
  calendar.
- Passwords are SHA-256 pre-hashed before bcrypt, so long passphrases are
  neither truncated nor rejected.
- GDPR Article 17: `retention.erase_caller()` anonymises calls and deletes
  appointments for a phone number; `DELETE /admin/businesses/{id}` cascades a
  full tenant erasure.
- Twilio webhooks are HMAC signature-validated. Without that, anyone could
  POST fabricated calls and costs at a tenant.
- API keys are masked in logs by a structlog processor, not by convention.

---

## Development

```bash
make test                     # backend suite
make lint                     # ruff + mypy
make logs s=app               # tail one service
make psql                     # database shell
make revision m="add thing"   # new migration
```

Both Python services also run without Docker:

```bash
cd app && uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
ENCRYPTION_KEY=$(make -s keygen | head -1 | cut -d= -f2) pytest -q
```

### Test coverage focus

116 tests, concentrated on the things that are silent when wrong:

- **G.711 codec** — exhaustive conformance across every int16 sample.
- **Provider chain** — that a raising provider degrades instead of propagating,
  and that `LOCAL_ONLY` blocks cloud LLMs but not telephony.
- **Credential crypto** — that a ciphertext moved between tenants fails.
- **Endpointing** — that a cough doesn't trigger a turn and a mid-sentence
  breath doesn't cut the caller off.
- **App wiring** — that every route is mounted and every response model
  serialises, which is what catches a missing dependency before deploy.

---

## Configuration

See `.env.example`. The essentials:

| Variable | Purpose |
|---|---|
| `CALLSENTRY_LOCAL_ONLY` | `1` blocks all paid inference APIs |
| `ENCRYPTION_KEY` | 32 bytes base64. **Rotating it orphans stored credentials.** |
| `PUBLIC_BASE_URL` | Where Twilio reaches the API |
| `PUBLIC_WS_URL` | Where Twilio opens the media stream (`wss://` in prod) |
| `INTERNAL_API_TOKEN` | Guards `/internal/*`, used by the voice container |
| `KB_CONFIDENCE_THRESHOLD` | Below this, escalate instead of answering |

The environment is the baseline. Everything except the boot-time infrastructure
(database and Redis URLs, `ENCRYPTION_KEY`, `JWT_SECRET`, `INTERNAL_API_TOKEN`)
can also be changed from the dashboard under **Settings → Platform
configuration** by a user with the operator role. Those overrides are stored
in the `platform_settings` table (secrets encrypted), applied to the running
service immediately, and re-applied on every boot. Clearing an override puts
the environment value back.

Per-business users are managed under **Settings → Users** (add, remove,
change password); each user can change their own password under **Settings →
Your account**. Roles: **admin** (full access to the business), **viewer**
(read-only; every write and the whole Settings area are refused server-side
by `api/readonly.py`), and **operator** (platform staff, cross-tenant).

`DEMO_VIEWER_EMAIL` names a viewer-role account that the public showcase page
signs visitors in as with no password, so "View the dashboard" opens the
overview directly. Leave it blank to send visitors to the sign-in page. The
seed creates `viewer@callsentry.local` for this.

---

## Known limitations

- **Warm transfer is signalled, not executed.** `/internal/turn` returns a
  `transfer_to` number and the call ends; wiring that to a Twilio `<Dial>`
  redirect is a small addition to the media handler.
- **Endpointing is energy-based.** It performs well on a band-limited phone
  line, but a caller in a loud car will trigger early. A neural VAD would drop
  into `Endpointer` behind the same interface.
- **`top_topics` uses keyword counting** over summaries rather than the topic
  labels the analysis step already produces. Fine at low volume; it wants a
  real topics table before it means much.
- **Cal.com slot length is assumed to be 30 minutes** when reading availability.
