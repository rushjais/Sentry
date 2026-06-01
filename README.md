# SENTRY 🛡️

**A voice agent that defends itself.** It gets attacked live, watches itself fail, rewrites its own guardrails, and defeats the same attack seconds later — autonomously, with no human in the loop.

Built for the Cekura × Daily Voice Agents Hackathon (NVIDIA + AWS).

```
Reasoning:    NVIDIA Nemotron (via NIM, OpenAI-compatible)
Voice:        Pipecat + Daily (WebRTC real-time transport)
Adversary:    Cekura (synthetic adversarial caller swarm + eval)
Self-improve: failure clustering → Nemotron patch-writer → in-memory hot-swap
Compute:      AWS (orchestrator + redeploy compute)
```

---

## The 90-second story

1. **Trust** — Call the support agent ("Ava", a Meridian Bank line). It verifies identity, answers normally, low latency, sounds human.
2. **Break** — Hit **UNLEASH**. A Cekura swarm of adversarial callers hits it. The agent gets socially-engineered into reading out a (fake) card number, live, on the speakers. The dashboard flashes red: `FAILURES 7 / 12`.
3. **Harden** — Hit **HARDEN**. The loop clusters the failures, Nemotron rewrites the guardrails, and the agent hot-swaps its active config in seconds — a timer runs labeled *autonomous, no human input*.
4. **Refuse** — The same attacks replay. The agent refuses cleanly. The dashboard flips green: `FAILURES 0 / 12 · hardened in ~14s`.

The whole thing hinges on one idea: the agent's behavior is governed by a single mutable `ActiveConfig` (system prompt + guardrails + refusal exemplars). "Hardening" rewrites that object and swaps it in memory — so the live "redeploy" is a sub-millisecond operation, not a scary rebuild.

---

## Quick start (one command, no paid keys)

The full break → harden → refuse loop runs headless in **mock mode** — no Cekura account, no voice keys needed. If you have an `NVIDIA_API_KEY`, the real Nemotron patch-writer fires; otherwise a cached fallback patch produces the identical outcome.

```bash
git clone https://github.com/rushjais/Sentry.git && cd Sentry
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-core.txt   # the loop only — installs in seconds
cp .env.example .env                    # optional: add NVIDIA_API_KEY for the live patch-writer
./demo.sh                               # boots the orchestrator + proves the loop
```

Expected tail:

```
=== VERDICT ===
  before: 7/12 (taxonomy={'pii_extraction': 3, 'jailbreak': 2, 'policy_override': 2})
  after:  0/12 in ~14s
  RESULT: PASS ✓ red->green loop proven
```

> **What's real vs. mock, honestly:** the self-hardening loop is fully real — failure clustering, the live Nemotron patch-writer (with a cached fallback), the in-memory config hot-swap, and the secure-policy swap all run for real. The **adversary** is what's mocked in this public demo: `CEKURA_MOCK=1` replays a known set of attack transcripts (`orchestrator/cekura_client.py::_MOCK_FAILURES`) instead of calling Cekura. The live Cekura REST path in that file is **stubbed** — the payload shapes are best-guesses and there's no run-completion polling yet, so wire it to your account before relying on it. The voice agent (`agent/bot.py`) is built but should be verified against your own Daily/Deepgram/ElevenLabs keys.

### Watch it in the browser

```bash
# 1. orchestrator (mock mode is fine for the visual demo too)
CEKURA_MOCK=1 uvicorn orchestrator.main:app --port 8080

# 2. open the dashboard — no build step, it connects to ws://localhost:8080/ws
open dashboard/index.html

# 3. click UNLEASH, then HARDEN, and watch red → green.
```

### Full voice demo (live call)

Install the voice stack and fill in the real keys in `.env` (Daily, Deepgram, ElevenLabs, NVIDIA):

