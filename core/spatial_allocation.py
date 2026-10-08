from __future__ import annotations

from shapely.geometry import shape, mapping, box


def build_allocation_feature_collection(field_geojson: dict, allocation_df, name_col: str = "RU") -> dict:
    """Split a user polygon into contiguous visual zones proportional to optimized shares.

    This is an indicative cartographic allocation only. It does not claim sub-field
    agronomic suitability because within-field soil/moisture/terrain layers are not yet
    used by the optimizer.
    """
    if not field_geojson or allocation_df is None or len(allocation_df) == 0:
        return {"type":"FeatureCollection","features":[]}
    geom=shape(field_geojson)
    if geom.is_empty or geom.area <= 0:
        return {"type":"FeatureCollection","features":[]}
    minx,miny,maxx,maxy=geom.bounds
    width=maxx-minx
    if width <= 0:
        return {"type":"FeatureCollection","features":[]}
    shares=allocation_df['share'].astype(float).clip(lower=0).to_numpy()
    total=float(shares.sum())
    if total <= 0:
        return {"type":"FeatureCollection","features":[]}
    shares=shares/total
    features=[]; x0=minx
    for idx,(_,row) in enumerate(allocation_df.iterrows()):
        x1=maxx if idx==len(allocation_df)-1 else x0+width*float(shares[idx])
        part=geom.intersection(box(x0,miny,x1,maxy))
        x0=x1
        if part.is_empty: continue
        features.append({
            "type":"Feature",
            "geometry":mapping(part),
            "properties":{
                "crop":str(row.get(name_col,row.get('product','Crop'))),
                "share_pct":round(float(row.get('share',0))*100,1),
                "area_ha":round(float(row.get('area_ha',0)),2),
                "visualization_only":True,
            }
        })
    return {"type":"FeatureCollection","features":features}
