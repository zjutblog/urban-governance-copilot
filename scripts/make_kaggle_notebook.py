# -*- coding: utf-8 -*-
"""生成 Kaggle 版训练 notebook（GPU 全量 5 折）。

用法：py scripts/make_kaggle_notebook.py
输出：notebooks/kaggle_function_classifier.ipynb
"""
import json
import os
import re

OUT = os.path.join("notebooks", "kaggle_function_classifier.ipynb")

# 职能映射：从 dept_rules.py 动态读取（单一来源）
_rules_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dept_rules.py")
_rules_src = open(_rules_file, encoding="utf-8").read()
_m = re.search(r"_RULES = \[.*?\]\n", _rules_src, re.S)
assert _m, "cannot find _RULES in dept_rules.py"
_RULES_SRC = (
    _m.group(0)
    + "\ndef map_department(name):\n    for kw, cls in _RULES:\n        if kw in name:\n            return cls\n    return \"其他\"\n"
)

CORE_SRC = """
# ==== 自动探测挂载的数据集（无需手改路径）====
# 若报错，请在右侧 "Add Input" 里搜索你上传的 dataset 并挂载，然后重跑本 cell
import glob
_csvs = sorted(glob.glob("/kaggle/input/**/*.csv", recursive=True))
print("挂载到的 CSV 文件:", _csvs)
assert _csvs, "未找到 CSV！请点击右侧 Add Input 挂载 labeled_1200.csv 所在的数据集"
DATA = next((p for p in _csvs if "labeled_1200" in p), _csvs[0])
print("使用数据:", DATA)

MODEL_NAME = "bert-base-chinese"   # Kaggle 直接从 HF 下载；网络慢可换 hf-mirror
EPOCHS = 8
FOLDS = 5
LR = 2e-5
MAX_LEN = 128
MIN_CLASS = 10

class TextDataset(Dataset):
    def __init__(self, texts, labels, tokenizer):
        self.enc = tokenizer(texts, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt")
        self.labels = torch.tensor(labels, dtype=torch.long)
    def __len__(self):
        return len(self.labels)
    def __getitem__(self, i):
        return {k: v[i] for k, v in self.enc.items()} | {"labels": self.labels[i]}

@torch.no_grad()
def evaluate(model, ds, device):
    model.eval()
    loader = DataLoader(ds, batch_size=64)
    pred, label = [], []
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        logits = model(**batch).logits
        pred.extend(logits.argmax(-1).cpu().numpy().tolist())
        label.extend(batch["labels"].cpu().numpy().tolist())
    return accuracy_score(label, pred), f1_score(label, pred, average="macro", zero_division=0)

def train_fold(model, tokenizer, tr_ds, va_ds, device, class_weight):
    loader = DataLoader(tr_ds, batch_size=32, shuffle=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    best_f1, best_state = -1.0, None
    for ep in range(EPOCHS):
        model.train()
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = torch.nn.functional.cross_entropy(out.logits, batch["labels"], weight=class_weight)
            opt.zero_grad(); loss.backward(); opt.step()
        acc, f1 = evaluate(model, va_ds, device)
        print(f"  ep{ep+1} val_acc={acc:.4f} macroF1={f1:.4f}")
        if f1 > best_f1:
            best_f1, best_state = f1, {k: v.clone() for k, v in model.state_dict().items()}
    if best_state:
        model.load_state_dict(best_state)
    return best_f1

# 数据准备
df = pd.read_csv(DATA, encoding="utf-8-sig", dtype=str).fillna("")
df["回复组织"] = df["回复组织"].str.strip()
df = df[df["回复组织"] != ""].copy()
df["职能"] = df["回复组织"].map(map_department)
vc = df["职能"].value_counts()
small = set(vc[vc < MIN_CLASS].index)
df.loc[df["职能"].isin(small), "职能"] = "其他"
classes = sorted(df["职能"].unique())
cls2id = {c: i for i, c in enumerate(classes)}
print(f"samples={len(df)} classes={len(classes)}")
print(classes)

texts = (df["留言内容"] + "\\n" + df["demand"]).tolist()
labels = [cls2id[c] for c in df["职能"]]
tokenizer = BertTokenizerFast.from_pretrained(MODEL_NAME)
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

results = []
for fold, (tr, va) in enumerate(skf.split(texts, labels)):
    print(f"===== fold {fold+1} =====")
    model = BertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=len(classes)).to(device)
    cw = torch.tensor([len(labels) / (len(classes) * labels.count(c)) for c in range(len(classes))], dtype=torch.float32).to(device)
    tr_ds = TextDataset([texts[i] for i in tr], [labels[i] for i in tr], tokenizer)
    va_ds = TextDataset([texts[i] for i in va], [labels[i] for i in va], tokenizer)
    best = train_fold(model, tokenizer, tr_ds, va_ds, device, cw)
    acc, f1 = evaluate(model, va_ds, device)
    results.append({"fold": fold + 1, "acc": acc, "macro_f1": f1})
    print(f"  fold{fold+1} final acc={acc:.4f} macroF1={f1:.4f} (best={best:.4f})")

print("\\n===== 汇总 =====")
for r in results:
    print(r)
print(f"mean acc={sum(r['acc'] for r in results)/len(results):.4f}  mean macroF1={sum(r['macro_f1'] for r in results)/len(results):.4f}")
"""

cells = [
    ("markdown", "# BERT 职能分类器（Kaggle GPU 版）\n\n归口预测第二级：留言 → 职能类别。5 折交叉验证。\n\n**使用前**：把 `data/labeled_1200.csv` 上传为 Kaggle Dataset（例如名为 `liuyanban1200`），然后修改下方 `DATA` 路径。"),
    ("code", "!pip install -q transformers scikit-learn 2>/dev/null || true\nimport os, time\nimport numpy as np, pandas as pd\nimport torch\nfrom sklearn.metrics import accuracy_score, f1_score\nfrom sklearn.model_selection import StratifiedKFold\nfrom transformers import BertForSequenceClassification, BertTokenizerFast\nfrom torch.utils.data import Dataset, DataLoader\n\ndevice = torch.device(\"cuda\" if torch.cuda.is_available() else \"cpu\")\nprint(\"device:\", device, \"| torch\", torch.__version__)"),
    ("code", _RULES_SRC),
    ("code", CORE_SRC),
]

nb = {
    "cells": [
        {
            "cell_type": ctype,
            "metadata": {},
            "source": src.splitlines(keepends=True),
            "execution_count": None,
            "outputs": [] if ctype == "code" else [],
        }
        for ctype, src in cells
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("written:", OUT)
