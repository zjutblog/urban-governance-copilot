# Kaggle 上微调 Qwen3（LoRA）跑"城市治理回复助手"教程

> 目标：用你们免费的官方回复数据，在 **Kaggle 免费 GPU** 上把 `Qwen/Qwen3-0.6B`（可换 1.5B/3B）LoRA 微调成政务回复助手，产出可导入 Ollama 的模型。
> 配套 notebook：`notebooks/kaggle_qwen3_lora_ugov.ipynb`（可直接导入）。

---

## 0. 你需要准备的东西
1. 一个 Kaggle 账号（免费）。
2. 本机已经生成好的训练数据（**很小**，直接拖进去即可）：
   - `data/lora/train.jsonl`（1131 条）
   - `data/lora/eval.jsonl`（12 条）
   想换更大/自己标的也可以，格式统一为每行 `{"messages":[{role,content}...]}`。
   （可选）也可只传 `data/labeled_1200.csv`，notebook 里现造，但多一步。）

---

## 1. 新建并开 GPU
1. 打开 https://www.kaggle.com → 右上角 **New Notebook**（或 Code）。
2. 右侧 **Settings** 面板：
   - **Accelerator = GPU**（免费是 P100 16GB / T4）。
   - **Internet = On**（默认开，用于下基座 + 装包）。
   - 语言保持 **Python**。

## 2. 传数据
左上角 **+ Add Input → Upload Dataset**：
- 新建一个小 dataset，把 `train.jsonl`、`eval.jsonl` 上传。
- dataset 名随便，例如 `ugov-lora`。记下挂载路径，一般形如：
  `/kaggle/input/ugov-lora/train.jsonl`（notebook 会自动 `glob` 找到，不用手填也能跑）。

## 3. 全选代码跑一遍
直接把 `notebooks/kaggle_qwen3_lora_ugov.ipynb` **导入**（File → Import Notebook → Upload .ipynb），或新建 notebook 后把下面各段复制进去，**依次 Run All**。

---

## 4. 核心代码（与 notebook 一致）

### (1) 装依赖（首次约 1 分钟）
```python
!pip install -q "transformers>=4.45" peft accelerate datasets bitsandbytes
```

### (2) 配置与加载
```python
import glob, json, os, torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType

BASE_MODEL = "Qwen/Qwen3-0.6B"      # 显存够可换 Qwen/Qwen3-1.5B、Qwen3-3B
OUT_DIR    = "/kaggle/working/ugov-qwen"

# 自动在 /kaggle/input 下找 train/eval
train_file = glob.glob("/kaggle/input/*/train.jsonl")[0]
eval_file  = glob.glob("/kaggle/input/*/eval.jsonl")[0]
print("train:", train_file)
```

### (3) 读数据 + 只用"回复"算损失的 Dataset
```python
from torch.utils.data import Dataset

def load(path):
    out=[]
    for line in open(path, encoding="utf-8"):
        line=line.strip()
        if line: out.append(json.loads(line))
    return out

class SFT(Dataset):
    def __init__(self, samples, tok, max_len=512):
        self.data=[]
        for m in samples:
            full = tok(tok.apply_chat_template(m["messages"], tokenize=False, add_generation_prompt=False),
                       truncation=True, max_length=max_len)
            prom = tok(tok.apply_chat_template(m["messages"], tokenize=False, add_generation_prompt=True),
                       truncation=True, max_length=max_len)
            plen = len(prom["input_ids"])
            ids  = full["input_ids"]
            if plen >= len(ids): plen = len(ids)-1
            labels=[ids[i] if i>=plen else -100 for i in range(len(ids))]
            self.data.append({"input_ids":ids,"attention_mask":full["attention_mask"],"labels":labels})
    def __len__(self): return len(self.data)
    def __getitem__(self,i):
        d=self.data[i]
        return {k:torch.tensor(v) for k,v in d.items()}

tok = AutoTokenizer.from_pretrained(BASE_MODEL)
if tok.pad_token is None: tok.pad_token = tok.eos_token
ds = SFT(load(train_file), tok)
print("samples:", len(ds))
```

