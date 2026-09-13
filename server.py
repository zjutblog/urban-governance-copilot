"""FastAPI 后端：聊天（异步任务 + 轮询）、geocode、历史、静态前端。"""
from __future__ import annotations

import os
import threading
import uuid
import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from app.geo.geocoder import get_geocoder
from app.rag.corpus import get_corpus
from app.service import refresh_pipeline, run_pipeline, stream_pipeline
from app.storage.trace_store import TraceStore

_BASE = os.path.dirname(os.path.abspath(__file__))
_WEB_DIR = os.path.join(_BASE, "web")

app = FastAPI(title="Urban Governance Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 任务注册表（线程安全）
# ============================================================
class TaskRegistry:
    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[task_id] = {"status": "running", "result": None, "error": None}
        return task_id

    def set(self, task_id: str, status: str, result: Any = None, error: str = None):
        with self._lock:
            self._tasks[task_id] = {"status": status, "result": result, "error": error}

    def get(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._tasks.get(task_id)


tasks = TaskRegistry()


class ChatRequest(BaseModel):
    text: str
    user_id: str = "demo_user"
    api_key: Optional[str] = None


def _llm_cfg(api_key: Optional[str]) -> Optional[dict]:
    """请求级 LLM 配置：随 state 在 pipeline 内传递，各请求互不影响。"""
    return {"api_key": api_key} if api_key else None


def _run_task(task_id: str, text: str, user_id: str, llm_config: Optional[dict] = None):
    try:
        result = run_pipeline(text, user_id, llm_config)
        tasks.set(task_id, "done", result=result)
    except Exception as e:  # noqa: BLE001
        logger.exception("pipeline failed")
        tasks.set(task_id, "error", error=str(e))


@app.post("/api/chat")
def chat(req: ChatRequest):
    task_id = tasks.create()
    threading.Thread(
        target=_run_task, args=(task_id, req.text, req.user_id, _llm_cfg(req.api_key)), daemon=True
    ).start()
    return {"task_id": task_id}


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE 流式：逐事件推送节点执行进度，最终推送 result。"""
    llm_config = _llm_cfg(req.api_key)

    def gen():
        try:
            for ev in stream_pipeline(req.text, req.user_id, llm_config):
                yield ev
        except Exception as e:  # noqa: BLE001
            logger.exception("stream pipeline failed")
            yield f'data: {json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- 民情看板 / 区县地图 / 风险预警（预处理的 dashboard.json）----
_DASH_PATH = os.path.join(_BASE, "data", "dashboard.json")
_dash_cache: dict = {}


def _get_dash() -> dict:
    if not _dash_cache and os.path.exists(_DASH_PATH):
        try:
            with open(_DASH_PATH, encoding="utf-8") as f:
                _dash_cache.update(json.load(f))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dashboard.json load failed: {e}")
    return _dash_cache


@app.get("/api/dashboard")
def dashboard():
    return _get_dash()


@app.get("/api/case/{doc_id}")
def case_detail(doc_id: str):
    """引用案例详情：按 doc_id 返回语料中的案例全文（供前端点击查看）。"""
    corpus = get_corpus()
    for d in corpus["documents"]:
        if str(d.doc_id) == str(doc_id):
            return {"doc_id": d.doc_id, "title": d.title, "content": d.content, "metadata": d.metadata}
    raise HTTPException(404, "case not found")


@app.get("/api/search")
def search(q: str = "", top_k: int = 5):
    """相似案例检索（BM25，无 LLM，免费）。"""
    corpus = get_corpus()
    docs = corpus["retriever"].search(q, top_k=top_k)
    return {"results": [{"doc_id": d.doc_id, "title": d.title, "content": d.content, "metadata": d.metadata} for d in docs]}


@app.get("/api/policy")
def policy_search(q: str = "", top_k: int = 6):
    """政策法规检索（BM25，无 LLM）：按诉求内容返回真实政策条款（Evidence-based 引用）。"""
    from app.rag.policy_corpus import search_policies

    docs = search_policies(q, top_k=top_k)
    return {"results": [{"doc_id": d.doc_id, "title": d.title, "content": d.content, "metadata": d.metadata} for d in docs]}


@app.post("/api/quick")
def quick(req: ChatRequest):
    """单条快速分析（无 LLM）：本地感知分类 + 检索归口投票 + 紧急度规则。"""
    return _quick_analyze(req.text)


def _quick_analyze(text: str) -> dict:
    from collections import Counter

    from app.agents.perception import PerceptionAgent

    corpus = get_corpus()
    docs = corpus["retriever"].search(text, top_k=5)
    dept_vote = Counter(d.metadata.get("department") for d in docs if d.metadata.get("department"))
    field_vote = Counter(d.metadata.get("field") for d in docs if d.metadata.get("field"))
    top_dept = dept_vote.most_common(1)[0][0] if dept_vote else "未知"
    top_field = field_vote.most_common(1)[0][0] if field_vote else "其他"
    RISK = ["上访", "群体", "受伤", "死亡", "断水", "断电", "火灾", "塌陷", "爆炸", "中毒", "安全事故", "危险", "堵路", "罢工"]
    urgency = "high" if any(w in text for w in RISK) else "medium"
    cat, conf = "", 0.0
    try:
        per = PerceptionAgent().classify(text)
        if per:
            cat, conf = per.get("category", ""), float(per.get("category_confidence", 0))
    except Exception:  # noqa: BLE001
        pass
    return {
        "text": text, "category": cat, "category_confidence": conf,
        "field": top_field, "responsible_department": top_dept, "urgency": urgency,
        "nearby": [{"doc_id": d.doc_id, "content": d.content[:140], "metadata": d.metadata} for d in docs],
    }


class BatchRequest(BaseModel):
    content: str  # CSV 文本（每行第一列=留言内容）


@app.post("/api/batch")
def batch(req: BatchRequest):
    """批量分析（无 LLM）：逐行 CSV 做归口+紧急度+满意度预测，返回结果表。"""
    import csv
    import io

    texts = []
    reader = csv.reader(io.StringIO(req.content))
    for row in reader:
        if row and row[0].strip():
            texts.append(row[0].strip())
    results = []
    for t in texts:
        r = _quick_analyze(t)
        # 满意度预测（规则：含风险词或紧急度 high 降为"可能不满意"）
        r["satisfaction"] = "低" if r["urgency"] == "high" else "较高"
        results.append({k: r[k] for k in ("text", "field", "responsible_department", "urgency", "satisfaction")})
    return {"total": len(results), "results": results}


@app.get("/api/report")
def report(field: str = "", province: str = "", month: str = ""):
    """民情月报（无 LLM 模板版）：从 dashboard.json 统计生成治理报告。"""
    d = _get_dash()
    fields = d.get("fields", [])
    months = d.get("months", [])
    provinces = d.get("provinces", [])
    dists = d.get("districts", [])
    risks = d.get("risk", [])

    sel_field = next((x for x in fields if x["name"] == field), None)
    sel_province = next((x for x in provinces if x["name"] == province), None)
    sel_month = next((x for x in months if x["month"] == month), None)

    total = d.get("total", 0)
    line1 = f"## 民情月报（{province or '全国'}{' · ' + field if field else ''}{' · ' + month if month else ''}）"
    line2 = f"本报告基于 {total} 条人民网留言数据。"

    # 领域分布 top
    top_fields = fields[:6]
    field_txt = "、".join(f"{x['name']}({x['count']})" for x in top_fields) or "无"

    # 高风险领域（满意度低/问题突出）—— 用 risk 数据近似高风险词
    risk_keywords = {}
    for r in risks[:100]:
        risk_keywords[r.get("keyword")] = risk_keywords.get(r.get("keyword"), 0) + 1
    top_risk = sorted(risk_keywords.items(), key=lambda x: -x[1])[:6]
    risk_txt = "、".join(f"{k}({v})" for k, v in top_risk) or "暂无"

    # 高发区县
    top_dists = dists[:5]
    dist_txt = "、".join(f"{x['name']}({x['count']})" for x in top_dists) or "无"

    # 月份趋势
    month_txt = "、".join(f"{x['month']}({x['count']})" for x in months[:6]) or "无"

    report_md = (
        f"{line1}\n\n{line2}\n\n"
        f"**一、问题领域分布**\n{field_txt}\n\n"
        f"**二、高发区域（区县）**\n{dist_txt}\n\n"
        f"**三、月度趋势**\n{month_txt}\n\n"
        f"**四、高风险信号**\n{risk_txt}\n\n"
        f"**五、建议**\n"
        f"1. 重点关注上表高发领域与高发区县，加强属地巡查。\n"
        f"2. 对高风险信号（{risk_txt[:30]}）类诉求，建议提前介入、及时回应。\n"
    )
    return {
        "report_md": report_md,
        "summary": {"total": total, "field": sel_field, "province": sel_province, "month": sel_month,
                    "top_risk": top_risk, "top_dists": top_dists},
    }


@app.get("/api/route")
def route(q: str = ""):
    """能做什么路由器：判断用户输入意图，推荐走哪个功能模块。"""
    if not q:
        return {"recommend": "", "name": "", "reason": ""}
    RULES = [
        (["地图", "位置", "附近", "坐标", "哪个区", "在哪儿"], "map", "区县地图洞察", "包含地点/位置信息"),
        (["统计", "多少", "占比", "趋势", "分布", "对比", "排名", "比去年", "环比"], "dashboard", "民情数据看板", "想了解统计/趋势"),
        (["风险", "危险", "隐患", "预警", "上访", "群体", "聚集"], "risk", "风险预警", "涉及风险/隐患"),
        (["类似", "案例", "别人", "怎么处理", "怎么解决", "之前", "有没有"], "search", "相似案例检索", "想检索历史案例"),
        (["月报", "报告", "总结", "这个月", "本月"], "report", "民情月报", "想要一份治理报告"),
        (["批量", "上传", "一批", "csv", "excel", "多个"], "batch", "批量分析", "需要批量处理"),
        (["回想", "上次", "之前做过", "任务", "进度"], "review", "决策复盘", "回顾历史/任务"),
        (["快速", "这一条", "单条", "抓紧"], "quick", "单条快速分析", "快速归类"),
    ]
    for kws, view, name, reason in RULES:
        if any(w in q for w in kws):
            return {"recommend": view, "name": name, "reason": reason}
    return {"recommend": "chat", "name": "智能对话助手", "reason": "综合对话分析"}


class MemoryRequest(BaseModel):
    content: str


class ImageRequest(BaseModel):
    image: str  # base64 编码图片
    question: str = ""  # 可选，提问


@app.post("/api/analyze_image")
def analyze_image(req: ImageRequest):
    """多模态（分阶段 VLM）：识别图片内容 + 读文字，结合治理场景分析。

    依赖 .env 的 VLM_API_KEY / VLM_BASE_URL / VLM_MODEL（硅基流动/智谱的 qwen-vl 等，OpenAI 兼容）。
    """
    import base64

    import openai as _openai

    key = os.getenv("VLM_API_KEY", "")
    if not key:
        return {"error": "未配置视觉模型 key：请在 .env 填 VLM_API_KEY"}

    base_url = os.getenv("VLM_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("VLM_MODEL", "Qwen/Qwen2-VL-7B-Instruct")
    question = req.question or "请描述这张图片的主要内容，提取图中的文字/数字/关键信息，并结合城市社区治理场景，指出可能存在的治理问题。"
    try:
        client = _openai.OpenAI(base_url=base_url, api_key=key)
        resp = client.chat.completions.create(model=model, messages=[
            {"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{req.image}"}},
            ]},
        ])
        return {"text": resp.choices[0].message.content, "model": model}
    except Exception as e:  # noqa: BLE001
        return {"error": f"视觉模型调用失败：{e}"}


def _vlm_understand(req: ImageRequest) -> tuple[str, dict]:
    """VLM 识别图片为文本。返回 (文本, 错误dict或空)。"""
    import openai as _openai

    key = os.getenv("VLM_API_KEY", "")
    if not key:
        return "", {"error": "未配置 VLM_API_KEY，请在 .env 填写"}
    base_url = os.getenv("VLM_BASE_URL", "https://api.moonshot.cn/v1")
    model = os.getenv("VLM_MODEL", "kimi-k2.6")
    question = req.question or (
        "你是城市治理现场图片识别助手。请用**简洁分点**格式识别这张现场图片，总字数控制在 120 字以内，"
        "按下面 5 行输出（没有的写“无”）：\n"
        "① 地点/地址：\n② 问题类型：\n③ 涉及对象/单位：\n④ 一句话概括：\n⑤ 可能的治理问题：\n"
        "要求：直接给结论，不要输出 Markdown 标题符号(#)、加粗符号(**)或分隔线(---)，不要长篇分析。"
    )
    try:
        client = _openai.OpenAI(base_url=base_url, api_key=key)
        resp = client.chat.completions.create(model=model, messages=[
            {"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{req.image}"}},
            ]},
        ])
        return (resp.choices[0].message.content or "").strip(), {}
    except Exception as e:  # noqa: BLE001
        return "", {"error": f"视觉模型调用失败：{e}"}


@app.post("/api/chat_image")
def chat_image(req: ImageRequest):
    """图片 → 识别 → 当留言走完整管线（有 DeepSeek 余额=思维链/归口/决策/地图；无余额=降级归口+地图）。"""
    content, err = _vlm_understand(req)
    if err:
        return err
    # 走完整多智能体管线（分析/决策用 LLM，有余额即完整；无余额自动降级）
    try:
        res = run_pipeline(content, user_id="image_user")
        res["image_text"] = content
        return res
    except Exception as e:  # noqa: BLE001
        # 降级：无 LLM（检索归口 + 紧急度规则 + 地图 geocode）
        quick = _quick_analyze(content)
        geo_doc = get_geocoder().geocode(content)
        return {
            "image_text": content,
            "llm_fallback": True,
            "quick": quick,
            "geo": {"query_location": geo_doc} if geo_doc else None,
        }


@app.post("/api/memory")
def save_memory(req: MemoryRequest):
    """保存任务备注到长期记忆（memory.db）。"""
    from app.storage.memory import MemoryStore
    store = MemoryStore()
    store.add_memory("demo_user", "note", req.content.strip(), importance=0.7)
    store.close()
    return {"ok": True}


# ---- 通用 skills 封装：文本分析 / 表格数据分析（无 LLM，本地可跑）----

# 风险词（文本分析用）
_TXT_RISK = ["上访", "群体", "受伤", "死亡", "中毒", "断水", "断电", "火灾", "塌陷", "爆炸", "安全事故", "危险", "堵路", "罢工", "欠薪"]


@app.post("/api/analyze_document")
def analyze_document(req: MemoryRequest):
    """文本/文档分析（无 LLM 基础版）：统计 + 高频词 + 风险词 + 生成报告。"""
    import re
    from collections import Counter

    text = req.content.strip()
    if not text:
        return {"error": "内容为空"}
    n_chars = len(text)
    n_sents = len(re.split(r"[。！？;；\n]+", text)) - 1
    # 高频词（去停用词）
    stop = set("的了是在和与就都一个也都有很被把对从这可那为到而我说你".split())
    words = [w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}", text) if w not in stop]
    top_words = Counter(words).most_common(8)
    hit_risks = [w for w in _TXT_RISK if w in text]
    report_md = (
        "## 文本分析报告\n\n"
        f"- 字符数：{n_chars}，句子数：{n_sents}\n"
        f"- 出现风险信号：{'、'.join(hit_risks) if hit_risks else '未检出'}\n"
        f"- 高频词：{'、'.join(w for w, _ in top_words) or '无'}\n\n"
        "**风险提示**：" + ("请关注文中" + "、".join(hit_risks[:3]) + "等信号。" if hit_risks else "未发现明显风险信号。")
    )
    return {"n_chars": n_chars, "n_sents": n_sents, "top_words": top_words, "risk": hit_risks, "report_md": report_md}


@app.post("/api/analyze_excel")
def analyze_excel(req: MemoryRequest):
    """Excel/CSV 数据分析（无 LLM）：结构/数据质量/数值统计/异常值。"""
    import io

    import pandas as pd

    try:
        df = pd.read_csv(io.StringIO(req.content))
    except Exception as e:  # noqa: BLE001
        return {"error": f"解析失败：{e}"}
    if df.empty:
        return {"error": "数据为空"}
    cols = []
    for c in df.columns:
        cols.append({"name": str(c), "missing": int(df[c].isna().sum()), "dtype": str(df[c].dtype)})
    quality = round(1 - float(df.isna().mean().mean()), 3)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    num_stats = {}
    for c in num_cols[:20]:
        s = df[c]
        num_stats[str(c)] = {"min": round(float(s.min()), 3), "max": round(float(s.max()), 3),
                             "mean": round(float(s.mean()), 3), "std": round(float(s.std()), 3)}
    # 异常值（数值列，3σ）
    outlier_ann = []
    for c in num_cols[:10]:
        s = df[c].dropna()
        if s.empty or s.std() == 0:
            continue
        lo, hi = s.mean() - 3 * s.std(), s.mean() + 3 * s.std()
        n_out = int(((s < lo) | (s > hi)).sum())
        if n_out:
            outlier_ann.append({"col": str(c), "outliers": n_out, "range": [round(float(lo), 2), round(float(hi), 2)]})
    report_md = (
        "## 数据分析报告\n\n"
        f"- 行数 **{len(df)}**，列数 **{len(df.columns)}**\n"
        f"- 数据质量分 **{quality * 100:.1f}%**（缺失越少越高）\n"
        f"- 数值列：{len(num_cols)} 个；异常列：{len(outlier_ann)} 个\n\n"
        "**异常值提示**：" + ("；".join(f"{o['col']}({o['outliers']}个)" for o in outlier_ann[:5]) or "未检出明显异常。")
    )
    return {"rows": len(df), "cols": len(df.columns), "columns": cols, "quality": quality,
            "num_stats": num_stats, "outliers": outlier_ann, "report_md": report_md}


@app.get("/api/chat/{task_id}")
def chat_status(task_id: str):
    t = tasks.get(task_id)
    if t is None:
        raise HTTPException(404, "task not found")
    return t


@app.get("/api/geocode")
def geocode(text: str):
    r = get_geocoder().geocode(text)
    return {"query": text, "result": r}


@app.get("/api/history")
def history():
    store = TraceStore()
    rows = store.conn.execute(
        "SELECT run_id, complaint_id, status, steps_used, consistency, route, created_at, refreshed_at, complaint_text FROM runs ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    counts = store.update_counts()
    # 取每 run 最近一次决策结论（任务记忆）
    runs = []
    for r in rows:
        d = dict(r)
        n = counts.get(d["run_id"], 0)
        d["update_count"] = n
        d["has_updates"] = n > 0
        d["conclusion"] = None
        dec = store.latest_decision(d["run_id"])
        if dec:
            try:
                dj = json.loads(dec)
                d["conclusion"] = {
                    "department": dj.get("responsible_department"),
                    "reply": dj.get("generated_reply"),
                    "route": d.get("route"),
                }
            except Exception:  # noqa: BLE001
                pass
        runs.append(d)
    store.close()
    return {"runs": runs}


class UpdateRequest(BaseModel):
    content: str  # 新增的留言补充内容（模拟留言板平台推送）


@app.post("/api/updates/{run_id}")
def push_update(run_id: str, req: UpdateRequest):
    """接收一条留言更新（模拟留言板推送）。历史记录将被打上"有更新"标记。"""
    store = TraceStore()
    try:
        if store.get_run(run_id) is None:
            raise HTTPException(404, "run not found")
        total = store.add_update(run_id, req.content.strip())
        return {"run_id": run_id, "update_count": total}
    finally:
        store.close()


@app.get("/api/history/{run_id}")
def history_detail(run_id: str):
    store = TraceStore()
    run = store.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    steps = store.conn.execute("SELECT * FROM steps WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()
    gate = store.conn.execute("SELECT * FROM gate_results WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (run_id,)).fetchone()
    updates = store.list_updates(run_id)
    store.close()
    if run is None:
        raise HTTPException(404, "run not found")
    return {
        "run": dict(run),
        "steps": [dict(s) for s in steps],
        "gate": dict(gate) if gate else None,
        "updates": updates,
    }


@app.get("/api/history/{run_id}/chain")
def history_chain(run_id: str):
    """关键证据链：把一次运行聚合为可审计链路（诉求→计划→执行→证据→引用校验→推理→门控→回复）。"""
    from app.services.evidence_chain import build_evidence_chain

    try:
        return build_evidence_chain(run_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/history/{run_id}/refresh")
def history_refresh(run_id: str, req: ChatRequest):
    """按需重答：原留言 + 过去生成的决策 + 新增更新 拼成 prompt 喂 LLM。不点不花钱。"""
    try:
        return refresh_pipeline(run_id, _llm_cfg(req.api_key))
    except ValueError as e:
        raise HTTPException(400, str(e))


if os.path.isdir(_WEB_DIR):
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
