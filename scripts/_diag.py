import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pandas as pd
from collections import Counter

df = pd.read_csv("data/labeled_1200.csv", encoding="utf-8-sig", dtype=str).fillna("")
df["回复组织"] = df["回复组织"].str.strip()
df = df[df["回复组织"] != ""].copy()

# 复用映射
import importlib.util
spec = importlib.util.spec_from_file_location("tf", "scripts/train_function_classifier.py")
# 直接内联映射规则（从训练脚本导入 _RULES/map_department）
import re
src = open("scripts/train_function_classifier.py", encoding="utf-8").read()
ns = {}
exec(re.search(r"_RULES = \[.*?\]\n", src, re.S).group(0), ns)
exec("def map_department(name):\n    for kw, cls in _RULES:\n        if kw in name:\n            return cls\n    return '其他'", ns)
map_department = ns["map_department"]

df["职能"] = df["回复组织"].map(map_department)
other = df[df["职能"] == "其他"]
print(f"'其他' 类样本数: {len(other)}")
print("\n'其他' 类里的部门 Top 25（映射遗漏的部门）：")
c = Counter(other["回复组织"])
for dept, n in c.most_common(25):
    print(f"  {n:3d}  {dept}")

# 职能分布
print("\n全部职能分布：")
for k, v in Counter(df["职能"]).most_common():
    print(f"  {k:8s} {v}")
