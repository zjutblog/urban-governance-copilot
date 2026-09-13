# -*- coding: utf-8 -*-
"""BERT 职能分类器训练（本地 CPU / Kaggle GPU 通用）。

任务：留言 → 职能类别（归口预测第二级）。标签 = 回复组织 的职能映射。
数据：data/labeled_1200.csv（1087 条有回复组织）
模型：bert-base-chinese（本地 D:/models/bert-base-chinese-ner，Kaggle 上换官方名）
训练：StratifiedKFold 交叉验证，手动训练循环（无 Trainer 版本依赖）

用法（本地）：
  py scripts/train_function_classifier.py --folds 1 --epochs 4
  py scripts/train_function_classifier.py --folds 5 --epochs 4   # 全量 5 折

用法（Kaggle，改 --data/--model 指向挂载路径）：
  !python train_function_classifier.py --data /kaggle/input/xxx/labeled_1200.csv \\
      --model /kaggle/input/bert-base-chinese --folds 5 --epochs 4 --out /kaggle/working
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from dept_rules import map_department
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import BertForSequenceClassification, BertTokenizerFast


class TextDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.enc = tokenizer(
            texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt"
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        return {k: v[i] for k, v in self.enc.items()} | {"labels": self.labels[i]}


def train_fold(model, tokenizer, train_ds, val_ds, epochs, lr, out_dir, device, class_weight=None):
    loader = DataLoader(train_ds, batch_size=16, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    best_f1, best_state = -1.0, None
    for ep in range(epochs):
        model.train()
        t0 = time.time()
        tot = 0.0
        for batch in tqdm(loader, desc=f"epoch {ep+1}/{epochs}", leave=False):
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = F.cross_entropy(out.logits, batch["labels"], weight=class_weight)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            tot += loss.item()
        # 验证
        val_acc, val_f1, val_top3 = evaluate(model, val_ds, device)
        print(f"  [ep{ep+1}] loss={tot/len(loader):.4f} val_acc={val_acc:.4f} val_macroF1={val_f1:.4f} ({time.time()-t0:.0f}s)")
        if val_f1 > best_f1:
            best_f1 = val_f1
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    if best_state is not None:
        model.load_state_dict(best_state)
        model.save_pretrained(out_dir)
        tokenizer.save_pretrained(out_dir)
    return best_f1


@torch.no_grad()
def evaluate(model, ds, device):
    model.eval()
    loader = DataLoader(ds, batch_size=32)
    all_logits, all_label = [], []
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        all_logits.append(model(**batch).logits.cpu().numpy())
        all_label.append(batch["labels"].cpu().numpy())
    logits = np.concatenate(all_logits)
    label = np.concatenate(all_label)
    pred = logits.argmax(-1)
    acc = accuracy_score(label, pred)
    f1 = f1_score(label, pred, average="macro", zero_division=0)
    top3 = float(np.mean([label[i] in np.argsort(logits[i])[-3:] for i in range(len(label))]))
    return acc, f1, top3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join("data", "labeled_1200.csv"))
    ap.add_argument("--model", default=r"D:\models\bert-base-chinese-ner")
    ap.add_argument("--out", default=os.path.join("data", "models", "function_classifier"))
    ap.add_argument("--folds", type=int, default=1, help="跑前 N 折（1=快速验证，5=全量）")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max_len", type=int, default=128)
    ap.add_argument("--min_class", type=int, default=10, help="样本数低于此值的类并入'其他'")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device} | torch {torch.__version__} | cpu cores {os.cpu_count()}")

    df = pd.read_csv(args.data, encoding="utf-8-sig", dtype=str).fillna("")
    df["回复组织"] = df["回复组织"].str.strip()
    df = df[df["回复组织"] != ""].copy()
    df["职能"] = df["回复组织"].map(map_department)

    # 合并小类到"其他"
    vc = df["职能"].value_counts()
    small = set(vc[vc < args.min_class].index)
    df.loc[df["职能"].isin(small), "职能"] = "其他"
    classes = sorted(df["职能"].unique())
    cls2id = {c: i for i, c in enumerate(classes)}
    print(f"[data] {len(df)} samples, {len(classes)} classes: {classes}")
    print(f"[merged to 其他] {sorted(small)}")

    texts = (df["留言内容"] + "\n" + df["demand"]).tolist()
    labels = [cls2id[c] for c in df["职能"]]

    tokenizer = BertTokenizerFast.from_pretrained(args.model)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    fold_scores = []
    for fold, (tr_idx, va_idx) in enumerate(skf.split(texts, labels)):
        if fold >= args.folds:
            break
        print(f"\n===== fold {fold+1} =====")
        tr_texts = [texts[i] for i in tr_idx]
        va_texts = [texts[i] for i in va_idx]
        tr_labels = [labels[i] for i in tr_idx]
        va_labels = [labels[i] for i in va_idx]

        model = BertForSequenceClassification.from_pretrained(
            args.model,
            num_labels=len(classes),
            ignore_mismatched_sizes=True,  # 本地模型是 NER 版（73 标签），分类头重新初始化
        ).to(device)
        # 类别加权：缓解极度不平衡（小类样本少，权重高）
        cw = compute_class_weight("balanced", classes=np.arange(len(classes)), y=np.array(labels))
        cw = torch.tensor(cw, dtype=torch.float32).to(device)
        train_ds = TextDataset(tr_texts, tr_labels, tokenizer, args.max_len)
        val_ds = TextDataset(va_texts, va_labels, tokenizer, args.max_len)
        fold_dir = os.path.join(args.out, f"fold{fold+1}")
        os.makedirs(fold_dir, exist_ok=True)

        best = train_fold(model, tokenizer, train_ds, val_ds, args.epochs, args.lr, fold_dir, device, cw)
        acc, f1, top3 = evaluate(model, val_ds, device)
        print(f"  [fold{fold+1}] best_val_macroF1={best:.4f} | final acc={acc:.4f} macroF1={f1:.4f}")
        fold_scores.append({"fold": fold + 1, "acc": acc, "macro_f1": f1})

        # 存该折预测明细
        model.eval()
        loader = DataLoader(val_ds, batch_size=32)
        preds = []
        with torch.no_grad():
            for batch in loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                preds.extend(model(**batch).logits.argmax(-1).cpu().numpy().tolist())
        pd.DataFrame({
            "original_id": df.iloc[va_idx]["original_id"].values,
            "gold": [classes[i] for i in va_labels],
            "pred": [classes[p] for p in preds],
        }).to_csv(os.path.join(args.out, f"pred_fold{fold+1}.csv"), index=False, encoding="utf-8-sig")
        del model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

    if fold_scores:
        s = pd.DataFrame(fold_scores)
        print("\n========== 汇总 ==========")
        print(s.to_string(index=False))
        print(f"mean acc={s['acc'].mean():.4f} | mean macroF1={s['macro_f1'].mean():.4f}")
        s.to_csv(os.path.join(args.out, "summary.csv"), index=False, encoding="utf-8-sig")
        print(f"[saved] {args.out}")


if __name__ == "__main__":
    main()
