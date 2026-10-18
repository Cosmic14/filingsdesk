"""Smoke-test a running FilingsDesk API on real SEC filings (not part of CI).

Real filings change every quarter, so this checks behaviour (answered, cited, refused when
it should be), not exact figures. Usage: python scripts/live_smoke.py [API_URL]
"""

import sys
import time

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
QUESTIONS = [
    ("How many employees does NVIDIA have?", True),
    ("What were Apple's Services net sales in the most recent quarter?", True),
    ("How much revenue did NVIDIA's Data Center segment make last quarter?", True),
    ("How much did Alphabet spend on share repurchases?", True),
    ("What does Microsoft say about its capital expenditure on AI infrastructure?", True),
    ("What risks does Amazon describe about AWS competition?", True),
    ("What was Amazon's operating cash flow?", True),
    ("What does Apple say about tariffs?", True),
    ("What is the capital of France?", False),
]

passed = 0
for question, answerable in QUESTIONS:
    started = time.monotonic()
    body = httpx.post(f"{API}/ask", json={"question": question}, timeout=90).json()
    ok = (not body["refused"] and bool(body["citations"])) if answerable else body["refused"]
    passed += ok
    print(f"{'PASS' if ok else 'FAIL'} {time.monotonic() - started:4.1f}s  {question}")
    print(f"     [{body['answered_by']}/{body['confidence']}] {body['answer'][:160]}")
print(f"\n{passed}/{len(QUESTIONS)} behaved as expected")
sys.exit(0 if passed == len(QUESTIONS) else 1)
