"""语料服务：一次性加载数据 → 文档 → 混合检索器（单例，惰性）。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from loguru import logger

from app.rag.case_builder import build_case_document
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.loader import load_complaints

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "complaints.csv",
)

# 语料文件优先级：环境变量 CORPUS_CSV > data/labeled_1200.csv > data/complaints.csv
_LABELED_PATH = os.path.join(os.path.dirname(_DATA_PATH), "labeled_1200.csv")


def _corpus_path() -> str:
    env = os.getenv("CORPUS_CSV")
    if env and os.path.exists(env):
        return env
    if os.path.exists(_LABELED_PATH):
        return _LABELED_PATH
    return _DATA_PATH


@lru_cache(maxsize=1)
def get_corpus() -> dict[str, Any]:
    path = _corpus_path()
    rows = load_complaints(path)
    documents = [build_case_document(r) for r in rows]
    retriever = HybridRetriever(documents)
    logger.info(f"corpus loaded: {len(rows)} rows from {path}, {len(documents)} documents")
    return {"rows": rows, "documents": documents, "retriever": retriever}
