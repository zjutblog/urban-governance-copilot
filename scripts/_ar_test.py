import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.service import run_pipeline
# 信息较明确的（有地点+类型）
r = run_pipeline("太原市小店区南中环附近路灯长期不亮，影响夜间出行", user_id="ar_test")
print("route:", r["gate"].get("route") if r.get("gate") else "?")
print("plan 步骤:", [(s["action_type"], s.get("status")) for s in r["plan"]["steps"]])
print("trace:", [e["action"] for e in r.get("trace", [])])
