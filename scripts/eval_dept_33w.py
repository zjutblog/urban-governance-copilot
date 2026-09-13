# -*- coding: utf-8 -*-
"""33 万全量 · 职能分类基线（免费标签，CPU 可跑）。

目的：锚定"归口 acc 提到 85%"的现实性。
- 标签：33 万 CSV 的"回复组织" → dept_rules 职能映射（免费，无需 LLM）
- 特征：中文 char n-gram TF-IDF + LogisticRegression（sklearn，CPU 秒级~分钟级）
- 评估：Top-1 / Top-3 准确率（10 类职能 + 按领域分组）
"""
import sys
import csv
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from collections import Counter

import numpy as np
import pandas as pd
import lightgbm as lgb
from dept_rules import map_department
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split

import builtins
# 管道重定向下也即时输出，避免缓冲丢失
print = lambda *a, **k: builtins.print(*a, flush=True, **k)

CSV = r"D:\人民网留言板2025.csv"


def log(msg):
    print(msg)


def main():
    log("[load] reading CSV (GB18030, stream)...")
    rows = []
    with open(CSV, "r", encoding="gb18030", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        i_text = idx["留言内容"]
        i_dept = idx["回复组织"]
        i_field = idx["留言领域"]
        for row in reader:
            dept = row[i_dept].strip() if i_dept < len(row) else ""
            if not dept:
                continue
            text = row[i_text].strip() if i_text < len(row) else ""
            field = row[i_field].strip() if i_field < len(row) else ""
            if text and dept:
                rows.append({"text": text, "dept": dept, "field": field})
    print(f"[load] {len(rows)} rows with 回复组织")

    df = pd.DataFrame(rows)
    df["func"] = df["dept"].map(map_department)

    # 类别分布
    vc = df["func"].value_counts()
    print(f"[func] 映射后类别数: {len(vc)}")
    print(vc.head(12).to_string())

    # 收敛到 10 类：< 某阈值的并入"其他"
    MIN = 8000
    small = set(vc[vc < MIN].index)
    df.loc[df["func"].isin(small), "func"] = "其他"
    classes = sorted(df["func"].unique())
    print(f"\n[min_class={MIN}] 最终 {len(classes)} 类: {classes}")
    print(df["func"].value_counts().to_string())

    # 抽样（控制 CPU 时间）
    SAMPLE = 60000
    if len(df) > SAMPLE:
        df = df.sample(n=SAMPLE, random_state=42)
    texts = (df["text"] + "\n" + df["func"]).tolist()
    labels = df["func"].tolist()

    # 特征 + 模型
    print(f"\n[train] n={len(df)}, build TF-IDF (char 2-3 gram)...")
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=60000, sublinear_tf=True)
    X = vec.fit_transform(df["text"])
    y = df["func"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print("[train] LightGBM...")
    clf = lgb.LGBMClassifier(n_estimators=120, learning_rate=0.2, num_leaves=31, n_jobs=4, min_child_samples=30, verbose=-1)
    clf.fit(X_tr, y_tr)

    pred = clf.predict(X_te)
    acc = (pred == y_te).mean()
    # Top-3
    probs = clf.predict_proba(X_te)
    top3 = np.array([y_te.iloc[i] in set(clf.classes_[np.argsort(probs[i])[-3:]]) for i in range(len(y_te))]).mean()

    print("\n================ 33 万职能分类基线 ================")
    print(f"n_test={len(y_te)}  类别数={len(classes)}")
    print(f"Top-1 acc = {acc*100:.1f}%")
    print(f"Top-3 acc = {top3*100:.1f}%")
    print("\n[按职能 Top-1]")
    for c in classes:
        mask = y_te == c
        if mask.sum() >= 100:
            print(f"  {c:8s} n={mask.sum():6d} acc={(pred[mask]==y_te[mask]).mean()*100:5.1f}%")


if __name__ == "__main__":
    main()
