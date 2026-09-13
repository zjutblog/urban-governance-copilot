# -*- coding: utf-8 -*-
"""归口预测 · 职能粒度检索式基线（修正版）。

上版结论：机构名粒度 854 类、84.8% 单例 → 小样本下数学上不可学。
本版：把"回复组织"粗映射到 ~20 个职能类（关键词规则），
再跑 leave-one-out 检索式 baseline，验证两级归口的第一级（职能）可预测性。
"""
import sys
import io
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from collections import Counter, defaultdict

import pandas as pd
from dept_rules import map_department
from rank_bm25 import BM25Okapi

from app.rag.hybrid_retriever import tokenize_zh


def main():
    df = pd.read_csv(os.path.join("data", "labeled_1200.csv"), encoding="utf-8-sig", dtype=str).fillna("")
    df["回复组织"] = df["回复组织"].str.strip()
    df["职能"] = df["回复组织"].map(map_department)

    gold_idx = [i for i, r in df.iterrows() if r["回复组织"]]
    print(f"[gold] {len(gold_idx)} samples")

    # 映射覆盖率
    dept_set = set(df.loc[gold_idx, "回复组织"])
    mapped = sum(1 for d in dept_set if map_department(d) != "其他")
    print(f"[mapping] {len(dept_set)} depts -> {mapped} mapped ({mapped/len(dept_set)*100:.1f}%), 未映射: {len(dept_set)-mapped}")
    fc = Counter(df.loc[gold_idx, "职能"])
    print("[职能分布]")
    for k, v in fc.most_common():
        print(f"  {k:8s} {v}")

    # 语料
    texts = [r["留言内容"] + "\n" + r["demand"] for _, r in df.iterrows()]
    bm25 = BM25Okapi([tokenize_zh(t) for t in texts])

    def predict(exclude_idx: int, top_k: int = 20) -> list[str]:
        q = df.loc[exclude_idx, "留言内容"] + " " + df.loc[exclude_idx, "demand"]
        scores = bm25.get_scores(tokenize_zh(q))
        scores[exclude_idx] = -1.0
        top = scores.argsort()[::-1][:top_k]
        f_score: dict[str, float] = defaultdict(float)
        for rank, doc_idx in enumerate(top):
            f = df.loc[doc_idx, "职能"]
            if f:
                f_score[f] += 1.0 / (rank + 1)
        return [f for f, _ in sorted(f_score.items(), key=lambda x: -x[1])]

    rows = []
    for i in gold_idx:
        gold = df.loc[i, "职能"]
        preds = predict(i)
        rows.append({"i": i, "gold": gold, "pred1": preds[0] if preds else "", "pred3": preds[:3]})
    res = pd.DataFrame(rows)

    def acc_at(r_: pd.DataFrame, k: int) -> float:
        if k == 1:
            return float((r_["pred1"] == r_["gold"]).mean())
        return float(r_.apply(lambda r: r["gold"] in r["pred3"], axis=1).mean())

    print("\n================ 职能粒度评测 ================")
    print(f"[整体]    n={len(res):4d}  Top-1={acc_at(res,1)*100:5.1f}%  Top-3={acc_at(res,3)*100:5.1f}%")

    res["领域"] = res["i"].map(lambda i: df.loc[i, "留言领域"])
    print("[按留言领域 Top-1]")
    for fld, g in res.groupby("领域"):
        if len(g) >= 30:
            print(f"  {fld:6s} n={len(g):4d}  Top-1={acc_at(g,1)*100:5.1f}%  Top-3={acc_at(g,3)*100:5.1f}%")

    print("\n[成功样例]")
    for _, r in res[res["pred1"] == res["gold"]].head(3).iterrows():
        print(f"  gold={r['gold']}  pred={r['pred1']} | {df.loc[r['i'],'留言内容'][:40]}")
    print("[失败样例]")
    for _, r in res[res["pred1"] != res["gold"]].head(3).iterrows():
        print(f"  gold={r['gold']}  pred={r['pred1']} (top3={r['pred3']}) | {df.loc[r['i'],'留言内容'][:40]}")

    res.to_csv(os.path.join("data", "eval_department_function_baseline.csv"), index=False, encoding="utf-8-sig")
    print("\n[saved] data/eval_department_function_baseline.csv")


if __name__ == "__main__":
    main()
