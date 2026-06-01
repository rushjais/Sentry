# SETUP.md — Phase 0 (do this BEFORE Saturday)

The goal of this week: walk into the venue with Pipecat + Nemotron + Cekura already warm, so Saturday is spent on the **loop and the demo**, not boilerplate. Budget ~4–6 hours total. If you only do steps 1–3, you're still in good shape.

All commands assume macOS/Linux + Python 3.11+. Run from the repo root.

---

## Step 0 — Repo + env (15 min)

```bash
git init sentry && cd sentry
# drop these files in, then:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

You'll fill `.env` as you collect keys below.

---

## Step 1 — NVIDIA Nemotron endpoint (45 min)

NVIDIA NIM gives free OpenAI-compatible access to Nemotron. 1,000 free credits, 40 req/min — plenty for prototyping.

1. Go to **build.nvidia.com**, sign in, create an API key. It starts with `nvapi-`.
2. Put it in `.env`:
   ```
   NVIDIA_API_KEY=nvapi-xxxxxxxx
   NVIDIA_MODEL=nvidia/nemotron-3-nano-30b-a3b
   ```
3. Smoke-test it with the standard OpenAI client (NIM is OpenAI-compatible):
   ```bash
   python - <<'PY'
   import os
   from openai import OpenAI
   c = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
              api_key=os.environ["NVIDIA_API_KEY"])
   r = c.chat.completions.create(
       model=os.environ.get("NVIDIA_MODEL","nvidia/nemotron-3-nano-30b-a3b"),
       messages=[{"role":"user","content":"Say hello in 5 words."}],
       max_tokens=50)
   print(r.choices[0].message.content)
   PY
   ```
   If you get a sentence back, your reasoning brain is live. **This same endpoint powers both the agent and the patch-writer.**

> Note the model string can change — confirm the current Nemotron model name on build.nvidia.com the day before. As of Jan 2026 it's `nvidia/nemotron-3-nano-30b-a3b`.

---

## Step 2 — Pipecat voice agent hello-world (2 hrs — the big one)

Pipecat is the orchestration framework Daily maintains. It has a **built-in `NvidiaLLMService`**, so Nemotron drops straight in.

```bash
pip install -r requirements-voice.txt   # pinned pipecat-ai==0.0.98 + extras
```

Get keys for the fast STT/TTS/transport layer (you know this from Strata):
- **Daily** (transport): dashboard.daily.co → create a room → API key
- **Deepgram** (STT): console.deepgram.com → API key
- **ElevenLabs** (TTS): elevenlabs.io → API key  *(this is what `agent/bot.py` uses)*

Add to `.env`:
```
DAILY_API_KEY=...
DAILY_ROOM_URL=https://YOURDOMAIN.daily.co/sentry
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
```

Then run the provided agent and **talk to it**:
```bash
python agent/bot.py
# open the DAILY_ROOM_URL in a browser, join, and have a conversation
```
**Success = you can speak to it and it answers in <~2s.** If yes, your hardest surface is done before Saturday even starts.

> Reference: the official `pipecat-ai/nemotron-january-2026` repo is the canonical Nemotron+Pipecat example. If `agent/bot.py` fights you, clone that repo and confirm your keys work against it first, then port back.

---

## Step 3 — Cekura account + MCP into Claude Code (1 hr — biggest time-saver)

Cekura is the adversary + eval engine. The MCP server lets Claude Code create agents, define attack scenarios, run tests, and read results from plain English.

1. Sign up at **cekura.ai**, grab your API key from settings.
2. Add to `.env`: `CEKURA_API_KEY=...`
3. Connect the MCP server to Claude Code (one command):
   ```bash
   claude mcp add --transport http Cekura https://api.cekura.ai/mcp \
     --header "X-CEKURA-API-KEY:YOUR_API_KEY"
   ```
4. In Claude Code, confirm it's wired:
   > "List my Cekura agents and show me the schema for creating a test scenario."
5. Register your support agent in Cekura (point it at the Daily room / agent webhook) and run **one trivial test** so you've seen the result payload format. You'll cluster these payloads on Saturday — knowing their shape now saves debugging time then.

---

## Step 4 — AWS ready (don't build, just de-risk) (30 min)

You don't deploy anything this week. You just remove day-of friction:
- Confirm AWS creds in your shell (`aws sts get-caller-identity` returns your account).
- Identify a GPU instance type if you want to self-host Nemotron (e.g. a g5/g6). **But default to the NIM-hosted endpoint** — self-hosting is the first thing on the scope-cut ladder.
- Decide your "on AWS" story: simplest is running the orchestrator (`uvicorn`) on a small AWS box so the redeploy compute genuinely runs on AWS for the NVIDIA/AWS judge narrative.

Add (if self-hosting later):
```
AWS_REGION=us-west-2
```

---

## Step 5 — Skim, don't deep-read (1 hr)
- Pipecat: custom processors + `LLMUpdateSettingsFrame` (this is your hot-swap mechanism)
- Cekura: how scenarios + metrics are defined
- One Nemotron customization example on build.nvidia.com

---

## Friday-night checklist
- [ ] `nvapi-` key works (Step 1 smoke test passes)
- [ ] You can hold a spoken conversation with `agent/bot.py` (Step 2)
- [ ] Cekura MCP responds in Claude Code + you've seen one result payload (Step 3)
- [ ] `aws sts get-caller-identity` works (Step 4)
- [ ] Speakerphone / external mic packed, backup hotspot, all chargers
- [ ] Teammate decision made

If all five boxes are checked Friday night, Saturday is about the **loop and the demo** — which is exactly where the win lives.
