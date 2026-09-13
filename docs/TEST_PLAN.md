# 测试计划 TEST PLAN v1.0

> 2026-08-25 · 基于 2026-08 版代码全量通读（server.py / app/* / scripts/* / web/*）
> 环境：conda env `urban_agent`（Python 3.11），Windows，离线可测项不依赖 LLM/API Key

---

## 0. 范围与目标

| 项 | 内容 |
|---|---|
| 被测对象 | 多智能体流水线（main.py/service.py/app/workflow）、8 个离线 API、dashboard 数据底座、Web 前端 |
| 数据规模 | 33 万条原始 CSV（D:\人民网留言板2025.csv，331MB）；检索语料 labeled_1200.csv（1200条）；dashboard.json 聚合 |
| 本次触发 | 风险预警采样修复（build_dashboard_cache.py）：由"前300条截断"改为"按月分层等比采样"，需回归 |
| 目标 | ① 数据底座正确性 ② 离线功能零成本可用 ③ 多智能体链路可控可审计 ④ 缺陷清零出报告 |

**不在范围内**：BERT 职能分类器训练精度（见 docs/EVAL.md）、MCP server（RDMA_v2）内部实现、Kaggle notebook。

---

## 1. 通读发现的已知问题（测试重点）

| # | 级别 | 位置 | 问题 | 影响 |
|---|---|---|---|---|
| K1 | **P0** | server.py:267 与 :277 | `/api/history` **重复定义两次**，Starlette 按注册顺序匹配，旧版（无 update_count/has_updates）先注册先命中，新版永不生效 | 历史"有更新"红点失效；修复=删除第一处定义 |
| K2 | P1 | main.py:71 | CLI 的 `log_run` 未传 `complaint_text`（service.py:93 有传） | CLI 产生的历史记录无法"按需重答"（refresh 报"未存原始留言"） |
| K3 | P1 | server.py:180 batch | `/api/batch` 无行数上限，每行跑一次 BM25+分类器 | 大 CSV 提交可致内存/CPU 打满（DoS） |
| K4 | P2 | service.py:275 | stream_pipeline 内 `if "geo" ... : pass` 死代码 | 无影响，清理项 |
| K5 | P2 | trace_store.py | SQLite 未开 WAL，chat 后台线程与请求线程并发写 | 高并发偶发 `database is locked` |
| K6 | P2 | harness/config.py:39 | perception 模型默认路径 `D:/jupyter_work/event_classifier/best_model` 在项目外 | 换机即静默降级（category 为空），需验证降级链路不断 |
| K7 | P3 | corpus.py | 检索语料实际是 labeled_1200.csv（1200条）非 33 万 | 设计如此（BM25 增量为后续项），宣传口径勿混淆 |
| K8 | P3 | nodes.py:287 | execute_node 失败步骤仍把 status 归为 done 的条件依赖 handler 先置 failed，unknown action 路径 step.status 未置位即返回 | 计划步骤状态可能与实际不符 |

> K1/K2 属明确 bug，建议随本计划修复后再进入回归。

---

## 2. 分层测试设计

### L0 数据资产校验（无依赖，已随本次修复执行 ✅）

| 用例 | 步骤 | 期望 |
|---|---|---|
| L0-1 | 读 dashboard.json | total=333470；fields/months/provinces/satisfaction/topics/districts/risk 7 个键齐全 |
| L0-2 | risk 数量与字段 | len(risk)=300；每条仅含 text/province/time/keyword/field |
| L0-3 | **risk 时间跨度** | 覆盖 ≥12 个不同月份（2025-01 ~ 2026-02），最早≠最晚同月（修复验收点） |
| L0-4 | months 总数守恒 | sum(months.count) ≈ total（±解析失败容差<1%） |
| L0-5 | districts | 642 区县，count 降序，lng/lat 在中国境内范围 |
| L0-6 | 可复现性 | 重跑 build_dashboard_cache.py，输出文件除 topics 外逐字节一致（random.seed=42） |

命令：
```powershell
D:\anacanda\envs\urban_agent\python.exe scripts\build_dashboard_cache.py   # ~3min
```

### L1 单元测试（纯函数，pytest，无 LLM/网络）

| 用例 | 目标函数 | 断言要点 |
|---|---|---|
| U1 | rag.hybrid_retriever.tokenize_zh | 空串→[]；单字→[自身]；空白剔除；bigram 长度=n-1 |
| U2 | rag.hybrid_retriever._rrf_fuse | 两路排名融合权重正确；k=60 公式；空列表容错 |
| U3 | geo.geocoder.haversine_km | 北京→上海≈1067km(±5%)；同点=0；对跛点不崩 |
| U4 | geo.geocoder.Geocoder.geocode | "杭州市西湖区"命中 district 级；乱码→None 且进缓存；批量=逐条一致 |
| U5 | harness.guard.check_action | executor 允许 mcp_call；planner 调 decide 被拒（白名单） |
| U6 | harness.guard.check_budget | steps_used≥max_steps(8)/revisions≥2 返回 ok=False |
| U7 | agents.decision._verify_grounding | 伪造 case id 被剔除并追加警告；部门不在证据中→confidence≤0.4；无 docs→confidence≤0.3 |
| U8 | agents.decision._fallback_decision | 关键词映射优先级（分析结果>关键词>高频部门）；输出含降级 warning |
| U9 | rag.case_builder.calculate_quality | 5分解决+满意+有回复=1.0；非法评分不抛异常 |
| U10 | storage.trace_store | log_run/update_run/add_update/list_updates/latest_decision/set_refreshed 全 CRUD；老库 ALTER 迁移幂等 |
| U11 | storage.memory | add/get/close；importance 排序 |
| U12 | llm.client.resolve_llm_config | 请求级 cfg 覆盖 .env；缺省回落 DeepSeek 默认 |
| U13 | scripts.build_dashboard_cache.sample_risk_yearly | 超量→恰好N且跨月；欠量→全保留倒序；脏时间不崩；种子可复现（本次新增，已通过 ✅） |

### L2 API 集成测试（FastAPI TestClient，无 LLM）

前置：`CORPUS_CSV` 指向小样本 CSV 加速启动（可选）。

| 用例 | 端点 | 断言 |
|---|---|---|
| A1 | GET /api/dashboard | 200；total=333470；risk 时间跨度跨年（K1 修复回归关联） |
| A2 | GET /api/search?q=噪音&top_k=3 | 200；≤3条；doc_id/metadata 齐全 |
| A3 | POST /api/quick {"text":"小区晚上施工噪音大"} | field/dept 非空；urgency∈{high,medium}；nearby≤5 |
| A4 | POST /api/quick 含风险词文本 | urgency=high |
| A5 | POST /api/batch 三行 CSV 文本 | total=3；每行五字段齐全 |
| A6 | POST /api/batch 空 body/空行 | total=0 不崩 |
| A7 | GET /api/report?field=城建&province=浙江省 | report_md 五段齐全；summary 回显筛选 |
| A8 | GET /api/history | **含 update_count/has_updates 字段**（验证 K1 修复后新版生效） |
| A9 | POST /api/updates/{run_id} | run 不存在→404；存在→update_count 递增 |
| A10 | GET /api/history/{run_id} | run/steps/gate/updates 结构完整 |
| A11 | GET /api/case/{真实doc_id} | 200；不存在→404 |
| A12 | GET /api/geocode?q=北京市海淀区 | result.level=district |
| A13 | POST /api/chat + 轮询 GET /api/chat/{task_id}（无 Key 注定 error） | task 状态机 running→error，error 信息可读（不挂死） |

### L3 工作流端到端

| 用例 | 方式 | 断言 |
|---|---|---|
| E1 | mock ChatOpenAI（monkeypatch get_llm 返回固定 JSON）跑 graph.invoke | 节点序列 plan→execute*→gate→END；trace 逐节点落库；decision.related_cases 全部 ∈ 检索 ids |
| E2 | mock 让 gate consistency<theta_low | 路由 escalate→human_review，review_status=pending |
| E3 | mock 让 route=retry 且 max_retries 用尽 | 最终 route=escalate（不死循环） |
| E4 | planner 返回非法 action_type | 清洗为 analyze 或进 errors，pipeline 不崩 |
| E5 | 留言含地点实体 | replan 自动注入 geo_query 步骤且位于 decide 前 |
| E6 | 真实 DeepSeek 冒烟（需余额） | `.\run.ps1 "小区附近晚上施工噪音很大"`：耗时<120s，回复≤80字，无编造事实表述 |
| E7 | refresh 闭环 | 对 E6 的 run_id push update → history 出现 has_updates → refresh 返回 refreshed=True 且引用更新内容 |

### L4 前端手工验收（http://127.0.0.1:8000）

| # | 页面 | 检查点 |
|---|---|---|
| W1 | 功能大厅 | 9 卡片渲染、点击跳转 |
| W2 | 民情看板 | total 显示 333,470；月度图 14 个点 |
| W3 | **风险预警** | 300 条卡片时间分布跨全年（不再全是 1 月初）★本次修复验收 |
| W4 | 区县地图 | 642 打点；点击区县弹常见诉求 |
| W5 | 相似案例检索 | 输入关键词出结果，点击案例详情不 404 |
| W6 | 快速分析/批量分析 | 结果表渲染；批量导出可用 |
| W7 | 民情月报 | 报告 Markdown 渲染 |
| W8 | 智能对话（SSE） | 思维链逐节点流出；断网/无 Key 时错误提示友好 |
| W9 | 决策复盘 | 历史列表、"有更新"标记、重答按钮 |

### L5 性能与健壮性

| 用例 | 场景 | 通过标准 |
|---|---|---|
| P1 | /api/quick 并发 20 | p95 < 2s，无 5xx |
| P2 | /api/batch 1000 行 | <60s 完成；>10000 行应被拒（配合 K3 修上限后验证） |
| P3 | chat 并发 3 任务同时落库 trace.db | 无 locked 异常（或加 WAL 后通过，K5） |
| P4 | dashboard.json 冷加载 | 首次 /api/dashboard < 500ms |

---

## 3. 执行与环境

```powershell
# 进入项目根目录
cd D:\urban-governance-copilot

# 单元 + API 层（建议先补 tests/ 目录，当前为空）
& D:\anacanda\envs\urban_agent\python.exe -m pytest tests -v

# 真实冒烟（需 DeepSeek 余额）
.\run.ps1 "小区附近晚上施工噪音很大"
.\start.ps1   # Web 手工验收 W1~W9
```

依赖：pytest（如未安装 `pip install pytest httpx`，TestClient 需要 httpx）。

## 4. 通过标准与产出

- **准出**：P0/P1 缺陷清零；P2 有规避方案；L0/L1/L2 自动化用例 100% 通过；W3 必须通过。
- **产出**：本计划 + tests/ 用例集 + 缺陷记录表（编号/级别/复现/结论）+ 回归报告。
- 顺序建议：先修 K1、K2 → L0（已完成）→ L1 → L2 → L3(E1-E5) → L4 → 真实冒烟 E6/E7 → L5。
