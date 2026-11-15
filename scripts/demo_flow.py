import sys

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PASSWORD = "Demo@1234"


def login(client: httpx.Client, name: str) -> dict[str, str]:
    reply = client.post(f"{API}/auth/login", json={"email": f"{name}@jklu.demo", "password": PASSWORD})
    reply.raise_for_status()
    return {"Authorization": f"Bearer {reply.json()['token']}"}


def agent_events(client: httpx.Client, headers: dict, message: str) -> list[dict]:
    import json

    events = []
    with client.stream("POST", f"{API}/agent/chat", json={"message": message}, headers=headers) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def step(title: str) -> None:
    print(f"\n== {title}")


with httpx.Client(timeout=120) as client:
    faculty = login(client, "faculty01")
    step("Faculty asks the Concierge for a workshop bundle")
    events = agent_events(client, faculty, "Host a 2-day AI workshop on 3-4 Dec for 80 people, 2 external speakers staying 2 nights, 12 cars")
    proposal = next(e["proposal"] for e in events if e["type"] == "proposal")
    print(f"proposal ok={proposal['ok']} components={len(proposal['view']['components'])}")

    step("Faculty presses Submit (a human action)")
    submitted = client.post(f"{API}{proposal['submit']['endpoint']}", json=proposal["submit"]["body"], headers=faculty)
    submitted.raise_for_status()
    bundle = submitted.json()
    print(f"bundle #{bundle['id']} status={bundle['status']}")

    step("Approvers act inside their own scopes")
    for approver in ("estate", "guesthouse.mgr", "parking.officer"):
        headers = login(client, approver)
        for item in client.get(f"{API}/approvals", headers=headers).json():
            if item["booking"]["bundle_id"] == bundle["id"]:
                outcome = client.post(f"{API}/approvals/{item['step_id']}/approve", json={}, headers=headers).json()
                print(f"{approver}: step {item['scope']} -> {outcome['outcome']}")

    step("Bundle is confirmed and passes are issued")
    final = client.get(f"{API}/bundles/{bundle['id']}", headers=faculty).json()
    print(f"bundle status={final['status']}")
    parking = next(c for c in final["components"] if c["resource_type"] == "parking")
    passes = client.get(f"{API}/passes", params={"booking_id": parking["id"]}, headers=faculty).json()
    print(f"{len(passes)} parking passes issued")

    step("Gate scan")
    admin = login(client, "admin")
    security = login(client, "security01")
    client.post(f"{API}/demo/now", json={"now": parking["start"]}, headers=admin)
    scan = client.post(f"{API}/passes/scan", json={"token": passes[0]["token"], "lot_id": parking["resource_id"]}, headers=security).json()
    print(f"scan result={scan['result']}")

    step("Audit chain")
    print(client.get(f"{API}/audit/verify", headers=admin).json())
    client.post(f"{API}/demo/now", json={"now": "2026-11-16T10:00:00"}, headers=admin)