```bash
pip install -r requirements-voice.txt          # heavy: pipecat + daily + silero

uvicorn orchestrator.main:app --port 8080      # terminal 1
python agent/bot.py                            # terminal 2 — joins your DAILY_ROOM_URL
open dashboard/index.html                       # terminal 3
```

Join the Daily room in a browser and talk to Ava. Each spoken turn streams to the dashboard; when you click HARDEN, the running agent hot-swaps its prompt mid-call (no restart) and refuses the attacks it just fell for.

---

## Architecture

```
            ┌─────────────────────────────────────────────┐
            │                  DASHBOARD                    │
            │  (single-file index.html — what judges watch) │
            │  UNLEASH · HARDEN · live feed · taxonomy ·    │
            │  timer · red→green state flip                 │
            └───────────────┬───────────────▲──────────────┘
                            │ WebSocket /ws  │ status events
                            ▼                │
   ┌──────────────┐  attacks ┌──────────────┴───────────────┐
   │   CEKURA      ├────────▶│        ORCHESTRATOR (FastAPI)  │
   │ adversarial   │         │  - holds ACTIVE_CONFIG         │
   │ caller swarm  │◀────────┤  - /unleash /harden /status    │
   │ (the adversary)│ results │  - /ws  /active-prompt         │
   └──────────────┘         │  - hot-swaps config in memory  │
                            └───────┬─────────────────▲──────┘
                  runs the agent    │                 │ patch
                                    ▼                 │
            ┌───────────────────────────┐   ┌─────────┴────────┐
            │     VOICE AGENT (Pipecat)  │   │  PATCH-WRITER     │
            │  Daily (WebRTC) transport  │   │  (Nemotron call)  │
            │  Deepgram STT → Nemotron   │   │  failures → rules │
            │  → ElevenLabs TTS          │   │  + cached fallback│
            │  reads ACTIVE_CONFIG/turn  │   └──────────────────┘
            └───────────────────────────┘
```

## Repo map

| Path | What it is |
|---|---|
| `orchestrator/main.py` | FastAPI brain. Holds `ACTIVE_CONFIG`; exposes `/unleash` `/harden` `/status` `/active-prompt` `/ws` `/agent-turn` `/agent-rearmed` `/cekura-callback`. |
| `orchestrator/config.py` | The mutable `ActiveConfig`, the intentionally-exploitable v0, the secure policy, and the cached fallback patch. `apply_patch()` swaps exploit policy → secure policy. |
| `orchestrator/patch_writer.py` | Failure clusters → Nemotron → config patch. Times out to the cached patch so a flaky model never kills the demo. |
| `orchestrator/cekura_client.py` | Runtime path to trigger Cekura runs + normalize results. `CEKURA_MOCK=1` replays a known failure set for offline demos. |
| `agent/bot.py` | The Pipecat voice agent. Fetches its prompt from `/active-prompt` and hot-swaps mid-call via `LLMMessagesUpdateFrame` when the config version bumps. |
| `dashboard/index.html` | Single-file threat console. WebSocket live feed, UNLEASH/HARDEN, taxonomy, timer, red→green. No build step. |
| `prove_loop.py` | Headless proof of the red→green loop (used by `demo.sh`). |
| `cekura/scenarios.md` | The 12 adversarial scenarios + the Cekura-MCP prompt to scaffold them. |

## Demo-safety notes
- The "redeploy" is an **in-memory config swap**, never a container rebuild.
- `patch_writer` has a **cached fallback** — if the live Nemotron call is slow or returns garbage, it silently uses a known-good patch. Same visible outcome.
- The fake card number is the standard test PAN `4111 1111 1111 1111` — zero real-PII ambiguity.

## Configuration

All config is via environment variables — see `.env.example`. The only one needed for the headless mock demo is none (set `NVIDIA_API_KEY` to exercise the live patch-writer). Voice requires `DAILY_*`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, and `NVIDIA_API_KEY`.

## License

MIT (see below) — the defensive loop is intended to be reusable as a Pipecat plugin.
