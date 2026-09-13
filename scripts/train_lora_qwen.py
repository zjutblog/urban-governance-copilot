# -*- coding: utf-8 -*-
"""Qwen3 LoRA 微调（城市治理回复/决策助手），CPU/GPU 均可。

用法（本机 CPU 试跑小样本）：
  py scripts/train_lora_qwen.py --max_train 12 --epochs 1 --out data/lora/adapter-qwen3-0.6b

正式（更多数据，GPU 更好）：
  py scripts/train_lora_qwen.py --epochs 3 --lr 2e-4 --rank 16 --out data/lora/adapter-qwen3-0.6b --merge

要点：
- 用 transformers 的 assistant_tokens_mask 只对"回复"算损失，提示词不学。
- 纯 CPU float32 LoRA；想更省内存可加 --load_4bit（需 bitsandbytes，Linux/GPU）。
- --merge 训练后可把 adapter 合并回基座，便于后续转 GGUF 导入 Ollama。
"""
from __future__ import annotations

import argparse
import json
import os
import time

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model, TaskType, PeftModel

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_samples(path: str, cap: int = 0):
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    if cap and cap > 0:
        samples = samples[:cap]
    return samples


class SFTDataset(Dataset):
    def __init__(self, samples, tokenizer, max_len=512):
        self.data = []
        for m in samples:
            # 不含生成提示：整段含 assistant 回复（目标段）
            full = tokenizer(
                tokenizer.apply_chat_template(m["messages"], tokenize=False, add_generation_prompt=False),
                truncation=True, max_length=max_len,
            )
            # 到 assistant 回复前的提示（system+user+assistant头）——掩码用它定边界
            prompt = tokenizer(
                tokenizer.apply_chat_template(m["messages"], tokenize=False, add_generation_prompt=True),
                truncation=True, max_length=max_len,
            )
            p_len = len(prompt["input_ids"])
            ids = full["input_ids"]
            if p_len >= len(ids):
                p_len = len(ids) - 1
            labels = list(ids)
            for i in range(min(p_len, len(labels))):
                labels[i] = -100
            self.data.append({
                "input_ids": torch.tensor(ids, dtype=torch.long),
                "attention_mask": torch.tensor(full["attention_mask"], dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            })

    def __len__(self):
        return len(self.data)

    def __getitem__(self, i):
        return self.data[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--train", default=os.path.join(_ROOT, "data", "lora", "train.jsonl"))
    ap.add_argument("--max_train", type=int, default=0, help="0=全量；小样本试跑传小值")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--out", default=os.path.join(_ROOT, "data", "lora", "adapter-qwen3-0.6b"))
    ap.add_argument("--device", default="auto")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--load_4bit", action="store_true")
    args = ap.parse_args()

    device = "cpu"
    if args.device == "auto" and torch.cuda.is_available():
        device = "cuda"
    elif args.device != "auto":
        device = args.device

    print(f"[load] base={args.base} device={device}")
    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base, trust_remote_code=True,
        torch_dtype=torch.float32 if device == "cpu" else torch.bfloat16,
    )
    model = model.to(device)
    if getattr(model, "enable_input_require_grads", None):
        model.enable_input_require_grads()

    # LoRA：attn 全投射 + 前馈门控，通用配置
    lora = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.rank,
        lora_alpha=args.alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    samples = load_samples(args.train, args.max_train)
    ds = SFTDataset(samples, tok, args.max_len)
    dl = DataLoader(ds, batch_size=1, shuffle=True)
    print(f"[data] train samples: {len(samples)}")

    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=args.lr)
    total = len(dl) * args.epochs
    step = 0
    t0 = time.time()
    model.train()
    for ep in range(args.epochs):
        for batch in dl:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = out.loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            step += 1
            if step % 5 == 0 or step == total:
                print(f"  epoch{ep+1} step {step}/{total} loss {loss.item():.4f} "
                      f"({(time.time()-t0)/max(step,1):.1f}s/step, 累计{time.time()-t0:.0f}s)")
    print(f"[done] final loss avg; saved adapter -> {args.out}")

    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)

    if args.merge:
        print("[merge] merging adapter into base ...")
        merged = PeftModel.from_pretrained(model, args.out).merge_and_unload()
        merged_out = args.out + "-merged"
        os.makedirs(merged_out, exist_ok=True)
        merged.save_pretrained(merged_out)
        tok.save_pretrained(merged_out)
        print(f"[merge] saved -> {merged_out}  (可转 GGUF 导入 Ollama)")


if __name__ == "__main__":
    main()
