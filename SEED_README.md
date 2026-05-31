# SENTRY seed files — how to use

These are pre-drafted, architecture-correct starter files for SENTRY. They match
PLAN.md and CLAUDE.md exactly. Drop them into your ~/sentry folder, then point
Claude Code at them.

## Install (run in Terminal, one line at a time)
    cd ~/sentry
    unzip ~/Downloads/sentry_seed.zip -d .
    # if it nests under a folder, flatten it:
    #   mv sentry_seed/* . && rmdir sentry_seed

## What's here
- PLAN.md            authoritative spec (same one your CLAUDE.md references)
- SETUP.md           Phase-0 prep commands for this week
- requirements.txt   python deps
- .env.example       every key you'll need
- orchestrator/      FastAPI brain: config.py (exploitable v0 + cached fallback),
                     patch_writer.py (Nemotron + 8s timeout fallback),
                     cekura_client.py (runtime + MOCK mode), main.py (the loop + websocket)
- agent/bot.py       Pipecat voice agent w/ Nemotron + LLMUpdateSettingsFrame hot-swap
- cekura/scenarios.md the 12 attacks + the exact Claude-Code-via-MCP prompt
- dashboard/         EMPTY on purpose — let Claude Code build index.html (Prompt 6),
                     it's the demo surface and benefits from a fresh design pass

## The prompt to give Claude Code after dropping these in
Paste this as your next message in Claude Code (after it finishes the Prompt-1 plan):

"I've dropped seed files into the project (see SEED_README.md). Review every file
in orchestrator/ and agent/, plus cekura/scenarios.md, against PLAN.md and
CLAUDE.md. Tell me: what's solid, what's stubbed and needs finishing, and what's
missing. Don't rewrite working code — finish and wire it up. Confirm the Nemotron
model string and Pipecat NvidiaLLMService import against current docs before
trusting them. Then we'll proceed phase by phase starting from Phase 0 setup."
