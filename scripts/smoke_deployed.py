import json
import sys
import time
from datetime import datetime, timedelta

import httpx

if len(sys.argv) < 2:
    sys.exit("usage: smoke_deployed.py <api_url>")
API = sys.argv[1].rstrip("/")
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        failures.append(name)


with httpx.Client(timeout=120) as client:
    deadline = time.time() + 120
    ready = False
    while time.time() < deadline and not ready:
        try:
            ready = client.get(f"{API}/health/ready").status_code == 200
        except httpx.HTTPError:
            pass
        if not ready:
            time.sleep(3)
    check("health/ready", ready)

    login = client.post(f"{API}/auth/login", json={"email": "admin@jklu.demo", "password": "Demo@1234"})
    check("login", login.status_code == 200)
    headers = {"Authorization": f"Bearer {login.json().get('token', '')}"}

    now = datetime.fromisoformat(client.get(f"{API}/demo/now", headers=headers).json()["now"])
    start = (now + timedelta(days=2)).replace(hour=11, minute=0, second=0)
    search = client.get(f"{API}/availability/search", params={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "types": "classroom"}, headers=headers).json()
    check("free-room search", len(search["hits"]) > 0, f"({len(search['hits'])} rooms)")

    benchmark = client.get(f"{API}/benchmark/run", params={"events": 8}, headers=headers).json()
    check("benchmark", benchmark["search_latency"][-1]["p95_ms"] < 500, json.dumps(benchmark["search_latency"][-1]))

    events = []
    with client.stream("POST", f"{API}/agent/chat", json={"message": "free classroom tomorrow 2-4 pm for 60"}, headers=headers) as stream:
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    check("offline agent command", any(e["type"] == "done" for e in events) and any(e["type"] == "tool_call" for e in events))

    check("audit chain", client.get(f"{API}/audit/verify", headers=headers).json()["ok"] is True)

print("PASS" if not failures else f"FAILED: {failures}")
sys.exit(1 if failures else 0)
