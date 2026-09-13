"""应用层缓存：embedding / 检索 / 响应缓存，带 TTL。

GPU 上的 KV-cache 属推理层（vLLM prefix cache）；这里是 CPU 上可落地的
应用层缓存，弥补本机无法使用推理层 prefix cache 的缺口。
"""
from __future__ import annotations

import time
from typing import Any, Optional


class Cache:
    def __init__(self, default_ttl: float = 600.0):
        self._store: dict[str, tuple[float, Any]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        expires, value = item
        if time.time() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        self._store[key] = (time.time() + (ttl or self.default_ttl), value)

    def clear(self):
        self._store.clear()
