import os, httpx
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv(dotenv_path=".env")   # explicit path — no auto-find

# 1) NVIDIA Nemotron
try:
    c = OpenAI(base_url=os.getenv("NVIDIA_BASE_URL","https://integrate.api.nvidia.com/v1"),
               api_key=os.environ["NVIDIA_API_KEY"])
    # Nemotron-nano emits a reasoning pass before content; too small a budget
    # returns content=None. 2048 gives headroom so this never false-alarms.
    r = c.chat.completions.create(model=os.getenv("NVIDIA_MODEL","nvidia/nemotron-3-nano-30b-a3b"),
        messages=[{"role":"user","content":"Say hello in 5 words."}], max_tokens=2048)
    print("NVIDIA OK:", (r.choices[0].message.content or "").strip())
except Exception as e:
    print("NVIDIA FAIL:", repr(e)[:200])

# 2) Deepgram
try:
    r = httpx.get("https://api.deepgram.com/v1/projects",
                  headers={"Authorization":"Token "+os.environ["DEEPGRAM_API_KEY"]})
    print("Deepgram OK" if r.status_code==200 else f"Deepgram FAIL {r.status_code}: {r.text[:120]}")
except Exception as e:
    print("Deepgram FAIL:", repr(e)[:200])

# 3) ElevenLabs
try:
    r = httpx.get("https://api.elevenlabs.io/v1/voices",
                  headers={"xi-api-key":os.environ["ELEVENLABS_API_KEY"]})
    print("ElevenLabs OK" if r.status_code==200 else f"ElevenLabs FAIL {r.status_code}: {r.text[:120]}")
except Exception as e:
    print("ElevenLabs FAIL:", repr(e)[:200])

# 4) Daily
try:
    r = httpx.get("https://api.daily.co/v1/",
                  headers={"Authorization":"Bearer "+os.environ["DAILY_API_KEY"]})
    print("Daily OK" if r.status_code==200 else f"Daily FAIL {r.status_code}: {r.text[:120]}")
except Exception as e:
    print("Daily FAIL:", repr(e)[:200])
