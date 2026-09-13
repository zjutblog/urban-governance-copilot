"""离线地理编码：文本地点 -> 经纬度。

流程：cpca 抽取省市区（离线）-> 查行政区划中心点表（DataV 数据，离线）。
带内存缓存，避免重复计算。
"""
from __future__ import annotations

import os
import math
from typing import Any, Optional

import cpca
import pandas as pd
from loguru import logger

_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "region_centers.csv",
)


def haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """两点球面距离（公里）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Geocoder:
    def __init__(self, csv_path: str = _CSV_PATH):
        self.df = pd.read_csv(csv_path, dtype=str)
        # 构建索引
        self._district = self.df[self.df["level"] == "district"].set_index("district")
        self._city = self.df[self.df["level"] == "city"].set_index("city")
        self._province = self.df[self.df["level"] == "province"].set_index("province")
        self._cache: dict[str, Optional[dict[str, Any]]] = {}

    def _lookup(self, prov, city, dist) -> Optional[dict[str, Any]]:
        if dist and dist in self._district.index:
            r = self._district.loc[dist]
            return self._make(r["province"], r["city"], dist, r["lng"], r["lat"], "district")
        if city and city in self._city.index:
            r = self._city.loc[city]
            return self._make(r["province"], city, "", r["lng"], r["lat"], "city")
        if prov and prov in self._province.index:
            r = self._province.loc[prov]
            return self._make(prov, "", "", r["lng"], r["lat"], "province")
        return None

    @staticmethod
    def _make(prov, city, dist, lng, lat, level) -> Optional[dict[str, Any]]:
        try:
            return {
                "province": prov,
                "city": city,
                "district": dist,
                "lng": float(lng),
                "lat": float(lat),
                "level": level,
            }
        except (TypeError, ValueError):
            return None

    def geocode(self, text: str) -> Optional[dict[str, Any]]:
        text = (text or "").strip()
        if not text:
            return None
        if text in self._cache:
            return self._cache[text]

        try:
            r = cpca.transform([text]).iloc[0]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cpca failed for {text!r}: {e}")
            self._cache[text] = None
            return None

        prov = None if pd.isna(r["省"]) else str(r["省"])
        city = None if pd.isna(r["市"]) else str(r["市"])
        dist = None if pd.isna(r["区"]) else str(r["区"])

        result = self._lookup(prov, city, dist)
        self._cache[text] = result
        return result

    def geocode_batch(self, texts: list[str]) -> list[Optional[dict[str, Any]]]:
        return [self.geocode(t) for t in texts]


_geocoder: Optional[Geocoder] = None


def get_geocoder() -> Geocoder:
    global _geocoder
    if _geocoder is None:
        _geocoder = Geocoder()
        logger.info("geocoder loaded")
    return _geocoder
