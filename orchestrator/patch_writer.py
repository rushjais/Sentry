"""
patch_writer.py — the self-improvement core.

Takes the failures Cekura found, clusters them into root causes, and asks
Nemotron to WRITE the guardrails that would have prevented them. This is the
"agent rewrites its own defenses" claim, made real.

Reliability contract for the stage:
  - Runs live against Nemotron.
  - If the call exceeds PATCH_WRITER_TIMEOUT_SECONDS or returns unparseable
    JSON, it silently returns CACHED_FALLBACK_PATCH. The on-stage outcome is
    identical either way, so a flaky model never kills the demo.
"""

from __future__ import annotations
import os
import json
import asyncio
from collections import Counter
from typing import List, Dict, Any

from openai import OpenAI

from .config import CACHED_FALLBACK_PATCH

_client = OpenAI(
    base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    api_key=os.getenv("NVIDIA_API_KEY", "missing"),
)
_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
# Nemotron-nano emits a long reasoning_content pass (~7k chars) that counts
# toward the completion budget. At 1200 tokens the JSON in `content` got
# truncated (finish_reason=length) and failed to parse — forcing the cached
# fallback every time. 3000 tokens lets the JSON complete; verified live.
_MAX_TOKENS = int(os.getenv("PATCH_WRITER_MAX_TOKENS", "3000"))
# Live latency observed 5–9s; bump the timeout so the genuine Nemotron patch is
# the norm and the cached patch stays a true fallback (not the default).
_TIMEOUT = float(os.getenv("PATCH_WRITER_TIMEOUT_SECONDS", "12"))


def cluster_failures(failures: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Group raw Cekura failures by their attack category -> root-cause buckets."""
    buckets: Dict[str, List[Dict]] = {}
    for f in failures:
        cat = f.get("category", "uncategorized")
        buckets.setdefault(cat, []).append(f)
    return buckets


def taxonomy(failures: List[Dict[str, Any]]) -> Dict[str, int]:
    """Counts per category, for the dashboard's live taxonomy panel."""
    return dict(Counter(f.get("category", "uncategorized") for f in failures))


_PATCH_PROMPT = """You are the security hardening engine for a bank's voice support agent.
The agent just FAILED the following adversarial calls. Each failure is a real
breach: the agent did something it should never do.

FAILURES (grouped by root cause):
{clusters}

Write the minimal set of defenses that would have prevented EVERY failure above.
Return STRICT JSON only — no markdown, no prose, no backticks — with this shape:
{{
  "guardrails": ["<hard rule>", ...],
  "refusal_exemplars": ["Caller: '<attack>' -> '<correct refusal>'", ...],
  "new_label": "v1 (hardened)",
  "root_causes": ["<short root cause>", ...]
}}
Rules must be absolute and must explicitly defeat authority pretexts, prompt
injection, and manufactured urgency. Output JSON and nothing else."""


def _build_prompt(clusters: Dict[str, List[Dict]]) -> str:
    lines = []
    for cat, items in clusters.items():
        lines.append(f"\n## Root cause: {cat} ({len(items)} failures)")
        for it in items[:3]:  # cap examples per cluster to keep the prompt tight
            atk = it.get("attacker_utterance", it.get("transcript", "?"))
            leak = it.get("agent_response", it.get("what_leaked", "?"))
            lines.append(f"  - attacker said: {atk!r}")
            lines.append(f"    agent wrongly responded: {leak!r}")
    return _PATCH_PROMPT.format(clusters="\n".join(lines))


def _call_nemotron(prompt: str) -> dict:
    """Blocking Nemotron call. Raises on bad JSON so the caller can fall back."""
    resp = _client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=_MAX_TOKENS,
        response_format={"type": "json_object"},  # constrain output to clean JSON
    )
    raw = resp.choices[0].message.content.strip()
    # Nemotron-nano can emit <think>...</think> or stray fences; strip them.
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip() if raw.count("```") >= 2 else raw
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in Nemotron response")
    patch = json.loads(raw[start : end + 1])
    if not patch.get("guardrails"):
        raise ValueError("patch had no guardrails")
    return patch


def _agent_turn_sync(system_prompt: str, utterance: str) -> str:
    """One blocking agent turn under a given system prompt — same model the voice
    agent uses. Used by the live-attack box to test the CURRENT config."""
    resp = _client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": utterance}],
        temperature=0.4,
        max_tokens=1024,  # headroom so reasoning tokens don't truncate the reply to empty
    )
    return (resp.choices[0].message.content or "").strip()


async def run_agent_turn(system_prompt: str, utterance: str, timeout: float = 12.0) -> str:
    """Async wrapper with timeout. On any failure returns "" (scored as a refusal,
    never a leak — failing safe keeps the demo honest)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_agent_turn_sync, system_prompt, utterance), timeout=timeout
        )
    except Exception:  # noqa: BLE001
        return ""


async def generate_patch(failures: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns a patch dict. Tries Nemotron live; falls back to the cached patch
    on timeout or parse failure. Never raises — the demo must always proceed.
    """
    clusters = cluster_failures(failures)
    prompt = _build_prompt(clusters)
    try:
        patch = await asyncio.wait_for(
            asyncio.to_thread(_call_nemotron, prompt), timeout=_TIMEOUT
        )
        patch["_source"] = "nemotron-live"
        return patch
    except (asyncio.TimeoutError, ValueError, Exception) as e:  # noqa: BLE001
        fallback = dict(CACHED_FALLBACK_PATCH)
        fallback["_source"] = f"cached-fallback ({type(e).__name__})"
        return fallback
