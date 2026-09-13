# -*- coding: utf-8 -*-
"""生成可公开的**去标识样例**（≤200 条），放到 data/samples/。

合规依据：第三方原始数据"仅研究用途、不公开传播全量数据"，
仓库只放去标识样例（见 NOTICE）。

脱敏规则：
- 只保留：留言领域、留言类型、留言内容、回复内容（去掉 ID/主题/精确属地/时间/评分等）
- 过滤广告水印行（含"众鲤""数据网"等）
- 按领域均衡抽样，总量默认 200
"""
from __future__ import annotations

import os
import re

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(_ROOT, "data", "labeled_1200.csv")
OUT_DIR = os.path.join(_ROOT, "data", "samples")
OUT = os.path.join(OUT_DIR, "complaints_sample.csv")

WATERMARK = re.compile(r"众鲤|数据网|http|www\.|加微信|QQ群")


def main(limit: int = 200):
    df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str).fillna("")
    keep = df[["留言领域", "留言类型", "留言内容", "回复内容"]].copy()

    # 过滤水印/广告/空行
    mask = (
        keep["留言内容"].str.len().between(8, 600)
        & ~keep.apply(lambda r: bool(WATERMARK.search(str(r["留言内容"]) + str(r["回复内容"]))), axis=1)
    )
    keep = keep[mask]

    # 按领域均衡抽样
    keep["_rank"] = keep.groupby("留言领域").cumcount()
    keep = keep.sort_values(["_rank", "留言领域"]).drop(columns="_rank").head(limit)

    os.makedirs(OUT_DIR, exist_ok=True)
    keep.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"written {len(keep)} rows -> {OUT}")
    print("领域分布:", keep["留言领域"].value_counts().to_dict())


if __name__ == "__main__":
    main()
