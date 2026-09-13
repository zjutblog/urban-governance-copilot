"""政策知识库：加载 data/policy_corpus.jsonl → 政策条款 Document → BM25 检索。

设计要点：
- 为「引用真实条款」而做：检索粒度是**条款级**，decision 可引用「《标题》第X条」。
- 复用 HybridRetriever（BM25 中文 bigram，向量默认关），policy 条款也走统一检索接口。
- 文件缺失/为空时优雅降级为「无政策库」，不阻断工作流。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

from loguru import logger

from app.domain.document import Document
from app.rag.hybrid_retriever import HybridRetriever

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_POLICY_PATH = os.path.join(_ROOT, "data", "policy_corpus.jsonl")


def _load_policy_rows() -> list[dict]:
    if not os.path.exists(_POLICY_PATH):
        logger.warning(f"policy corpus not found: {_POLICY_PATH}")
        return []
    rows = []
    with open(_POLICY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:  # noqa: BLE001
                logger.warning(f"bad policy line skipped: {e}")
    return rows


def _article_to_doc(policy: dict, article: dict) -> Document:
    """把「政策 + 条款」映射为一个可检索的 Document（条款级粒度，便于引用具体条款）。"""
    title = policy.get("title", "")
    year = (policy.get("effective_date") or "")[:4] or (policy.get("publish_date") or "")[:4]
    suffix = f"（{year}）" if year else ""
    art_no = article.get("article_no", "")
    content = f"{title}{suffix} | 相关领域：{', '.join(policy.get('category', []) or [])} | 适用关键词：{', '.join(policy.get('keywords', []) or [])} | {art_no}：{article.get('content', '')}"
    metadata = {
        "policy_id": policy.get("policy_id", ""),
        "title": title,
        "doc_no": policy.get("doc_no", ""),
        "authority": policy.get("authority", ""),
        "article_no": art_no,
        "category": ", ".join(policy.get("category", []) or []),
        "keywords": ", ".join(policy.get("keywords", []) or []),
        "publish_date": policy.get("publish_date", ""),
        "effective_date": policy.get("effective_date", ""),
        "doc_type": "policy",
    }
    return Document(
        doc_id=f"{policy.get('policy_id', '')}-{art_no}",
        title=f"{title} · {art_no}",
        content=content,
        source="policy_corpus",
        doc_type="policy",
        metadata=metadata,
        quality_score=0.9,  # 政策条款可信度视为高；query 检索时已按相关性排序
    )


@lru_cache(maxsize=1)
def get_policy_corpus() -> dict[str, Any]:
    """单例：返回 {policies, documents, retriever}。documents 为条款级。"""
    policies = _load_policy_rows()
    documents = []
    n_articles = 0
    for p in policies:
        arts = p.get("articles") or []
        for a in arts:
            documents.append(_article_to_doc(p, a))
            n_articles += 1
    retriever = HybridRetriever(documents) if documents else None
    logger.info(f"policy corpus loaded: {len(policies)} policies, {n_articles} articles")
    return {"policies": policies, "documents": documents, "retriever": retriever}


def search_policies(query: str, top_k: int = 5) -> list[Document]:
    """按诉求内容检索相关政策条款，返回条款 Document 列表（按相关性降序）。"""
    corpus = get_policy_corpus()
    retriever = corpus["retriever"]
    if retriever is None or not query.strip():
        return []
    return retriever.search(query, top_k=top_k)


def format_policy_evidence(docs: list[Document], max_items: int = 6) -> str:
    """把检索到的政策条款格式化成 prompt 的政策依据块（仅用真实条款）。"""
    if not docs:
        return "（未检索到相关法规条款）"
    lines = []
    for d in docs[:max_items]:
        m = d.metadata
        ref = f"《{m.get('title', '')}》{m.get('article_no', '')}"
        lines.append(f"- [{ref}]（{m.get('authority', '')}）{d.metadata.get('keywords', '')}：{_strip_prefix(d.content)}")
    return "\n".join(lines)


def _strip_prefix(content: str) -> str:
    """去掉 content 前半段拼接的标题/领域/关键词前缀，只留条款正文。"""
    if " | " in content:
        return content.split(" | ", 2)[-1]
    return content


def _cite_format(d: Document) -> str:
    m = d.metadata
    return f"《{m.get('title', '')}》{m.get('article_no', '')}"
