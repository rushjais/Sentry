"""Headless proof of the SENTRY red->green loop (CEKURA_MOCK=1).

Connects to the orchestrator's /ws, fires /unleash then /harden, and prints the
event stream + the key numbers the dashboard will render. No voice/Daily needed.
"""
import asyncio, json, os, sys
import httpx, websockets

PORT = os.getenv("PORT", "8080")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws"


async def main():
    events = []

    async with websockets.connect(WS) as ws:
        async def pump():
            try:
                async for m in ws:
                    e = json.loads(m)
                    events.append(e)
                    ev = e.get("event")
                    if ev == "attack_result":
                        mark = "PASS" if e.get("passed") else "FAIL"
                        print(f"  [{mark}] {e.get('category'):16} {e.get('attacker','')[:54]}")
                    elif ev in ("attack_summary", "hardened"):
                        print(f"  >> {ev}: failures={e.get('failures')}/{e.get('total')} "
                              f"state={e.get('state')} elapsed={e.get('elapsed','-')}")
                    elif ev == "harden_rule":
                        print(f"     + rule: {e.get('rule','')[:70]}")
                    elif ev in ("attack_started","harden_started","harden_step"):
                        print(f"  -- {ev}: {e.get('step', e.get('root_causes',''))}")
            except Exception:
                pass
        task = asyncio.create_task(pump())
        await asyncio.sleep(0.3)

        async with httpx.AsyncClient(timeout=60) as c:
            print("\n=== UNLEASH (expect RED 7/12) ===")
            r1 = (await c.post(f"{BASE}/unleash")).json()
            await asyncio.sleep(3.0)
            print("  /unleash returned:", r1)
            s1 = (await c.get(f"{BASE}/status")).json()
            print("  /status:", {k: s1[k] for k in ("state","failures","config_label","config_version")})

            print("\n=== HARDEN (expect patch -> swap -> GREEN 0/12) ===")
            r2 = (await c.post(f"{BASE}/harden")).json()
            await asyncio.sleep(2.0)
            print("  /harden returned:", r2)
            s2 = (await c.get(f"{BASE}/status")).json()
            print("  /status:", {k: s2[k] for k in ("state","failures","config_label","config_version")})

            ap = (await c.get(f"{BASE}/active-prompt")).json()
            print(f"\n  /active-prompt version={ap['version']} "
                  f"prompt_len={len(ap['system_prompt'])} "
                  f"(contains GUARDRAILS={'SECURITY GUARDRAILS' in ap['system_prompt']})")

        await asyncio.sleep(0.3)
        task.cancel()

    # ---- assertions ----
    print("\n=== VERDICT ===")
    summ = next((e for e in events if e["event"] == "attack_summary"), {})
    hard = next((e for e in events if e["event"] == "hardened"), {})
    ok = (summ.get("failures") == 7 and summ.get("total") == 12 and
          hard.get("failures") == 0 and hard.get("total") == 12 and
          s2["state"] == "hardened" and s2["config_version"] == 1 and
          "SECURITY GUARDRAILS" in ap["system_prompt"])
    print(f"  before: {summ.get('failures')}/{summ.get('total')} (taxonomy={summ.get('taxonomy')})")
    print(f"  after:  {hard.get('failures')}/{hard.get('total')} in {hard.get('elapsed')}s")
    print(f"  patch source: {r2.get('patch_source')}")
    print("  RESULT:", "PASS ✓ red->green loop proven" if ok else "FAIL ✗")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
