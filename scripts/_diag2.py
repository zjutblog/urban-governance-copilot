import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import pandas as pd
from collections import Counter
from dept_rules import map_department

df = pd.read_csv("data/labeled_1200.csv", encoding="utf-8-sig", dtype=str).fillna("")
df["回复组织"] = df["回复组织"].str.strip()
df = df[df["回复组织"] != ""].copy()
df["职能"] = df["回复组织"].map(map_department)

vc = Counter(df["职能"])
print("[新映射 职能分布]")
for k, v in vc.most_common():
    print(f"  {k:8s} {v}")
print(f"\n总部门数: {df['回复组织'].nunique()}, 映射后类别数: {len(vc)}")

# 合并 <10 的类到其他后
MIN = 10
small = set(k for k, v in vc.items() if v < MIN)
print(f"\n[min_class={MIN}] 将并入'其他'的类: {sorted(small)}")
import copy
vc2 = copy.copy(vc)
for k in small:
    vc2["其他"] = vc2.get("其他", 0) + vc2.pop(k)
print("[合并后]")
for k, v in vc2.most_common():
    print(f"  {k:8s} {v}")
