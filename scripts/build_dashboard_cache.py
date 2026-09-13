# -*- coding: utf-8 -*-
"""33 万数据预处理 → data/dashboard.json（民情看板 + 区县地图 + 风险预警）。

零 LLM 成本，CPU 可跑。读 33 万 CSV，聚合：
- 领域/月份/省份分布、满意度、高发主题词
- 区县级聚合：留言属地(unique) → cpca 抽省市/区县 → geocoder 区县中心坐标
- 风险预警：关键词规则识别涉稳涉急留言（取 top N）
"""
import sys
import csv
import io
import os
import random
import re
import json
from collections import Counter, defaultdict
from datetime import datetime

RISK_TOP_N = int(os.getenv("RISK_TOP_N", "300"))


def _parse_time(s: str):
    """'2025/1/1 9:16' 或 '2025-01-01 09:16' -> datetime；解析失败返回 None。"""
    m = re.match(r"(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})", s or "")
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def sample_risk_yearly(hits: list[dict], top_n: int = RISK_TOP_N) -> list[dict]:
    """按月份分层等比采样 top_n 条，保证风险预警覆盖全年而非只落在年初。

    - 命中数 <= top_n：全量返回（按时间倒序）
    - 否则：各月按占比分配配额（最大余数法凑齐精确 top_n），
      月内随机采样（固定种子可复现），最终整体按时间倒序输出。
    """
    if len(hits) <= top_n:
        hits.sort(key=lambda x: x["_dt"] or datetime.min, reverse=True)
        for h in hits:
            h.pop("_dt", None)
        return hits

    by_month = defaultdict(list)
    for h in hits:
        by_month[h["_dt"].strftime("%Y-%m") if h["_dt"] else "未知"].append(h)

    n_total = len(hits)
    raw = {k: len(v) * top_n / n_total for k, v in by_month.items()}
    quota = {k: int(v) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: raw[k] - quota[k], reverse=True)
    for i in range(top_n - sum(quota.values())):
        quota[order[i % len(order)]] += 1

    rng = random.Random(42)
    picked = []
    for k, bucket in by_month.items():
        rng.shuffle(bucket)
        picked.extend(bucket[: quota.get(k, 0)])
    picked.sort(key=lambda x: x["_dt"] or datetime.min, reverse=True)
    for p in picked:
        p.pop("_dt", None)
    return picked

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import builtins
print = lambda *a, **k: builtins.print(*a, flush=True, **k)

CSV = r"D:\人民网留言板2025.csv"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dashboard.json")

# 高风险关键词（涉稳涉急，正则匹配）
RISK_WORDS = [
    "上访", "群体", "聚集", "堵路", "封路", "罢工", "受伤", "死亡", "死亡事件", "中毒", "断水", "断电",
    "断气", "疫情", "火灾", "塌陷", "塌方", "爆炸", "恐慌", "威胁", "危险", "安全事故", "环评造假",
    "强拆", "暴力", "斗殴", "欠薪", "讨薪", "滞留", "围堵", "媒体", "曝光", "跳楼", "自杀", "信号从",
]

# 高发主题词（从"留言主题"列 n-gram 统计 top 词，jihuabia 超长主题截断）
import jieba

def main():
    print("[load] reading CSV...")
    fields = Counter(); months = Counter(); provinces = Counter(); satis = Counter()
    topics = Counter()
    locality = defaultdict(Counter)          # 属地 -> {领域: count}
    risk_hits = []                           # 全量收集，循环结束后分层采样
    total = 0
    with open(CSV, "r", encoding="gb18030", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            total += 1
            def g(name):
                i = idx.get(name)
                return row[i].strip() if i is not None and i < len(row) else ""
            field = g("留言领域"); mtime = g("留言时间"); prov = g("省份")
            sat = g("满意情况"); loc = g("留言属地"); topic = g("留言主题"); text = g("留言内容")
            if field: fields[field] += 1
            if prov: provinces[prov] += 1
            if sat in ("满意", "不满意"): satis[sat] += 1
            if loc: locality[loc][field if field else "其他"] += 1
            # 月份
            if mtime:
                mm = re.match(r"(\d{4})[-\/](\d{1,2})", mtime)
                if mm:
                    months[f"{mm.group(1)}-{int(mm.group(2)):02d}"] += 1
            # 高发词（用主题，jieba 分词）
            if topic:
                for w in jieba.cut(topic):
                    if len(w) >= 2 and w not in ("什么", "为什么", "怎么", "请问", "我们", "他们", "一下"):
                        topics[w] += 1
            # 风险识别（全量收集，最后按月分层采样，避免只落在年初）
            risk_hit = next((w for w in RISK_WORDS if w in text), None)
            if risk_hit:
                risk_hits.append({
                    "text": text[:120], "province": prov, "time": mtime,
                    "keyword": risk_hit, "field": field, "_dt": _parse_time(mtime),
                })

    risk_rows = sample_risk_yearly(risk_hits)
    risk_span = (risk_rows[-1]["time"], risk_rows[0]["time"]) if risk_rows else ("-", "-")
    print(f"[load] total={total}, fields={len(fields)}, provinces={len(provinces)}, locality_unique={len(locality)}, "
          f"risk_hits={len(risk_hits)}, risk_sampled={len(risk_rows)}, risk_span={risk_span[0]} ~ {risk_span[1]}")

    # 区县坐标（对 unique 属地 cpca+geocode）
    from app.geo.geocoder import get_geocoder
    geo = get_geocoder()
    district_points = {}
    for loc in list(locality.keys())[:8000]:
        r = geo.geocode(loc)
        if r:
            key = (r.get("province"), r.get("city"), r.get("district"))
            if key not in district_points:
                district_points[key] = r
    dist_rows = []
    for (prov, city, dist), r in district_points.items():
        name = r.get("district") or r.get("city") or r.get("province") or ""
        # 聚合该区县的留言（locality 前缀匹配近似）
        cnt = 0; fcnt = Counter()
        prefix = name[:2]
        for loc, fc in locality.items():
            if prefix in loc or name in loc:
                cnt += sum(fc.values()); fcnt.update(fc)
        if cnt > 0:
            dist_rows.append({
                "name": name, "province": r.get("province"), "city": r.get("city"),
                "district": r.get("district"), "lng": r["lng"], "lat": r["lat"],
                "count": cnt, "top_fields": [k for k, _ in fcnt.most_common(3)],
            })
    dist_rows.sort(key=lambda x: -x["count"])

    data = {
        "total": total,
        "fields": [{"name": k, "count": v} for k, v in fields.most_common(20)],
        "months": [{"month": k, "count": v} for k, v in sorted(months.items())],
        "provinces": [{"name": k, "count": v} for k, v in provinces.most_common(20)],
        "satisfaction": dict(satis),
        "topics": [{"word": k, "count": v} for k, v in topics.most_common(30)],
        "districts": dist_rows[:800],
        "risk": risk_rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[out] {OUT}, size={os.path.getsize(OUT)/1024:.0f}KB, districts={len(dist_rows)}, risk={len(risk_rows)}")


if __name__ == "__main__":
    main()
