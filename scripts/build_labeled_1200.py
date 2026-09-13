# -*- coding: utf-8 -*-
"""构建小规模统一数据集：1200 条 LLM 标注 JSON + 33 万 CSV 现成标签。

- 输入1: D:\\jupyter_work\\留言板2025_1-12月_1200条.json (LLM 抽取: event_type/demand/urgency/location/...)
- 输入2: D:\\人民网留言板2025.csv (GB18030, original_id = CSV 行号, 已验证 100% 匹配)
- 输出: data/labeled_1200.csv (UTF-8-sig, 系统 corpus 直接读取)

零 LLM 成本：CSV 标签（领域/部门/满意度/评分）是现成的。
"""
import sys
import io
import csv
import json
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

JSON_PATH = r"D:\jupyter_work\留言板2025_1-12月_1200条.json"
CSV_PATH = r"D:\人民网留言板2025.csv"
OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "labeled_1200.csv")

CSV_COLS = [
    "留言ID", "留言主题", "留言内容", "回复内容", "留言类型", "留言领域",
    "留言状态", "留言属地", "省份", "市对象", "留言对象", "回复组织",
    "留言时间", "回复时间", "满意情况", "解决程度评分", "办理态度评分", "办理速度评分",
]
JSON_COLS = ["original_id", "month", "location", "location_hint", "event_type", "event_category", "demand", "urgency"]

# 广告水印值（数据站残留），置空
_WATERMARKS = {"更多数据请关注公众号", "【众鲤数据网】", "官网https://zldatas.com"}

def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        samples = json.load(f)
    print(f"[json] {len(samples)} samples")

    # 读 CSV 中命中的行
    ids = {s["original_id"] for s in samples}
    csv_rows: dict[int, dict] = {}
    with open(CSV_PATH, "r", encoding="gb18030", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for i, row in enumerate(reader):
            if i in ids:
                csv_rows[i] = {c: (row[idx[c]].strip() if idx[c] < len(row) else "") for c in CSV_COLS}
    print(f"[csv] matched {len(csv_rows)}/{len(ids)}")

    # 清洗水印
    for r in csv_rows.values():
        if r["满意情况"] in _WATERMARKS:
            r["满意情况"] = ""

    # 合并写盘
    merged = []
    for s in samples:
        row = {c: s.get(c, "") for c in JSON_COLS}
        cr = csv_rows.get(s["original_id"], {})
        row.update({c: cr.get(c, "") for c in CSV_COLS})
        if not row["留言内容"]:
            row["留言内容"] = s.get("original_text", "")
        merged.append(row)

    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JSON_COLS + CSV_COLS)
        writer.writeheader()
        writer.writerows(merged)
    print(f"[out] {len(merged)} rows -> {OUT_PATH}")

    # 覆盖率报告
    print("\n[coverage]")
    for c in ["留言类型", "留言领域", "回复组织", "满意情况", "回复内容"]:
        n = sum(1 for r in merged if r[c])
        print(f"  {c}: {n}/{len(merged)} ({n/len(merged)*100:.1f}%)")

    print("\n[3 条样例]")
    for r in merged[:3]:
        print(f"  id={r['original_id']} | {r['event_type']}/{r['event_category']} | 领域={r['留言领域']} | 部门={r['回复组织']} | 满意={r['满意情况']}")

if __name__ == "__main__":
    main()
