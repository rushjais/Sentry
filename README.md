# SENTRY 🛡️

**A voice agent that defends itself.** Call it, socially-engineer it into leaking a customer's card number — live, out loud — then watch it cluster its own failure, rewrite its guardrails with an LLM, hot-swap its config mid-call, and refuse the exact same attack seconds later. No human in the loop.

Built for the Cekura × Daily Voice Agents Hackathon (NVIDIA + AWS).

```
Reasoning:    NVIDIA Nemotron (via NIM, OpenAI-compatible)
Voice:        Pipecat + Daily (WebRTC) · Deepgram STT · ElevenLabs TTS
Adversary:    Cekura (adversarial caller swarm + eval)  — see "real vs simulated" below
Self-improve: failure clustering → Nemotron patch-writer → in-memory hot-swap
```

---

## What's real vs. simulated (read this first)

This repo is honest about its seams. For a public, offline-runnable demo, the agent and its self-defense are real; the *adversary fleet* is a replay.

| Component | Status | Notes |
|---|---|---|
| **The voice agent** (Ava) | ✅ **Real** | Live Daily call, Deepgram STT, Nemotron reasoning, ElevenLabs TTS. You talk to it. |
| **The live leak & refusal** | ✅ **Real** | Your actual spoken words + Ava's actual reply are streamed to the dashboard and scored leak-vs-refuse in real time (`/agent-turn`). The card number she leaks pre-harden, and the refusal post-harden, are genuine model output. |
| **The Nemotron patch-writer** | ✅ **Real** | On HARDEN, real failures are clustered and sent to Nemotron, which writes new guardrail rules. (A cached fallback patch covers a slow/garbled model call — identical visible outcome.) |
| **The mid-call hot-swap** | ✅ **Real** | The agent re-fetches its prompt and swaps guardrails on its next turn, no restart. The leak→refuse flip happens on one continuous call. |
| **The "swarm" of 12 attackers + the `7/12 → 0/12` counter** | 🟡 **Simulated** | The big counter is a **mock replay** (`CEKURA_MOCK=1`) of a known attack set — a *visualization* of what a Cekura run shows. It is not a live Cekura API call in this build. |
| **Live Cekura REST integration** | 🔴 **Stubbed** | `orchestrator/cekura_client.py` has the trigger/normalize shape but the payloads are best-guesses and there's no run-completion polling. Wire it to your account before relying on it. |

**Bottom line:** the loop you *hear* on the call — leak, self-harden, refuse — is real. The on-screen attack *fleet* is a replay standing in for a live Cekura swarm.

---

## How the demo works

Two things are on the dashboard at once:

1. **The live-call feed** *(real)* — every turn of your actual phone call with Ava appears as it happens: your words, her response, and a `✗ LEAKED` / `SAFE` verdict. This is the proof.
2. **The swarm counter** *(simulated)* — `UNLEASH` lights up a `7/12` red board and a failure taxonomy; `HARDEN` runs the real patch-writer, then flips it to `0/12` green. This is the cinematic framing around the real call.

The whole thing hinges on one idea: the agent's behavior is governed by a single mutable `ActiveConfig` (system prompt + guardrails + refusal exemplars). "Hardening" rewrites that object and the orchestrator swaps it in memory — so the live "redeploy" is sub-millisecond, not a container rebuild. A **RESET TO v0** button re-arms the exploitable config between takes without restarting anything.

---

## Quick start — the loop, headless, one command

The full break → harden → refuse loop runs with **no paid keys**. With `CEKURA_MOCK=1` the adversary is replayed; if you set `NVIDIA_API_KEY`, the real Nemotron patch-writer fires (otherwise a cached fallback gives the identical result).

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
  patch source: nemotron-live          # or cached-fallback if no NVIDIA key
  RESULT: PASS ✓ red->green loop proven
```

### Watch it in the browser

```bash
CEKURA_MOCK=1 uvicorn orchestrator.main:app --port 8080   # terminal 1
open dashboard/index.html                                  # terminal 2 — no build step
```

Click **⚡ UNLEASH** → red `7/12`, then **🛡 HARDEN** → green `0/12`, then **↺ RESET TO v0** to re-arm. The dashboard connects to `127.0.0.1:8080` over WebSocket.

### Full voice demo (the real thing)

Install the voice stack and put real keys in `.env` (Daily, Deepgram, ElevenLabs, NVIDIA):

```bash
pip install -r requirements-voice.txt                      # heavy: pipecat + daily + silero

