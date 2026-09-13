# 项目进展快照（PROGRESS）

> 用途：上下文中断/续接时的恢复锚点。读完这份 + `docs/PLAN.md` + `work.md` 即可继续。

---

## 一、项目定位（论文/就业双线）
- 城市治理多智能体：人民网留言板 2025（33.3万条）+ 1200 条 LLM 标注
- 论文三创新点：①Adaptive Retrieval ②Evidence-based Decision ③Governance Quality Gate
- 对比：普通 LLM / 固定 RAG / Agentic RAG（消融）

## 二、环境
- conda env `urban_agent`（D:\anacanda\envs\urban_agent\python.exe，Python 3.11.15）
- 启动：`.\start.ps1`（已加自动杀 8000 端口旧进程）；前端版本号 `?v=15`
- `.env`：LLM_API_KEY=DeepSeek(已充值，可用)，VLM_API_KEY=kimi(sk-开头,51位)，VLM_BASE_URL=https://api.moonshot.cn/v1，VLM_MODEL=**kimi-k2.6**
- 注意：sklearn 1.9 分类器崩溃（numpy 2.4 兼容）→ 用 LightGBM；本地 OCR(easyocr/rapidocr) 装不上（临时目录/网络）
- **LLM 双线（.env LLM_MODE=cloud|local）**：cloud=DeepSeek，local=Ollama Qwen(`qwen3:0.6b/8b`，CPU 一次 ~16s)。无 NVIDIA GPU；官方 huggingface.co 被墙，**用 ModelScope 或 hf-mirror.com 下模型**。
- **LoRA 微调链已搭好并跑通（证明级）**：`scripts/build_lora_dataset.py`(免费：官方回复→1131 训/12 验)→`scripts/train_lora_qwen.py`(CPU float32 LoRA，assistant 掩码只学回复)。基座 `Qwen/Qwen3-0.6B` 已下到 `data/lora/base_qwen3-0.6b`(1.5G)，adapter 证明在 `data/lora/adapter-qwen3-0.6b`。正式训练需 GPU/更多数据（详见 docs/LOCAL_QWEN.md）。

## 三、数据
- `D:\人民网留言板2025.csv`（33.3万，GB18030）
- `data/labeled_1200.csv`（1200条 LLM标注 + CSV标签 join，original_id=CSV行号）
- `data/dashboard.json`（33万统计：领域/月份/省份/满意度/高发词 + 642区县 + 300风险）
- `data/trace.db`（历史 run）+ `data/memory.db`（记忆）
- 脚本：scripts/build_labeled_1200.py、stats_2025.py、eval_dept_33w.py(LightGBM)、build_dashboard_cache.py、make_kaggle_notebook.py、build_geocoding_data.py
- 评测脚本：eval_department_baseline.py、eval_department_function_baseline.py、train_function_classifier.py

## 四、系统架构
- app/workflow/graph.py：plan→execute→replan→gate→human_review（LangGraph）
- 动作：perceive/analyze/retrieve/stats/geo_query/decide/mcp_call
- app/harness/: 动作白名单+预算；app/quality/self_consistency.py：k=3投票 pass/retry/escalate
- app/agents/decision.py：**防幻觉**（证据注入+引用校验+编造拦截+降级兜底）
- app/rag/：corpus(labeled_1200优先)、hybrid_retriever(BM25，向量默认关)、**policy_corpus(政策库条款级BM25)**
- app/tools/mcp_bridge.py：MCP(geotools/gis_data/model_tools)，app/workflow/nodes.py 有 mcp_call；另新增动作 **retrieve_policy**（决策前自动注入，检索真实法规条款）
- 知识：scripts/dept_rules.py（职能映射23类，训练/评测/notebook 共用）

## 五、已完成功能（首页功能大厅 11 个）
1. 智能对话助手（SSE流式 + 左侧历史对话列表可点击恢复）
2. 民情数据看板（33万统计）
3. 区县地图洞察（642区县打点，瓦片用 wprd0）
4. 风险预警（26关键词）
5. 相似案例检索（BM25）
6. 单条快速分析（无LLM：检索归口+规则）
7. 批量分析（CSV→批量归口+满意度，导出）
8. 民情月报（模板生成）
9. 文档分析（无LLM基础版）
10. 团队搜索/其他：见 web 功能
11. 多模态：**📷 上传照片 → /api/chat_image**（kimi识图→当留言走完整管线；无DeepSeek余额自动降级归口+地图）

