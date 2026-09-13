# GitHub 发布与涨星指南（城市治理 Copilot）

> 目标：**安全合规地公开**，并尽可能拿到 star。
> 先记住一句话：**star 取决于"差异化 + 可复现 + 传播"，不取决于代码量。**

---

## 一、红线（不做 = 侵权 / 泄露 / 封号）

- ❌ **不传全量数据**：33 万 CSV 来自第三方数据站，`PLAN.md` 已明确"仅研究用途、不公开传播全量数据"。只能放**去标识样例 ≤200 条**。
- ❌ **不传 `.env`**：里面有 DeepSeek key、kimi key、高德 key（之前还有 HF token）。
- ❌ **不传模型权重/大文件**：`data/models/`（390MB+1.4GB）、`data/lora/`（1.4GB）、`*.safetensors`、`*.gguf`、`data/trace.db`、`data/memory.db`（含留言原文）。
- ✅ **要加**：`LICENSE`（建议 MIT 或 Apache-2.0）+ `NOTICE`/README 里的**数据来源与合规声明**。

---

## 二、`.gitignore` 重写（当前缺失项已补齐）

```gitignore
# ---- 密钥 / 环境 ----
.env
.env.*
!.env.example

# ---- Python ----
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# ---- 模型权重（严禁，超大）----
data/models/
data/lora/
*.safetensors
*.gguf
*.bin
*.pt
*.pth

# ---- 数据：派生 / 含原始内容 / 大文件 ----
data/*.db
data/*.sqlite
data/chroma/
data/trace.db
data/memory.db
data/**/*.jsonl
!data/policy_corpus.jsonl      # 政策库是公开法规，可提交
data/labeled_1200.csv
data/complaints.csv
data/eval_*.csv
data/dashboard.json
data/*.log
data/ppt_extract.txt

# ---- 允许公开的样例 ----
!data/samples/**
!data/region_centers.csv       # DataV 公开行政区划中心点，可提交

# ---- 脚本临时输出 / 日志 ----
scripts/*_out.txt
scripts/*.log
*.log

# ---- IDE / OS ----
.vscode/
.idea/
.DS_Store
Thumbs.db
notebooks/.ipynb_checkpoints/
```

> 提交前务必跑 `git status` 逐项确认：**没有 `.env`、没有 `*.safetensors`、没有原始数据**。

---

## 三、目录改造：把"能公开的"和"不能公开的"分开

1. 新建 `data/samples/`：放 **≤200 条去标识样例**（去掉昵称、精确属地，保留领域/类型/回复结构）。
2. 其余数据留在本地，靠 `.gitignore` 排除。
3. 新增 `.env.example`（占位符，不含真 key）：
   ```
   LLM_BASE_URL=https://api.deepseek.com/v1
   LLM_MODEL=deepseek-chat
   LLM_API_KEY=sk-your-key
   QUALITY_GATE_K=3
   VLM_BASE_URL=https://api.moonshot.cn/v1
   VLM_MODEL=your-vlm-model
   VLM_API_KEY=sk-your-vlm-key
   AMAP_KEY=your-amap-key
   ```
4. （可选）`scripts/build_public_sample.py`：一键从本地数据生成去标识样例。

---

## 四、README：**决定 star 的就是这一页**

**顺序极其重要**（访客 5 秒决定要不要 star）：

1. **标题 + 一句话定位**
   `城市治理 Copilot —— 从群众留言到可验收工单的多智能体数字员工`
2. **徽章**：Python / License / 比赛 / 离线可跑
3. **🎬 演示 GIF（最关键！）**：录一段"输入留言 → 政策引用 → 生成工单"的 10 秒动图放最上面。**没有 GIF 的仓库 star 率大幅下降。**
4. **它有什么不一样（3 条，别多）**
   - 不编法条：只引用检索到的真实政策条款，溯源校验不一致即剔除
   - 会自主规划：自适应检索（该查才查、不够再挖）
   - 交付可验收：一键生成标准处理工单（字段完整率 100%）
5. **架构图**：直接放 `docs/flow.mmd` 渲染图（Mermaid 源码 GitHub 原生渲染）
6. **功能清单**（对齐赛道关键词：自主规划 / 工具调用 / 检索增强 / 多模态 / 长短期记忆 / 工作流编排 / 端到端闭环）
7. **快速开始（3 条命令跑起来）**
   ```
   pip install -r requirements.txt
   cp .env.example .env      # 填 key（不填也能跑离线 demo）
   ./start.ps1               # 打开 http://127.0.0.1:8000
   ```
   ⚠️ 一定要有**"无 API key 也能跑"的离线 demo**（`/api/quick`、`/api/search`、`/api/policy`）——可复现性直接影响 star。
8. **数据与合规声明**（放显眼位置，反而加分）
9. **评测结果（诚实表）**：1.7% / 37.6% / 50.6% / 80.7% + "未达 90%" + roadmap
10. **License / 致谢 / 联系**

**加分项**：中英双语 README（扩国际受众）；`docs/` 里放路演 PPT 大纲与架构图。

---

## 五、Star 从哪来（诚实版）

**先说预期**：大多数个人项目 star <100；能上 500+ 的都是"选题稀缺 + 可复现 + 传播到位"。你的**选题稀缺度不错**（政务 + 多智能体 + 33万真实数据 + 反编造）。

**渠道（按性价比）**
1. **掘金 / 知乎 / 小红书 / B站**：写一篇《我用 33 万条真实留言做了个政务数字员工》，配 GIF + 架构图 + 踩坑。**这是中文圈最有效的**。
2. **V2EX / 即刻 / 相关微信群、QQ 群**：一句话 + 链接，别硬广。
3. **Reddit**：r/LocalLLaMA、r/LLMDevs（英文简介 + demo GIF）。
4. **Hacker News / X**：Show HN；英文 one-liner。
5. **awesome-list PR**：提交到 `awesome-llm-apps`、`awesome-ai-agents` 等。
6. **借势**：比赛名次、论文、公众号/导师转发。

**技巧**
- 发布**工作日早上**；标题写"结果/数字"不写"我做了个…"。
- README 首屏必须有 GIF。
- 持续维护：回 issue、发 release、写 roadmap（活跃度影响推荐）。
- **绝不要买 star / 刷 star**：GitHub 会清理并可能封号，得不偿失。

---

## 六、执行步骤（命令）

```powershell
cd D:\urban-governance-copilot

# 1) 先重写 .gitignore（按第二节），补 .env.example / LICENSE
# 2) 初始化
git init
git add -A
git status            # ★逐项确认：无 .env、无 *.safetensors、无原始数据/大文件
git commit -m "feat: 城市治理 Copilot — 多智能体政务数字员工（自主规划/工具调用/政策引用/工单交付）"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<repo>.git
git push -u origin main
```

**push 前自查（重要）**：
```powershell
git ls-files | Select-String -Pattern "\.env|safetensors|\.db$|labeled_1200|complaints\.csv"
```
有输出就说明有问题，先 `git rm --cached` 移除并补 `.gitignore`。

**万一已经误提交了 key**：立刻去 DeepSeek/月之暗面/高德后台**吊销重发**，并用 `git filter-repo` 清历史（仅删文件不够，历史里还在）。

---

## 七、我可以代做
- 重写 `.gitignore`（UTF-8）｜生成 `.env.example`｜加 `LICENSE` + 数据合规 `NOTICE`
- 生成 `data/samples/` 去标识样例脚本
- 起草 `README.md`（中文）+ 英文摘要
- 执行 `git init / add / commit`（**push 需要你提供 remote 和凭据**）
