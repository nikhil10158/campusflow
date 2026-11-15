import sys

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

with httpx.Client(timeout=300) as client:
    token = client.post(f"{API}/auth/login", json={"email": "admin@jklu.demo", "password": "Demo@1234"}).json()["token"]
    result = client.post(f"{API}/simulate/race", params={"racers": 20}, headers={"Authorization": f"Bearer {token}"}).json()

print(f"room {result['venue']} {result['start']} -> {result['end']}")
print(f"racers={result['racers']} winners={result['winners']} conflicts={result['conflicts']} elapsed={result['elapsed_ms']} ms")
print(f"validator violations: {len(result['validator_violations'])}")
sys.exit(0 if result["winners"] == 1 and not result["validator_violations"] else 1)
