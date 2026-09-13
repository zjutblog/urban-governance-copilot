# -*- coding: utf-8 -*-
"""2025 留言板：关键字段分布统计（纯标准库，流式）。"""
import sys
import io
import csv
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PATH = r"D:\人民网留言板2025.csv"
ENC = "gb18030"

c_type = Counter(); c_field = Counter(); c_status = Counter(); c_sat = Counter()
c_org_top = Counter(); c_prov = Counter()
t_min = None; t_max = None
n = 0
n_with_reply = 0
n_with_rating = 0

with open(PATH, "r", encoding=ENC, errors="replace", newline="") as f:
    reader = csv.reader(f)
    header = next(reader)
    idx = {c: i for i, c in enumerate(header)}
    i_type, i_field = idx["留言类型"], idx["留言领域"]
    i_status, i_sat = idx["留言状态"], idx["满意情况"]
    i_org, i_prov = idx["回复组织"], idx["省份"]
    i_time = idx["留言时间"]
    for row in reader:
        n += 1
        c_type[row[i_type].strip()] += 1
        c_field[row[i_field].strip()] += 1
        c_status[row[i_status].strip()] += 1
        s = row[i_sat].strip()
        if s:
            n_with_rating += 1
            c_sat[s] += 1
        o = row[i_org].strip()
        if o:
            n_with_reply += 1
            c_org_top[o] += 1
        c_prov[row[i_prov].strip()] += 1
        t = row[i_time].strip()
        if t:
            if t_min is None or t < t_min: t_min = t
            if t_max is None or t > t_max: t_max = t

print(f"[rows] {n}")
print(f"[time range] {t_min} ~ {t_max}")
print(f"[with 回复组织] {n_with_reply} ({n_with_reply/n*100:.1f}%)")
print(f"[with 满意情况] {n_with_rating} ({n_with_rating/n*100:.1f}%)")

def show(title, c, k=12):
    print(f"\n[{title}] top{k}")
    for v, cnt in c.most_common(k):
        print(f"  {v:14s} {cnt:7d}  {cnt/n*100:5.1f}%")

show("留言类型", c_type)
show("留言领域", c_field)
show("留言状态", c_status)
show("满意情况", c_sat, 8)
show("回复组织", c_org_top)
show("省份", c_prov, 8)