## 六、已完成的关键改进
- **Adaptive Retrieval**（论文创新点1，核心）：`app/workflow/nodes.py` 的 `_assess_retrieval_need` + `replan_node` 接入。按信息充分性决定 retrieve/deepen(限1次)/skip；检索可用分析建议的 query。**单元测试通过**（4情形：充分skip/不足retrieve/案例好skip/初检差deepen/重试后skip）
- **政策检索（Evidence-based，论文创新点2缺的一环）**：政策库 `data/policy_corpus.jsonl`（24 部真实法规/44 条款）→ `app/rag/policy_corpus.py`（条款级 BM25）→ 工作流在 decide 前自动注入 `retrieve_policy` → decision prompt 注入政策证据、`policy_references` 只允许引用检索到的真实条款（`_verify_grounding` + `_is_valid_policy_ref` 剔除编造引用）。前端决策卡新增「政策依据」，`/api/policy` 独立检索。端到端已验证输出真实《标题》第X条引用。
- 防幻觉：decision 证据注入+引用校验+编造拦截+降级；make_decision 解析失败重试+兜底
- 多轮记忆：service.run_pipeline 写 memory；analyst/decision 注入历史
- 前端去AI化：action_type 英文→中文、去掉技术小字、核心结论前置、引用案例可点击弹窗
- 能力路由器 /api/route：输入推荐功能
- 高德瓦片修复（webrd→wprd）；.view[hidden] 修复布局；前端版本号防缓存
- 报告前置：核心结论/处理步骤/问题分析/结果复核/处理建议
- **前端修复（UX）**：①历史记录改为**忠实重放**本 run 完整决策+地点+轨迹（不再截断 160 字/串位）②新增 `clearMapState()`——本次无地点时清空旧地图（修复"问临沂却显示别处/地图残留上一条"）③`.history-back-row` 样式修复顶部返回按钮跑偏 ④decision `_coerce_str` 容错（LLM 把难度输出成整数导致解析失败）⑤ACTION_CN 补 retrieve_policy。前端 ?v=14
- **初赛评分对标**：`docs/COMPETITION_SCORE.md`（5×20 维度自评≈76/100 + 补分清单 + 演示脚本），引导向工单生成/评测体系补分
- **引用展示修复（?v=16）**：`kv()` 会转义 HTML → "参考依据/政策依据"把 `<a class="case-link">` 原样显示成文本、案例不可点。新增 `kvRaw()`（不转义，仅用于已 esc 的安全富内容），案例改为可点击 chip（📄 案例 ID）；并修掉洪水/交通/生活圈卡片 8 处同类转义问题。
- **本地 Qwen 微调线（已停用）**：见 docs/LOCAL_QWEN.md。结论：0.6B + 模板化官方回复数据 → 背模板不泛化、会编造，**不接入对外输出**；主链路保持 `LLM_MODE=cloud`(DeepSeek)，`.env` 已清理（HF_TOKEN 移除）。
- **图片识别结果美化（?v=17）**：新增 `renderMdLite()`（先 `esc` 再套格式的安全轻量 Markdown），"📷 图片识别"改为整块渲染（加粗/分隔线/列表/段落），不再显示 `**`、`---` 字面符号；`server.py::_vlm_understand` 提示词收紧为"5 行简洁分点、≤120 字、不要 Markdown 符号"。

## 七、评测现状（诚实）
- 归口基线：机构名 Top-1 1.7%；职能 v2 检索式 **37.6%**；BERT 分类器 21-29%
- 33万职能基线(LightGBM)：Top-1 **50.6%**、Top-3 80.7%（党委政府办90%，住建仅6%）
- **缺**：人工标注Benchmark、Recall@5、决策准确率、幻觉率、消融（LLM vs 固定RAG vs AgenticRAG）
- **关键**：分类F1 90%、归口Accuracy 90% 现状远未达（20-37%），别写成达标

## 八、待办（按 claim，优先级）
1. ✅ **政策检索**（Evidence-based 缺政策，已完成）：建政策库（`data/policy_corpus.jsonl`，24 部真实法规、44 条款）+ 检索（`app/rag/policy_corpus.py`，条款级 BM25）+ decision 引用真实条款（prompt 注入政策证据、`_verify_grounding` 政策引用溯源校验剔除编造；工作流自动注入 `retrieve_policy` 步骤）。端到端验证：`policy_references=['《大气污染防治法》第X条','《噪声污染防治法》第X条']` 均真实可溯源。前端决策卡新增「政策依据」展示 + `/api/policy` 端点。
2. ✅ **工单生成**（已完成）：`app/agents/work_order.py` 把留言+决策组装成标准处理工单（类型/领域/区域/紧急度/风险/归口/承办/办理时限/处置措施/政策依据/参考案例/面向市民回复/复核/置信度），确定性兜底使**关键字段完整率 100%**；`_extract_result` 每次结果带 `work_order`；前端聊天顶部「📋 处理工单」卡片，可**复制 Markdown / 下载 JSON**。
3. **Quality Gate 强化**（claim3）：self-consistency 上补 证据充分性/冲突检测/风险检测/不确定性量化
4. **不确定性识别**：主动拒答/请求补充信息（ask_user 类）
5. **评测体系**：人工标注 + recall@5 + 幻觉率 + 消融

## 九、关键文件
- 前端：web/index.html、app.js、style.css（版本 ?v=12）
- 后端：server.py（/api/chat/stream, dashboard, case, search, quick, batch, report, route, memory, analyze_document, analyze_excel, analyze_image, chat_image）
- 工作流：app/workflow/nodes.py（含 adaptive retrieval、geo 动态插入）
- 服务：app/service.py（run_pipeline, stream_pipeline）
- 配置：.env（LLM/VLM key）

## 十、恢复要点（下次继续）
- 若要我继续，从「待办」第1项「政策检索」开始，或按用户优先级
- 新增功能后：改 FEATURES(app.js) + index.html 加 view + server.py 加接口 + 前端处理函数 + bump ?v=N
- 测试不用 LLM 的用 `& py scripts/xxx.py`；跑完整管线用 run_pipeline（DeepSeek 已充值，可用）
