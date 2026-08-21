
from shapely.geometry import shape
from pyproj import Geod
_GEOD=Geod(ellps="WGS84")
def polygon_area_hectares(g):
    geom=shape(g)
    if geom.geom_type not in ("Polygon","MultiPolygon"):
        raise ValueError("Polygon required.")
    area_m2,_=_GEOD.geometry_area_perimeter(geom)
    return abs(area_m2)/10000
def representative_point(g):
    p=shape(g).representative_point()
    return float(p.y),float(p.x)
