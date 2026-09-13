"""高德 POI 地理编码：把"小区名/道路名/地标"精确到坐标。

用途：地图洞察"点击位置 → 弹该位置常见诉求"的小区级定位。
依赖：.env 的 AMAP_KEY（高德 Web服务 key，被 gitignore 排除）。
API：amap /v3/place/text（POI 关键词搜索，精确到楼栋/小区/道路）。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests
from loguru import logger

_BASE = "https://restapi.amap.com/v3/place/text"

_KEY_ENV = "AMAP_KEY"


class PoiGeocoder:
    def __init__(self):
        self.key = os.getenv(_KEY_ENV, "").strip()
        if not self.key:
            logger.warning("AMAP_KEY 未配置（请在 .env 填写），POI 定位不可用")

    @property
    def available(self) -> bool:
        return bool(self.key)

    def search(self, keyword: str, city: Optional[str] = None, limit: int = 5) -> list[dict[str, Any]]:
        """高德 POI 关键词搜索，返回 [{name, address, lng, lat, district, type}]。"""
        if not self.key or not keyword:
            return []
        params = {"keywords": keyword, "key": self.key, "offset": limit, "extensions": "base", "page": 1}
        if city:
            params["city"] = city
        try:
            r = requests.get(_BASE, params=params, timeout=6)
            data = r.json()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"amap poi failed for {keyword!r}: {e}")
            return []
        if data.get("status") != "1":
            logger.warning(f"amap poi resp status !=1 for {keyword!r}: {data.get('info')}")
            return []

        pois = []
        for p in data.get("pois", []):
            loc = (p.get("location") or "").split(",")
            if len(loc) == 2:
                try:
                    pois.append({
                        "name": p.get("name", ""),
                        "address": p.get("address", ""),
                        "district": p.get("adname", ""),
                        "type": p.get("type", ""),
                        "lng": float(loc[0]),
                        "lat": float(loc[1]),
                    })
                except (TypeError, ValueError):
                    continue
        return pois

    def resolve(self, keyword: str, city: Optional[str] = None) -> Optional[dict[str, Any]]:
        """取第一个命中，返回 {lng, lat, name, address, district} 或 None。"""
        pois = self.search(keyword, city=city)
        return pois[0] if pois else None


_poi: Optional[PoiGeocoder] = None


def get_poi() -> PoiGeocoder:
    global _poi
    if _poi is None:
        _poi = PoiGeocoder()
    return _poi


# 中文地点后缀（用于从留言文本正则抽取"小区/道路/地标"名称，无需 NER）
PLACE_SUFFIX = ["小区", "花园", "广场", "苑", "园", "城", "公寓", "大厦", "路", "街", "巷", "桥", "村", "镇", "街道", "学校", "医院", "公馆", "中心"]


def extract_place_names(text: str) -> list[str]:
    """从留言文本抽取疑似地点名（含常见后缀的短语），作为 POI 搜索关键词。

    注意：这是轻量抽取（CPU 快、无 GPU），召回有限但零成本；
    更准的可用已有 NER 模型（ner_finetuned_v2，需 GPU）。
    """
    import re

    if not text:
        return []
    names = []
    # 模式：任意 2~8 个汉字 + 地点后缀
    for m in re.finditer(r"[\u4e00-\u9fa5]{2,8}(?:" + "|".join(PLACE_SUFFIX) + ")", text):
        name = m.group(0)
        # 过滤明显非地点的组合（如"物业公司"里的"公司"不属于后缀，但"物业"会匹配"物业"？后缀不含"物业"，安全）
        if name not in names:
            names.append(name)
    return names[:5]
