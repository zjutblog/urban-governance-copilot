"""混合检索：BM25（字符 bigram） + 向量（chroma）+ 元数据过滤，RRF 融合。"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from loguru import logger
from rank_bm25 import BM25Okapi

from app.domain.document import Document
from app.rag.embedding import EmbeddingModel
from app.storage.vector_store import VectorStore


def tokenize_zh(text: str) -> list[str]:
    """中文字符 bigram 分词（无外部依赖，够用于 BM25）。"""
    text = re.sub(r"\s+", "", text or "")
    if not text:
        return []
    if len(text) == 1:
        return [text]
    return [text[i] + text[i + 1] for i in range(len(text) - 1)]


def _rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion，合并多个排序列表。"""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


class HybridRetriever:
    def __init__(self, documents: list[Document] | None = None):
        self.documents = documents or []
        self._bm25: Optional[BM25Okapi] = None
        self._id_map: dict[int, str] = {}
        self._embedder: Optional[EmbeddingModel] = None
        self._vector_store: Optional[VectorStore] = None
        self._vector_ready = False
        if self.documents:
            self._build_bm25()

    def _build_bm25(self):
        corpus = [tokenize_zh(d.content) for d in self.documents]
        self._bm25 = BM25Okapi(corpus)
        self._id_map = {i: d.doc_id for i, d in enumerate(self.documents)}
        logger.info(f"BM25 built over {len(self.documents)} docs")

    def _ensure_vector(self):
        if self._vector_ready:
            return
        # 语义向量默认关闭（CPU 慢）；设 RETRIEVER_USE_VECTOR=1 启用（GPU/预计算场景）
        if os.getenv("RETRIEVER_USE_VECTOR") != "1":
            self._vector_ready = False
            return
        try:
            self._embedder = EmbeddingModel()
            self._vector_store = VectorStore()
            # 已持久化的 collection 直接复用；空则构建
            if self._vector_store.count() == 0 and self.documents:
                texts = [d.content for d in self.documents]
                vecs = self._embedder.encode(texts)
                self._vector_store.add_documents(self.documents, vecs)
            self._vector_ready = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"vector search unavailable: {e}")
            self._vector_ready = False

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[Document]:
        if not self.documents:
            return []

        # 1. BM25
        bm25_scores = self._bm25.get_scores(tokenize_zh(query))
        bm25_ranked = [self._id_map[i] for i in bm25_scores.argsort()[::-1]]

        ranked_lists: list[list[str]] = [bm25_ranked[:top_k * 2]]

        # 2. 向量
        self._ensure_vector()
        if self._vector_ready:
            qv = self._embedder.encode([query])
            try:
                res = self._vector_store.search(qv[0], top_k=top_k * 2, where=where)
                vec_ranked = res.get("ids", [[]])[0] if res else []
                ranked_lists.append([str(i) for i in vec_ranked])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"vector search failed: {e}")

        # 3. RRF 融合
        fused_ids = _rrf_fuse(ranked_lists)[:top_k]

        by_id = {d.doc_id: d for d in self.documents}
        results = [by_id[i] for i in fused_ids if i in by_id]

        # 4. 元数据过滤兜底
        if where:
            results = [d for d in results if all(d.metadata.get(k) == v for k, v in where.items())]

        return results
