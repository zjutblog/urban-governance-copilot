# -*- coding: utf-8 -*-
"""摸底 2025 留言板数据集（纯标准库）：编码、规模、字段、缺失率、样例。"""
import sys
import io
import csv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PATH = r"D:\人民网留言板2025.csv"

# 1. 编码嗅探：读 2MB 字节，试解码，选错误最少的
with open(PATH, "rb") as f:
    raw = f.read(2_000_000)

def probe(enc):
    try:
        txt = raw.decode(enc, errors="replace")
        return txt.count("\ufffd"), txt
    except Exception:
        return 10**9, None

best = None
for enc in ("gb18030", "gbk", "utf-8", "utf-16-le", "big5"):
    errs, txt = probe(enc)
    print(f"[probe] {enc:10s} replacement_errors={errs}")
    if best is None or errs < best[0]:
        best = (errs, enc, txt)

errs, enc, txt = best
print(f"[chosen encoding] {enc} (replacement errors={errs})")

# 2. 表头与行数、缺失率
header = None
n_rows = 0
col_total = {}
with open(PATH, "r", encoding=enc, errors="replace", newline="") as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        if i == 0:
            header = row
            col_total = {c: 0 for c in row}
            print(f"\n[columns] {len(header)}")
            for j, c in enumerate(header):
                print(f"  {j}: {repr(c)}")
            continue
        n_rows += 1
        for j, cell in enumerate(row):
            if j < len(header) and cell.strip() == "":
                col_total[header[j]] = col_total.get(header[j], 0) + 1

print(f"\n[rows] {n_rows}")
print("[missing% per column]")
for c in header:
    m = col_total.get(c, 0) / max(n_rows, 1) * 100
    print(f"  miss% {m:6.1f}  {c}")

# 3. 时间字段样例（找包含"时间"的列）
for j, c in enumerate(header):
    if "时间" in c:
        with open(PATH, "r", encoding=enc, errors="replace", newline="") as f:
            reader = csv.reader(f)
            next(reader)
            vals = []
            for row in reader:
                if j < len(row) and row[j].strip():
                    vals.append(row[j])
                if len(vals) >= 3:
                    break
        print(f"\n[time col {c}] samples={vals}")

# 4. 前 2 行样例（截断）
with open(PATH, "r", encoding=enc, errors="replace", newline="") as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        if i == 0:
            continue
        print(f"\n[data row {i}]")
        for j, c in enumerate(header):
            v = row[j] if j < len(row) else ""
            print(f"  {c}: {v[:80]}")
        if i >= 1:
            break
