"""感知层 Agent：用本地已训练的小模型（event_classifier）做分类。

CPU 上跑 BERT-base 分类很快，避免让 8B 大模型做重复的粗分类，省 token 省时间。
"""
from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

from app.harness.config import get_harness_config


class PerceptionAgent:
    """本地事件分类器（后训练产物 event_classifier，10 类）。"""

    def __init__(self):
        cfg = get_harness_config().perception
        self.enabled = cfg.enabled
        self._model_path = cfg.classifier_model
        self._pipe = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        from transformers import pipeline

        if not os.path.exists(self._model_path):
            logger.warning(f"classifier model not found at {self._model_path}, perception disabled")
            self.enabled = False
            self._loaded = True
            return
        self._pipe = pipeline(
            "text-classification",
            model=self._model_path,
            tokenizer=self._model_path,
            device=-1,
        )
        self._loaded = True
        logger.info("perception classifier loaded")

    def classify(self, text: str) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        self._load()
        if self._pipe is None:
            return None
        try:
            out = self._pipe(text[:500], top_k=1)[0]
            return {
                "category": out["label"],
                "category_confidence": float(out["score"]),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"perception classify failed: {e}")
            return None