### (4) 加载基座 + 挂 LoRA
```python
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="auto")
model.enable_input_require_grads()
lora = LoraConfig(task_type=TaskType.CAUSAL_LM, r=16, lora_alpha=32, lora_dropout=0.05,
                  target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"])
model = get_peft_model(model, lora)
model.print_trainable_parameters()
```

### (5) 训练（16GB 显存可 fp16；0.6B 很快）
```python
args = TrainingArguments(
    output_dir=OUT_DIR,
    per_device_train_batch_size=2, gradient_accumulation_steps=4,
    num_train_epochs=3, learning_rate=2e-4, lr_scheduler_type="cosine",
    fp16=True, logging_steps=20, save_strategy="epoch",
    report_to="none", push_to_hub=False)
coll = DataCollatorForSeq2Seq(tokenizer=tok, model=model, padding=True, label_pad_token_id=-100)
trainer = Trainer(model=model, args=args, train_dataset=ds, data_collator=coll)
trainer.train()
```

### (6) 合并 adapter → 完整模型（给 Ollama 用）
```python
adapter_dir = OUT_DIR + "/adapter"
model.save_pretrained(adapter_dir); tok.save_pretrained(adapter_dir)
print("adapter saved:", adapter_dir)

from peft import PeftModel
merged = PeftModel.from_pretrained(model, adapter_dir).merge_and_unload()
merged_dir = OUT_DIR + "/merged"
merged.save_pretrained(merged_dir, safe_serialization=True); tok.save_pretrained(merged_dir)
print("merged saved:", merged_dir)
```

### (7) 打包下载
```python
!cd /kaggle/working/ugov-qwen && tar -czf /kaggle/working/qwen3-ugov-merged.tar.gz merged
print("下载文件: /kaggle/working/qwen3-ugov-merged.tar.gz")
```
右上角 **Output** 面板 → 下载压缩包。

---

## 5. 下载后如何接回项目
拿到 `merged/`（HF 结构：config.json / model.safetensors / tokenizer*）。

### 方式 A：先本机验证（可选）
```
py -c "from transformers import AutoModelForCausalLM, AutoTokenizer; m=AutoModelForCausalLM.from_pretrained('merged'); t=AutoTokenizer.from_pretrained('merged'); print(t.apply_chat_template([{'role':'user','content':'小区下水道堵了，谁来管？'}], tokenize=False))"
```

### 方式 B：转 GGUF 导入 Ollama（推荐，接进 .env 直接跑）
需要 `llama.cpp`（克隆或 pip 装 `llama-cpp-python` 只够跑不转；**转 GGUF 用 llama.cpp 的 `convert_hf_to_gguf.py`**）：
```
git clone https://github.com/ggml-org/llama.cpp
python llama.cpp/convert_hf_to_gguf.py merged -o qwen3-ugov.gguf
# 量化（可选）
python llama.cpp/quantize.py qwen3-ugov.gguf qwen3-ugov-Q4_K_M.gguf q4_k_m
# 导入 ollama
ollama create qwen3-ugov -f - <<'EOF'
FROM ./qwen3-ugov-Q4_K_M.gguf
TEMPLATE "{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"
PARAMETER temperature 0.3
EOF
```
然后项目 `.env`：
```
LLM_MODE=local
LOCAL_MODEL=qwen3-ugov
```

> 提示：转 GGUF 也可用在线/其它工具；若嫌麻烦，也可在 GPU 机器上用 vLLM 直接 serve `merged`，把 `.env` 的 `LOCAL_BASE_URL` 指过去。

---

## 6. 常见问题
- **OOM（显存爆）**：P100 16G 训 0.6B/1.5B 没问题；3B 若爆就 `per_device_train_batch_size=1` + `gradient_accumulation_steps=8`，或换更小。
- **下载基座慢/失败**：Kaggle 有外网能直连 HF；若偶尔连不上可临时 `import os; os.environ["HF_ENDPOINT"]="https://hf-mirror.com"`。
- **想要更多效果**：加 `--数据` 清洗（去掉超长/模板回复）、扩到更大基座、多训几轮看 eval loss；本项目基线效果有限属正常（官方回复风格偏模板）。
- **只训"回复"**：数据集已屏蔽提示词（只学 assistant 段），防止模型把 system/user 也背下来。
