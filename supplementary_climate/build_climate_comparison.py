"""Build Apr-Sep district comparisons for observed 1995-2014 baseline and 2021-2025, without asserting causality."""
import csv,sys,collections,statistics,pathlib
inp=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);data=collections.defaultdict(list)
with inp.open(encoding='utf-8-sig',newline='') as f:
 for row in csv.DictReader(f):
  if 4<=int(row['month'])<=9:data[(row['territory_code'],row['territory_name'],int(row['year']))].append(row)
records=collections.defaultdict(dict)
for (code,name,year),rows in data.items():
 assert len(rows)==6
 t=statistics.mean(float(x['T2M']) for x in rows)
 rain=sum(float(x['PRECTOTCORR_MONTH_MM']) for x in rows)
 records[(code,name)][year]=(t,rain)
with out.open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['territory_code','territory_name','baseline_1995_2014_T2M_C','recent_2021_2025_T2M_C','recent_minus_baseline_T2M_C','baseline_1995_2014_season_rain_mm','recent_2021_2025_season_rain_mm','recent_minus_baseline_rain_pct'])
 for (code,name),series in sorted(records.items()):
  def avg(a,b,col):return statistics.mean(series[y][col] for y in range(a,b+1))
  t0,t1=avg(1995,2014,0),avg(2021,2025,0)
  r0,r1=avg(1995,2014,1),avg(2021,2025,1)
  w.writerow([code,name,round(t0,4),round(t1,4),round(t1-t0,4),round(r0,4),round(r1,4),round((r1/r0-1)*100,4) if r0 else ''])
