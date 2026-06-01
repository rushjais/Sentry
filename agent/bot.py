"""
bot.py — the SENTRY voice agent (Pipecat + Daily + Nemotron + ElevenLabs).

Pipeline:  Daily transport (WebRTC) -> Deepgram STT -> NvidiaLLMService (Nemotron)
           -> ElevenLabs TTS -> back out to Daily.

The one non-standard piece: the agent does NOT hardcode its system prompt. It
fetches it from the orchestrator's /active-prompt at startup and re-applies it
whenever the config version changes. THAT is what makes the on-stage hot-swap
real: when /harden bumps the version, the very next turn the agent is governed
by the new guardrails, with no restart.

HOT-SWAP MECHANISM (verified against pipecat-ai==0.0.98):
  Nemotron/OpenAI-compatible services on 0.0.98 do NOT support a runtime
  `system_instruction` setting (that arrived in the 1.x line). The system prompt
  lives in the conversation context's messages. So we swap the prompt by pushing
  an LLMMessagesUpdateFrame that replaces the context with [new system prompt]
  + the existing non-system history. This is the supported channel and it's what
  the universal context aggregator consumes. Init and hot-swap therefore use the
  SAME channel (context messages) — no double-prompt conflict.

Import paths and the context/aggregator pattern mirror the canonical reference
repo pipecat-ai/nemotron-january-2026 (LLMContext + LLMContextAggregatorPair).
"""

from __future__ import annotations
import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

from pipecat.frames.frames import LLMMessagesUpdateFrame, LLMMessagesAppendFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.nvidia.llm import NvidiaLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer

ORCH = os.getenv("ORCHESTRATOR_URL", "http://localhost:8080")

DEFAULT_PROMPT = "You are Ava, a customer support agent for Meridian Bank."


