import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / "backend" / ".env")

key = os.environ.get("GEMINI_API_KEY", "")
if not key:
    print("GEMINI_API_KEY is empty. CampusFlow still runs in offline mode; set the key in backend/.env to go live.")
    sys.exit(0)

from google import genai

client = genai.Client(api_key=key)
candidates = []
for model in client.models.list():
    name = model.name.removeprefix("models/")
    if "generateContent" in (model.supported_actions or []) and "gemini" in name:
        candidates.append(name)
print("Models that support generateContent:")
for name in sorted(candidates):
    print(f"  {name}")

working = []
for name in sorted(candidates, key=lambda n: ("lite" not in n, "flash" not in n, n))[:6]:
    try:
        reply = client.models.generate_content(model=name, contents="Reply with the single word: ok")
        print(f"  tested {name}: {reply.text.strip()[:20]!r}")
        working.append(name)
    except Exception as error:
        print(f"  tested {name}: failed ({str(error)[:80]})")

if working:
    print("\nSuggested backend/.env values (verify quotas in your own project):")
    print(f"GEMINI_MODEL={working[0]}")
    print(f"GEMINI_FALLBACK_MODELS={','.join(working[1:3])}")
    print("LLM_RPM=10\nLLM_RPD=400")