CEKURA_MOCK=1 uvicorn orchestrator.main:app --port 8080    # terminal 1 — orchestrator
python agent/bot.py                                         # terminal 2 — Ava joins DAILY_ROOM_URL
open dashboard/index.html                                   # terminal 3 — dashboard
```

Join the Daily room in a browser and talk to Ava. Your turns stream to the live feed in real time. Click **HARDEN** and she hot-swaps her guardrails mid-call — ask the same question again and she refuses. Click **RESET TO v0** to run the take again clean.

---

## Architecture

```
            ┌─────────────────────────────────────────────┐
            │                  DASHBOARD                    │
            │  (single-file index.html — what you watch)    │
            │  UNLEASH · HARDEN · RESET · live-call feed ·  │
            │  taxonomy · timer · red→green state flip      │
            └───────────────┬───────────────▲──────────────┘
                            │ WebSocket /ws  │ status + live-turn events
                            ▼                │
   ┌──────────────┐         ┌───────────────┴───────────────┐
   │  CEKURA swarm │ attacks │        ORCHESTRATOR (FastAPI)  │
   │ (simulated in │────────▶│  - holds ACTIVE_CONFIG         │
   │  this build:  │◀────────┤  - /unleash /harden /reset     │
   │  mock replay) │ results │  - /ws /active-prompt          │
   └──────────────┘         │  - /agent-turn (live scoring)  │
                            │  - hot-swaps config in memory  │
                            └───────┬─────────────────▲──────┘
              real spoken turns ↑   │ serves prompt   │ patch
              (leak/refuse)         ▼                 │
            ┌───────────────────────────┐   ┌─────────┴────────┐
            │   VOICE AGENT (Pipecat)    │   │  PATCH-WRITER     │
            │  Daily WebRTC · Deepgram   │   │  (Nemotron call)  │
            │  STT → Nemotron → 11Labs   │   │  failures → rules │
            │  re-fetches ACTIVE_CONFIG  │   │  + cached fallback│
            │  & hot-swaps mid-call      │   └──────────────────┘
            └───────────────────────────┘
```

## Repo map

| Path | What it is |
|---|---|
| `orchestrator/main.py` | FastAPI brain. Holds `ACTIVE_CONFIG`; exposes `/unleash` `/harden` `/reset` `/status` `/active-prompt` `/ws` `/agent-turn` `/agent-rearmed` `/cekura-callback`. Scores live spoken turns for leaks and broadcasts everything to the dashboard. |
| `orchestrator/config.py` | The mutable `ActiveConfig`, the intentionally-exploitable v0, the hardened secure policy, and the cached fallback patch. `apply_patch()` swaps exploit policy → secure policy. |
| `orchestrator/patch_writer.py` | Clusters failures → calls Nemotron → returns new guardrails. Times out to the cached patch so a flaky model never kills the demo. |
| `orchestrator/cekura_client.py` | Runtime path to trigger Cekura runs + normalize results. `CEKURA_MOCK=1` replays a known failure set (the simulated swarm). Live REST path is stubbed. |
| `agent/bot.py` | The Pipecat voice agent. Fetches its prompt from `/active-prompt`, hot-swaps mid-call when the version bumps, and posts each spoken turn to `/agent-turn` for live scoring. |
| `dashboard/index.html` | Single-file threat console. WebSocket live-call feed, UNLEASH/HARDEN/RESET, taxonomy, timer, red→green. No build step. |
| `prove_loop.py` | Headless proof of the red→green loop (driven by `demo.sh`). |
| `smoke.py` | One-shot check that all four API keys (NVIDIA, Deepgram, ElevenLabs, Daily) are valid. |
| `cekura/scenarios.md` | The 12 adversarial scenarios + the Cekura-MCP prompt to scaffold them. |

## Configuration

All config is via environment variables — see `.env.example`. The headless mock demo needs no keys (set `NVIDIA_API_KEY` to exercise the live patch-writer). The full voice demo needs `DAILY_*`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, and `NVIDIA_API_KEY`. Run `python smoke.py` to verify them.

## License

MIT (see `LICENSE`) — the self-hardening loop is intended to be reusable as a Pipecat plugin.
