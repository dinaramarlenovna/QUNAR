"""Reproducible region and district area-weighted NASA POWER monthly cache.
Usage: python build_nasa_aggregates.py INPUT.zip OUTPUT_DIR
Monthly POWER parameter PRECTOTCORR is mm/day (monthly mean); ALLSKY_SFC_SW_DWN MJ/m2/day.
Calendar YYYY13 annual aggregate records are intentionally discarded.
Nominal grid polygons are spatial attribution proxies, not validated native product footprints.
"""
import csv,json,zipfile,sys,math,calendar,collections,pathlib
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

PARAMS=['T2M','T2M_MAX','T2M_MIN','RH2M','WS2M','PS','ALLSKY_SFC_SW_DWN','PRECTOTCORR','GWETROOT']
MEAN_COLS=PARAMS

def run(zip_path,out_dir):
 out=pathlib.Path(out_dir);out.mkdir(parents=True,exist_ok=True)
 z=zipfile.ZipFile(zip_path); names=set(z.namelist())
 def member(n):
  opts=[n,n.replace('/','\\'),n.replace('\\','/')]
  return next((a for a in opts if a in names),None)
 def load(n):
  p=member(n)
  if not p:raise FileNotFoundError(n)
  return json.loads(z.read(p))
 manifest=load('manifest.json'); grid=load('grid_clipped.geojson');bounds=load('turkestan_admin_boundaries.geojson')
 cells=manifest['cells']; assert len(cells)==len(grid['features'])==65
 assert len(bounds['features'])==17
 transformer=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
 project=lambda geom:transform(transformer.transform,shape(geom))
 grid_geom={f['properties']['id']:project(f['geometry']) for f in grid['features']}
 districts={f['properties']['district_code']:(f['properties']['name'],project(f['geometry'])) for f in bounds['features']}
 assert len(districts)==17
 datasets={}; problems=[]; counts=collections.Counter(); parameter_units={}
 for c in cells:
  cid=c['id'];obj=load(c['monthly_file']); p=obj['properties']['parameter'];datasets[cid]=p
  if set(p)!=set(PARAMS):problems.append(('parameter_set',cid))
  for param in PARAMS:
   series=p.get(param,{})
   expected={f'{y}{m:02d}' for y in range(1995,2026) for m in range(1,13)}
   missing=expected-set(series)
   if missing:problems.append(('missing_months',cid,param,len(missing)))
   for month in expected&set(series):
    val=series[month]
    if val is None or not isinstance(val,(int,float)) or not math.isfinite(val) or val<=-990:
     counts[param+'_invalid']+=1
    else:counts[param+'_valid']+=1
   if any(k.endswith('13') for k in series):counts['annual_13_entries']+=1
 weights={}
 for code,(name,geom) in districts.items():
  intersections={cid:geom.intersection(g).area for cid,g in grid_geom.items() if geom.intersects(g)}
  intersections={k:v for k,v in intersections.items() if v>0}
  area=sum(intersections.values()); district_area=geom.area
  if area<=0:problems.append(('district_no_coverage',code))
  weights[code]={cid:v/area for cid,v in intersections.items()}
  coverage=area/district_area if district_area else 0
  if not (.97<=coverage<=1.03):problems.append(('district_coverage_ratio',code,round(coverage,5)))
 area_region={c['id']:float(c['region_intersection_km2']) for c in cells}
 total=sum(area_region.values());weights['REGION']={k:v/total for k,v in area_region.items()}
 def weighted_row(code,year,month):
  key=f'{year}{month:02d}'; w=weights[code];values={}
  for p in PARAMS:
   usable=[(frac,datasets[cid].get(p,{}).get(key)) for cid,frac in w.items()]
   valid=[(frac,v) for frac,v in usable if isinstance(v,(int,float)) and math.isfinite(v) and v>-990]
   retained=sum(frac for frac,_ in valid)
   values[p]=round(sum(frac*v for frac,v in valid)/retained,6) if retained>=.95 else ''
   if retained<.95:counts['below_95pct_coverage']+=1
  values['PRECTOTCORR_MONTH_MM']=round(values['PRECTOTCORR']*calendar.monthrange(year,month)[1],6) if values['PRECTOTCORR']!='' else ''
  return values
 output=['district_monthly_1995_2025.csv','region_monthly_1995_2025.csv']
 headers=['territory_code','territory_name','year','month']+PARAMS+['PRECTOTCORR_MONTH_MM']
 for index,fn in enumerate(output):
  territories=list(districts) if index==0 else ['REGION']
  with (out/fn).open('w',newline='',encoding='utf-8-sig') as fh:
   writer=csv.DictWriter(fh,fieldnames=headers);writer.writeheader()
   for code in territories:
    for year in range(1995,2026):
     for month in range(1,13):
      row={'territory_code':code,'territory_name':districts[code][0] if code!='REGION' else 'Turkestan Region','year':year,'month':month}
      row.update(weighted_row(code,year,month));writer.writerow(row)
 # transparent weights for reproducibility
 with (out/'district_cell_weights.csv').open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.writer(f);writer.writerow(['territory_code','cell_id','area_weight'])
  for code in districts:
   for cid,w in sorted(weights[code].items()):writer.writerow([code,cid,format(w,'.15g')])
 qa={'source_archive':pathlib.Path(zip_path).name,'period':'1995-2025','cell_count':len(cells),'territory_count':len(districts),
     'monthly_points_per_parameter_per_cell':372,'expected_cell_month_values_per_parameter':65*372,
     'valid_counts':{p:counts[p+'_valid'] for p in PARAMS},'invalid_counts':{p:counts[p+'_invalid'] for p in PARAMS},
     'annual_summary_entries_excluded':counts['annual_13_entries'],'coverage_under_95percent_parameter_rows':counts['below_95pct_coverage'],
     'errors':problems,'district_cell_weights_sum':{k:round(sum(v.values()),12) for k,v in weights.items()},
     'notes':['Spatial weight polygons are NOMINAL approximations; NASA POWER native parameter footprints differ, particularly solar radiation.',
       'Do not concatenate 13th annual records as months.', 'PRECTOTCORR is monthly mean rate (mm/day); convert to monthly total by multiplying days in calendar month.',
       'NASA T2M_MAX/T2M_MIN monthly extrema aggregation depends on API parameter semantics; they cannot reconstruct counts of days above 35/40/45 °C.',
       'Monthly inputs can support approximate monthly FAO-56 Penman-Monteith ET0 but daily heat-extreme indicators require daily source.',
       'Area-based district averages are gridded estimates, not weather station measurements.']}
 (out/'NASA_QA.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
 return qa
if __name__=='__main__':
 q=run(sys.argv[1],sys.argv[2]);print(json.dumps({k:v for k,v in q.items() if k not in ('district_cell_weights_sum','notes')},ensure_ascii=False,indent=2))
