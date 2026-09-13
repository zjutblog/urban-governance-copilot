# -*- coding: utf-8 -*-
"""构建 Qwen3 LoRA 微调数据集（免费：用官方回复当监督目标）。

目标：把 Qwen3-0.6B 训练成"城市治理回复/决策建议"助手——
输入群众留言(+领域) → 输出面向市民的官方回复（沿用人民网官方回复风格，
学"程序性、可兑现、不编造事实"的政务话术）。

输出 data/lora/train.jsonl / eval.jsonl（chat messages 格式，供 transformers chat template 使用）。
"""
from __future__ import annotations

import json
import os
import random

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(_ROOT, "data", "labeled_1200.csv")
OUT_DIR = os.path.join(_ROOT, "data", "lora")

SYSTEM = (
    "你是「城市治理 Copilot」的政务留言处理助手。请依据群众留言生成一条面向市民的官方回复建议："
    "①话语自然、像真实政府部门回复；②只写程序性、可兑现的表述（如'已转交相关部门核实处理''将跟进督办并反馈'），"
    "禁止编造'已拆除/已处罚/已安排'等未发生事实；③一句话到两三句即可，不冗余。"
)


def clean(text: str) -> str:
    return (text or "").replace("\r", "").strip()


def main():
    df = pd.read_csv(CSV, encoding="utf-8-sig", dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        content = clean(r.get("留言内容", ""))
        reply = clean(r.get("回复内容", ""))
        if len(content) < 8 or len(reply) < 20:
            continue
        rows.append((content, reply, str(r.get("留言领域", "") or "")))

    # 按领域分组，eval 从各组抽 1 条（保覆盖），其余进 train
    random.seed(42)
    by_field: dict[str, list] = {}
    for c, rep, f in rows:
        by_field.setdefault(f, []).append((c, rep, f))
    train, eval_ = [], []
    for f, items in by_field.items():
        random.shuffle(items)
        eval_.append(items[0])
        train.extend(items[1:])
    random.shuffle(train)

    def make(content: str, reply: str) -> dict:
        return {"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content},
            {"role": "assistant", "content": reply},
        ]}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "train.jsonl"), "w", encoding="utf-8") as f:
        for c, rep, _ in train:
            f.write(json.dumps(make(c, rep), ensure_ascii=False) + "\n")
    with open(os.path.join(OUT_DIR, "eval.jsonl"), "w", encoding="utf-8") as f:
        for c, rep, _ in eval_:
            f.write(json.dumps(make(c, rep), ensure_ascii=False) + "\n")
    print(f"train: {len(train)}  eval: {len(eval_)}  (total usable {len(rows)})")
    print(f"saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
