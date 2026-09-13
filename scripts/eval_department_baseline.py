# -*- coding: utf-8 -*-
"""归口预测 · 检索式基线评测（纯本地 BM25，leave-one-out，零成本）。

任务：给定一条留言，预测责任部门（回复组织）。
方法：在其余样本中检索 top-K 相似案例，按 rank 加权聚合"回复组织"，
      取最高分部门为预测（Top-1），前三个不同部门为 Top-3 候选。
数据：data/labeled_1200.csv（1087 条有 回复组织 标签）
"""
import sys
import io
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from collections import Counter, defaultdict

import pandas as pd
from rank_bm25 import BM25Okapi

from app.rag.hybrid_retriever import tokenize_zh


def main():
    df = pd.read_csv(os.path.join("data", "labeled_1200.csv"), encoding="utf-8-sig", dtype=str).fillna("")
    df["回复组织"] = df["回复组织"].str.strip()
    gold_idx = [i for i, r in df.iterrows() if r["回复组织"]]
    print(f"[gold] {len(gold_idx)}/{len(df)} samples with 回复组织")

    # 语料：留言内容 + LLM 结构化诉求（retrieval 用）
    texts = [r["留言内容"] + "\n" + r["demand"] for _, r in df.iterrows()]
    bm25 = BM25Okapi([tokenize_zh(t) for t in texts])

    # 部门频率分布
    dept_freq = Counter(df.loc[gold_idx, "回复组织"])
    uniq = len(dept_freq)
    singletons = sum(1 for v in dept_freq.values() if v == 1)
    print(f"[dept] unique={uniq}, singleton={singletons} ({singletons/uniq*100:.1f}%)")
    print(f"       Top-1 准确率理论上限（部门 freq>=2 占比）= {sum(1 for v in dept_freq.values() if v>=2)/uniq*100:.1f}% of depts")

    # leave-one-out 检索
    def predict(exclude_idx: int, top_k: int = 20) -> list[str]:
        q = df.loc[exclude_idx, "留言内容"] + " " + df.loc[exclude_idx, "demand"]
        scores = bm25.get_scores(tokenize_zh(q))
        scores[exclude_idx] = -1.0
        top = scores.argsort()[::-1][:top_k]
        dept_score: dict[str, float] = defaultdict(float)
        for rank, doc_idx in enumerate(top):
            dept = df.loc[doc_idx, "回复组织"]
            if dept:
                dept_score[dept] += 1.0 / (rank + 1)
        return [d for d, _ in sorted(dept_score.items(), key=lambda x: -x[1])]

    rows = []
    for i in gold_idx:
        gold = df.loc[i, "回复组织"]
        preds = predict(i)
        rows.append({"i": i, "gold": gold, "pred1": preds[0] if preds else "", "pred3": preds[:3]})

    res = pd.DataFrame(rows)

    def acc_at(res_: pd.DataFrame, k: int) -> float:
        if k == 1:
            return float((res_["pred1"] == res_["gold"]).mean())
        return float(res_.apply(lambda r: r["gold"] in r["pred3"], axis=1).mean())

    overall = len(res)
    freq_ge2 = [i for i in gold_idx if dept_freq[df.loc[i, "回复组织"]] >= 2]
    res_ge2 = res[res["i"].isin(freq_ge2)]

    print("\n================ 评测结果 ================")
    print(f"[整体]      n={overall:4d}  Top-1={acc_at(res,1)*100:5.1f}%  Top-3={acc_at(res,3)*100:5.1f}%")
    print(f"[freq>=2]   n={len(res_ge2):4d}  Top-1={acc_at(res_ge2,1)*100:5.1f}%  Top-3={acc_at(res_ge2,3)*100:5.1f}%")

    # 按留言领域分组
    print("\n[按领域 Top-1]")
    res["领域"] = res["i"].map(lambda i: df.loc[i, "留言领域"])
    for fld, g in res.groupby("领域"):
        if len(g) >= 30:
            print(f"  {fld:6s} n={len(g):4d}  Top-1={acc_at(g,1)*100:5.1f}%  Top-3={acc_at(g,3)*100:5.1f}%")

    # 部门频率区间 vs Top-1
    print("\n[部门出现次数区间 vs Top-1]")
    for lo, hi in [(1, 1), (2, 5), (6, 20), (21, 10**9)]:
        sub = res[res["i"].map(lambda i: lo <= dept_freq[df.loc[i, "回复组织"]] <= hi)]
        if len(sub):
            print(f"  freq [{lo:3d},{hi:5d})  n={len(sub):4d}  Top-1={acc_at(sub,1)*100:5.1f}%")

    # 样例
    print("\n[成功样例]")
    ok = res[res["pred1"] == res["gold"]].head(3)
    for _, r in ok.iterrows():
        print(f"  gold={r['gold']}  pred={r['pred1']} | {df.loc[r['i'],'留言内容'][:40]}")
    print("[失败样例]")
    bad = res[res["pred1"] != res["gold"]].head(3)
    for _, r in bad.iterrows():
        print(f"  gold={r['gold']}  pred={r['pred1']} (top3={r['pred3']}) | {df.loc[r['i'],'留言内容'][:40]}")

    # 保存结果
    res.to_csv(os.path.join("data", "eval_department_baseline.csv"), index=False, encoding="utf-8-sig")
    print("\n[saved] data/eval_department_baseline.csv")


if __name__ == "__main__":
    main()
