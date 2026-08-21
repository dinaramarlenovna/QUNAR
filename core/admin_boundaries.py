from pathlib import Path
import json
from functools import lru_cache
from shapely.geometry import shape, Point
from shapely.ops import unary_union

BOUNDARY_FILE = Path(__file__).resolve().parents[1] / "data" / "turkestan_admin_boundaries.geojson"

@lru_cache(maxsize=1)
def load_boundaries():
    data = json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))
    out=[]
    for ft in data.get("features",[]):
        props=ft.get("properties",{})
        geom=shape(ft.get("geometry"))
        if not geom.is_valid:
            geom=geom.buffer(0)
        out.append({"district":props.get("district_code"),"coderayon":props.get("coderayon"),"name_ru":props.get("name"),"name_kk":props.get("name_kk"),"geometry":geom})
    return out

def detect_point(lat, lon):
    pt=Point(float(lon),float(lat))
    for rec in load_boundaries():
        if rec["geometry"].covers(pt):
            return {**{k:v for k,v in rec.items() if k!="geometry"},"share":1.0,"method":"official_polygon_point"}
    return None

def detect_polygon(geometry_geojson):
    if not geometry_geojson:
        return None
    geom=shape(geometry_geojson)
    if not geom.is_valid:
        geom=geom.buffer(0)
    if geom.is_empty or geom.area <= 0:
        return None
    # equal-area-ish local projection is not needed for ratios: same CRS area ratio is adequate at this local scale.
    matches=[]
    for rec in load_boundaries():
        inter=geom.intersection(rec["geometry"])
        if not inter.is_empty:
            matches.append((float(inter.area/geom.area),rec))
    if not matches:
        return None
    matches.sort(key=lambda x:x[0],reverse=True)
    share, rec=matches[0]
    return {**{k:v for k,v in rec.items() if k!="geometry"},"share":share,"method":"official_polygon_overlap",
            "all_matches":[{"district":r["district"],"share":s} for s,r in matches if s>0.001]}

@lru_cache(maxsize=1)
def boundary_geojson():
    return json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))
