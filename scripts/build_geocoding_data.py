# -*- coding: utf-8 -*-
"""构建离线行政区划中心点表（省/市/区县 -> 经纬度）。

数据源：阿里云 DataV 行政区划 GeoJSON（国内 CDN，无 key）。
输出：data/region_centers.csv
"""
import csv
import json
import os
import time
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "region_centers.csv")


def get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(1.0)


def center_of(p):
    c = p.get("center") or p.get("centroid")
    if not c:
        return None, None
    return float(c[0]), float(c[1])


def main():
    rows = []
    prov_data = get("https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json")

    for pf in prov_data.get("features", []):
        p = pf["properties"]
        prov_name = p["name"]
        prov_code = p["adcode"]
        plng, plat = center_of(p)
        rows.append([prov_name, "", "", plng, plat, "province"])

        try:
            sub = get(f"https://geo.datav.aliyun.com/areas_v3/bound/{prov_code}_full.json")
        except Exception as e:  # noqa: BLE001
            print(f"skip province {prov_name}: {e}")
            continue

        levels = {f["properties"].get("level") for f in sub.get("features", [])}
        if "district" in levels:
            # 直辖市：直接是区县
            for df_ in sub.get("features", []):
                d = df_["properties"]
                dlng, dlat = center_of(d)
                rows.append([prov_name, prov_name, d["name"], dlng, dlat, "district"])
        else:
            for cf in sub.get("features", []):
                c = cf["properties"]
                city_name = c["name"]
                city_code = c["adcode"]
                clng, clat = center_of(c)
                rows.append([prov_name, city_name, "", clng, clat, "city"])
                try:
                    time.sleep(0.05)
                    city_sub = get(f"https://geo.datav.aliyun.com/areas_v3/bound/{city_code}_full.json")
                    for df_ in city_sub.get("features", []):
                        d = df_["properties"]
                        dlng, dlat = center_of(d)
                        rows.append([prov_name, city_name, d["name"], dlng, dlat, "district"])
                except Exception as e:  # noqa: BLE001
                    print(f"  skip city {city_name}: {e}")
        time.sleep(0.1)
        print(f"done province {prov_name} ({prov_code})")

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["province", "city", "district", "lng", "lat", "level"])
        w.writerows(rows)

    print(f"total rows: {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
