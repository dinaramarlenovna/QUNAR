"""Optional mapped soil-property context; NOT an automatic fertility score.

ISRIC SoilGrids REST API (beta) is occasionally unavailable and currently
publicly marked paused. Run only on explicit user request; never fill unavailable
soil chemistry with guessed district means or zeros.  Single representative
point: NOT a polygon soil average.
"""
from math import isfinite
import requests

API='https://rest.isric.org/soilgrids/v2.0/properties/query'
DOCS='https://docs.isric.org/globaldata/soilgrids/index.html'
PROPERTIES=('clay','sand','silt','phh2o','soc','nitrogen','cec')
DEPTHS=('0-5cm','5-15cm','15-30cm')
UNIT_HINTS={
 'clay': '%', 'sand':'%', 'silt':'%', 'phh2o':'pH',
 'soc':'g/kg', 'nitrogen':'g/kg', 'cec':'cmol(c)/kg',
}


def parse_soilgrids_response(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('properties'),dict):
        raise ValueError('Invalid SoilGrids response')
    layers=payload['properties'].get('layers')
    if not isinstance(layers,list) or not layers:
        raise ValueError('SoilGrids has no available soil layers')
    records={}
    for layer in layers:
        name=layer.get('name')
        if name not in PROPERTIES:continue
        unit=layer.get('unit_measure') or {}
        factor=unit.get('d_factor', 1)
        try:factor=float(factor)
        except (ValueError,TypeError):raise ValueError('Invalid SoilGrids depth scaling')
        if not isfinite(factor) or factor<=0:raise ValueError('Invalid SoilGrids scaling')
        for depth in layer.get('depths',[]):
            label=depth.get('label')
            if label not in DEPTHS:continue
            measured=(depth.get('values') or {}).get('mean')
            if measured is None:continue
            val=float(measured)/factor
            if not isfinite(val):continue
            records.setdefault(name,{})[label]=val
    if not records:raise ValueError('SoilGrids has no non-missing sampled values')
    return {'values':records,'units':UNIT_HINTS,'source':'ISRIC SoilGrids 250 m gridded predictions',
            'coverage':'one user-location sample, not a polygon mean or a field measurement',
            'status':'reference_estimate_not_measured_fertility',
            'note':'pH, carbon, texture, nitrogen and CEC are separate predicted soil properties; no validated fertility or yield index is inferred.'}


def fetch_soilgrids_reference(latitude,longitude,*,request_get=None,timeout=15):
    lat=float(latitude);lon=float(longitude)
    if not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Invalid soil sample coordinates')
    get=request_get or requests.get
    response=get(API,params={'lat':lat,'lon':lon,
        'property':list(PROPERTIES),'depth':list(DEPTHS),'value':'mean'},timeout=timeout)
    response.raise_for_status()
    data=parse_soilgrids_response(response.json())
    data['latitude']=lat;data['longitude']=lon
    return data


def indicative_texture_from_soilgrids(soil_reference):
    """Approximate soil TEXTURE from mapped fractions, NOT measured fertility/FC.

    All 0-30 cm depth intervals required. Class intentionally coarse and always
    returned with explicit provenance; FAO presets are an optional scenario.
    """
    layers=soil_reference.get('values') or {}
    fractions={}
    for key in ('sand','clay','silt'):
        points=layers.get(key) or {}
        if any(depth not in points for depth in DEPTHS):
            raise ValueError('Full 0-30 cm mapped texture required')
        fractions[key]=(5*float(points['0-5cm'])+10*float(points['5-15cm'])+
                        15*float(points['15-30cm']))/30
    if not all(0<=v<=100 and isfinite(v) for v in fractions.values()):
        raise ValueError('Invalid mapped particle fractions')
    if not 90<=sum(fractions.values())<=110:
        raise ValueError('Soil texture fractions inconsistent')
    sand,clay,silt=(fractions[k] for k in ('sand','clay','silt'))
    if sand>=85 and clay<10: kind='sand'
    elif sand>=60 and clay<25:kind='sandy_loam'
    elif clay>=32:kind='clay_loam'
    elif silt>=50:kind='silt_loam'
    else:kind='loam'
    return {'faopreset':kind,'texture_fractions_pct':fractions,
            'source':'SoilGrids mapped 0-30cm texture -> indicative FAO AquaCrop scenario profile',
            'status':'estimated texture category; not measured field capacity/wilting point'}
