import sys, io, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.service import run_pipeline
tests = [
    "幸福小区楼下有人跳广场舞噪音大，影响老人休息",
    "小区附近晚上施工噪音很大，希望有关部门处理",
    "太原市小店区南中环附近路灯不亮，影响夜间出行",
]
for t in tests:
    try:
        r = run_pipeline(t, user_id="diag")
        g = r.get("gate") or {}
        print(f"OK  [{t[:20]}] route={g.get('route')} dept={r['decision'].get('responsible_department')}")
    except Exception as e:
        print(f"ERR [{t[:20]}] {type(e).__name__}: {str(e)[:120]}")
print("--- done ---")