async def fetch_active_prompt() -> tuple[str, int]:
    """Pull the current composed system prompt + version from the orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{ORCH}/active-prompt")
            r.raise_for_status()
            d = r.json()
            return d["system_prompt"], d["version"]
    except Exception:  # noqa: BLE001 — orchestrator down -> safe default
        return DEFAULT_PROMPT, 0


async def config_watcher(task: PipelineTask, context: LLMContext, start_version: int):
    """Poll the orchestrator; when the config version bumps (a hardening event),
    swap the system prompt in the live conversation. This is the hot-swap.

    We rebuild the message list as [new system prompt] + existing non-system
    history, then push LLMMessagesUpdateFrame so the change takes effect on the
    next turn. Preserving non-system history means a mid-call swap doesn't make
    Ava forget who she's talking to.
    """
    current = start_version
    while True:
        await asyncio.sleep(1.0)
        prompt, version = await fetch_active_prompt()
        if version == current:
            continue
        current = version
        history = [m for m in context.get_messages() if m.get("role") != "system"]
        new_messages = [{"role": "system", "content": prompt}] + history
        await task.queue_frames([LLMMessagesUpdateFrame(messages=new_messages)])
        print(f"[sentry] HOT-SWAPPED to config v{version} "
              f"({len(history)} history msgs preserved)", flush=True)
        # Report the version Ava is NOW enforcing so the dashboard reflects her
        # REAL state (not just the orchestrator's intent). Fire-and-forget.
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                await c.post(f"{ORCH}/agent-rearmed", json={"version": version})
        except Exception:  # noqa: BLE001
            pass


async def main():
    transport = DailyTransport(
        room_url=os.environ["DAILY_ROOM_URL"],
        token=None,
        bot_name="Ava (Meridian Bank)",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),  # turn-taking + barge-in
        ),
    )

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    tts = ElevenLabsTTSService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
    )

    system_prompt, version = await fetch_active_prompt()

    # Nemotron via NIM (OpenAI-compatible). The service streams choices[].delta.content
    # only, so the model's separate reasoning_content is never spoken — Ava speaks
    # a clean reply by default (~0.7s, verified live).
    #
    # IMPORTANT (verified empirically against this NIM endpoint): sending
    # chat_template_kwargs={"thinking": False} BREAKS this model — it routes the
    # whole answer into reasoning_content and returns content=None, so Ava would
    # say nothing. So we do NOT disable thinking by default. Leave NEMOTRON_NO_THINK
    # unset/"0". Only flip it on if you've confirmed your endpoint behaves.
    extra = {}
    if os.getenv("NEMOTRON_NO_THINK", "0") == "1":
        extra["chat_template_kwargs"] = {"thinking": False}
    llm = NvidiaLLMService(
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        model=os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-30b-a3b"),
        params=NvidiaLLMService.InputParams(
            temperature=0.5,
            # Nemotron-nano emits reasoning tokens before the spoken content; too
            # low a cap truncates the reply to empty (Ava goes silent). 1024 gives
            # headroom. This does not make the model think longer, so TTFB is
            # unaffected — it only prevents truncation.
            max_completion_tokens=1024,
            extra=extra,
        ),
    )

    # Single source of truth for the conversation. System prompt lives HERE (the
    # one channel) so startup and hot-swap are consistent.
    context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
    aggregator = LLMContextAggregatorPair(context)

    # Captures both sides of the spoken conversation so we can stream the REAL
    # call onto the dashboard. .user() goes after STT, .assistant() after the
    # assistant aggregator.
    transcript = TranscriptProcessor()

    # ORDER MATTERS: transcript.assistant() must come immediately after
    # transport.output() and BEFORE aggregator.assistant(). The assistant context
    # aggregator consumes the TTSTextFrame/BotStoppedSpeakingFrame that
    # AssistantTranscriptProcessor needs to detect end-of-turn; if the aggregator
    # runs first it swallows them and the transcript processor never emits
    # on_transcript_update — so Ava's spoken turns never reach /agent-turn and the
    # live feed stays empty. This order matches the canonical pipecat example.
    pipeline = Pipeline([
        transport.input(),
        stt,
        transcript.user(),
        aggregator.user(),
        llm,
        tts,
        transport.output(),
        transcript.assistant(),
        aggregator.assistant(),
    ])

    # cancel_on_idle_timeout=False: Pipecat otherwise cancels the pipeline (Ava
    # leaves the room and the process exits) after a quiet gap with no
    # BotSpeaking/UserSpeaking frames. On stage there ARE pauses (presenter talks
    # to the room, clicks HARDEN), so we must NOT drop the call on idle.
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        cancel_on_idle_timeout=False,
    )

    @transport.event_handler("on_first_participant_joined")
    async def _greet(_transport, _participant):
        # Kick off the opening line. A bare LLMRunFrame on an empty conversation
        # makes this model reply "I can't help with that" (nothing to respond to),
        # so we append a one-shot user cue that reliably triggers a warm greeting
        # (verified 5/5). The cue is a user turn, never spoken aloud.
        await task.queue_frames([LLMMessagesAppendFrame(
            messages=[{"role": "user",
                       "content": "(The call just connected. Please greet the caller.)"}],
            run_llm=True,
        )])

    # Stream the REAL spoken conversation to the dashboard. We track the latest
    # caller utterance and, when Ava replies, post the pair to the orchestrator,
    # which scores leak vs refusal and broadcasts it to the live feed.
    last_caller = {"text": ""}

    @transcript.event_handler("on_transcript_update")
    async def _on_turn(_proc, frame):
        for m in frame.messages:
            print(f"[sentry][transcript] role={m.role!r} content={(m.content or '')[:90]!r}", flush=True)
            if m.role == "user":
                last_caller["text"] = (m.content or "").strip()
            elif m.role == "assistant":
                caller = last_caller["text"]
                # Skip the internal greeting cue — it's not a real caller turn.
                if caller.startswith("(The call just connected"):
                    caller = ""
                try:
                    async with httpx.AsyncClient(timeout=3) as c:
                        r = await c.post(f"{ORCH}/agent-turn",
                                     json={"attacker": caller, "agent": (m.content or "").strip()})
                    print(f"[sentry][post] /agent-turn -> {r.status_code} {r.json()}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[sentry][post] /agent-turn FAILED: {e!r}", flush=True)

    # launch the hot-swap watcher alongside the pipeline
    asyncio.create_task(config_watcher(task, context, version))

    runner = PipelineRunner()
    exploitable = "intentionally misconfigured" in system_prompt
    print(f"[sentry] agent live on {os.environ['DAILY_ROOM_URL']} "
          f"(bound to {ORCH} · config v{version} · exploitable={exploitable})", flush=True)
    if not exploitable:
        print("[sentry] WARNING: fetched a NON-exploitable prompt — orchestrator is not at "
              "v0. Ava will refuse from the start. Reset the orchestrator to v0.", flush=True)
    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
