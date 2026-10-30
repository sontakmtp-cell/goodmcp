"""Real HTTP negative readiness probe, run inside the private test network."""
import json
import sys
import time
import httpx

expected = int(sys.argv[1])
for attempt in range(100):
    try:
        with httpx.Client(base_url="http://api:8000", timeout=5) as client:
            live = client.get("/health/live")
            ready = client.get("/health/ready")
            assert live.status_code == 200 and ready.status_code == expected
            assert "password" not in ready.text.lower()
            print(json.dumps({"live": live.status_code, "ready": ready.status_code, "expected": expected}))
            break
    except (httpx.TransportError, AssertionError):
        if attempt == 99: raise
        time.sleep(0.1)
