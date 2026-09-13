# 本地 Qwen 部署 + LoRA 微调指南

> 把「大模型部分」从云端 DeepSeek 换成**本地 Qwen**，并可 LoRA 微调成领域助手。保留 DeepSeek 作为**双线可切**的云端后端。

## 1. 环境结论（实测）
- **无 NVIDIA GPU**；8 核 CPU，可用内存约 8.6GB → 本地训练只能 CPU 慢慢跑。
- Ollama 已装且运行，已拉取 `qwen3:0.6b`(522MB) / `qwen3:8b`(5.2GB)。
- `qwen3:0.6b` 一次小调用约 **16s**（CPU 正常水平）；8b 更慢。
- conda env `urban_agent` 已补装：`peft 0.20`、`accelerate 1.14`（torch 为 CPU 版、transformers 5.15，兼容 Qwen3）。

## 2. 让应用跑在本地 Qwen（双线可切）
改 `.env`：
```
LLM_MODE=local        # cloud=DeepSeek | local=Ollama Qwen
LOCAL_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL=qwen3:0.6b   # 或微调后导入 Ollama 的 tag，如 qwen3-ugov
```
- `LLM_MODE=cloud`（默认）= 云端 DeepSeek（不变）；`LLM_MODE=local` = 本地 Qwen。
- 代码：`app/llm/client.py::resolve_llm_config` 已支持该双线；前端传的 api_key 在 cloud 模式仍可用。
- ⚠️ 本地 0.6b 跑完整管线（planner+analyze+决策×3 门控）会很慢、schema 输出未必稳；建议只在**部分环节**用本地（后续可把 decision 单独指到本地微调模型）。

## 3. LoRA 微调流程
**第 1 步：造数据（免费，官方回复当目标）**
```
py scripts/build_lora_dataset.py      # -> data/lora/{train,eval}.jsonl
```
**第 2 步：训练**
```
# 网络提示：官方 huggingface.co 本机被墙 → 用国内镜像（已实测可达）
set HF_ENDPOINT=https://hf-mirror.com

# 本机 CPU 小样本试跑：
py scripts/train_lora_qwen.py --max_train 12 --epochs 1 --max_len 256 --out data/lora/adapter-qwen3-0.6b
# 云端 GPU 正式跑（推荐，数据多、可多轮）：
py scripts/train_lora_qwen.py --epochs 3 --lr 2e-4 --rank 16 --merge --out data/lora/adapter-qwen3-0.6b
```
- 用 transformers `return_assistant_tokens_mask` **只学回复、屏蔽提示词**；LoRA 全量投到 attn+ffn。
- 首次会从 HF 下载基座 `Qwen/Qwen3-0.6B`（约 1.2GB）。
- 产出 `data/lora/adapter-*`（adapter），`--merge` 得到合并后的完整模型 `adapter-*-merged`。

**第 3 步：把微调模型接进本地（两种方式任选）**
- **方式 A（HF 直出 OpenAI 兼容）**：用微调后模型起一个本地推理服务，把 `LOCAL_BASE_URL` 指向它。
- **方式 B（导入 Ollama，需 llama.cpp 转 GGUF）**：用 `llama.cpp/convert_hf_to_gguf.py` 把 merged 模型转 GGUF → `ollama create qwen3-ugov -f Modelfile` → `LOCAL_MODEL=qwen3-ugov`。转 GGUF 工具本机暂无，需另行安装。

## 4. 数据说明
- `labeled_1200.csv` 含官方回复 1143 条 → train 1131 / eval 12（按领域分 eval 保覆盖）。
- 目标口径：群众留言 → 面向市民的官方回复（学人民网官方话术："程序性、可兑现、不编造已发生事实"）。

## 5. 限制与建议（诚实）
- 本机 CPU 真训很小样本（证明链路）；要出效果建议在 Kaggle/Colab 免费 GPU 上跑 3+ 轮（项目本就用了 Kaggle）。
- 0.6B 天花板低：可先上 1.5B/3B（需 GPU）。
- 结构化 JSON schema 输出建议用 `json` prompt 约束 + 后端容错（decision 已有 `_coerce_str/_coerce_list` 兜底）。

## 6. 当前已部署的微调模型（blog001/ugov-qwen3）
- **位置**：`data/models/qwen3-ugov/merged/`（完整：`model.safetensors` 1433MB + config/tokenizer/chat_template）。
- `.env` 已指向：`LOCAL_MODEL=qwen3-ugov`、`LOCAL_BASE_URL=http://127.0.0.1:8011/v1`、`LOCAL_MODEL_DIR=...\data\models\qwen3-ugov`。
- **切到本地跑**：① 另开终端跑 `.\start_local_model.ps1`（加载模型监听 8011）② 把 `.env` 的 `LLM_MODE` 改成 `local` ③ 正常 `.\start.ps1`。
  - ⚠️ CPU fp32 推理慢（一条回复数十秒）、0.6B 对 planner/决策 schema 偏弱；更适合"回复生成"。完整管线本地跑会很慢、质量一般——建议本地仅演示，主链路仍 `LLM_MODE=cloud`(DeepSeek)。
- **更优可选：转 GGUF 进 Ollama**（推理快）：`convert_hf_to_gguf.py data/models/qwen3-ugov/merged -o qwen3-ugov.gguf` → `ollama create qwen3-ugov -f Modelfile` → `.env` 的 `LOCAL_BASE_URL` 改回 `http://localhost:11434/v1`。
- **安全**：`.env` 里 `HF_TOKEN` 只用于拉模型，拉完即可删除并去 HF 撤销重建。

## 7. 实测评测发现（重要，别踩坑）
- **现象**：本地微调模型对"施工噪音"留言，输出的是"牡丹江市中级人民法院办公楼竣工…"——**答非所问 + 编造具体单位/时间**。
- **根因**：0.6B 容量小 + 训练数据（1131 条官方回复）高度模板化且含大量具体地名/单位 → 模型**记忆模板、不会泛化**，换诉求就张冠李戴。这与本项目"防幻觉"核心冲突。
- **结论**：**不要**把该模型接入对外输出（`.env` 的 `LOCAL_REPLY=0` 默认关闭；`LLM_MODE=cloud` 主链路保持 DeepSeek）。
- **要变好用，需**：① 换大基座（1.5B/3B/7B）；② 数据清洗（去掉/匿名化具体地名单位、去重、模板回复降权）；③ 少训 1~2 轮防过拟合；④ 加**留出集评测**（当前 eval 仅 12 条，需人评"是否答非所问/是否编造"）；⑤ 任务可改为"改写/润色给定要点"而非自由生成，降低幻觉面。

## 8. 应用集成开关（reply-only 本地化）
- 主链路（planner/分析/决策）必须用**能出 JSON** 的模型（DeepSeek，`LLM_MODE=cloud`）；本地微调模型只适合**回复生成**。
- `app/llm/local_reply.py` + `quality_gate_node` 已支持"定稿后用本地模型改写 `generated_reply`"，开关 `.env: LOCAL_REPLY=1`（默认 0）。
- ⚠️ 鉴于第 7 节实测幻觉，**默认关闭**；要用请先解决泛化问题。
