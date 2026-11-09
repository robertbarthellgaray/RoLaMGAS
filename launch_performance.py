"""Query NASA LSP's public high-energy performance form; cache exact results.

Not an official API. The parser fails explicitly if NASA changes its form/table.
Only public C3 inputs are sent; source/vehicle ground rules accompany each row.
"""
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime,timezone,timedelta
import argparse,hashlib,http.cookiejar,json,math,re,time,urllib.parse,urllib.request
from network import tls_context

BASE='https://elvperf.ksc.nasa.gov/Pages/'
PREFIX='ctl00$cphPageBody$'

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__();self.fields={};self.select=None;self.options=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='input' and a.get('name') and 'disabled' not in a and a.get('type')!='submit' and (a.get('type') not in ('radio','checkbox') or 'checked' in a):
            self.fields[a['name']]=a.get('value','')
        elif tag=='select' and 'disabled' not in a:self.select=a.get('name');self.options=[]
        elif tag=='option' and self.select:self.options.append((a.get('value',''),'selected' in a))
    def handle_endtag(self,tag):
        if tag=='select' and self.select:
            if self.options:self.fields[self.select]=next((v for v,selected in self.options if selected),self.options[0][0])
            self.select=None

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
        elif tag in ('br','li') and self.cell is not None:self.cell.append(' | ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip());self.cell=None
        elif tag=='tr' and self.row:self.rows.append(self.row);self.row=None

def checked_c3(value):
    try:value=float(value)
    except (ValueError,TypeError,OverflowError) as exc:raise ValueError('C3 must be a finite number') from exc
    if not math.isfinite(value) or not 0<=value<=250:raise ValueError('NASA capacity lookup supports finite C3 from 0 to 250 km²/s²')
    return value

def parse_result(html,c3):
    c3=checked_c3(c3);p=TableParser();p.feed(html)
    pairs={r[0].strip(':'):r[1] for r in p.rows if len(r)==2}
    try:reported=float(next(v for k,v in pairs.items() if k.startswith('C3')))
    except (StopIteration,ValueError):raise ValueError('NASA did not return a high-energy result table. Its website may have changed, or this C3 may be outside its supported range.')
    if abs(reported-c3)>1e-8 or pairs.get('Orbit Class')!='High Energy':raise ValueError('NASA returned different launch conditions; no capacities were accepted')
    no_results='There are no results.' in html
    if not no_results and not any(len(r)==7 and r[1]=='Vehicle' and 'Capability' in r[3] for r in p.rows):raise ValueError('NASA performance table format changed')
    vehicles=[]
    for row in p.rows:
        if len(row)!=7 or row[1]=='Vehicle':continue
        capability=row[3].replace(',','')
        if not re.fullmatch(r'\d+(?:\.\d+)?',capability):continue
        name,site,mass,fairing,adapter,rules=row[1:]
        vehicles.append(dict(vehicle=name.replace(' | ',' '),launch_site=site,capacity_kg=float(mass.replace(',','')),fairing=fairing,adapter=adapter,
                             ground_rules=rules.removeprefix('Click To Expand').strip(' |')))
    if not vehicles and not no_results:raise ValueError('NASA returned no numeric vehicle capabilities for this C3')
    return dict(schema_version=1,source='NASA Launch Services Program / NLS-II public performance website',
        source_url=BASE+'Results.aspx',query_url=BASE+'Query.aspx',c3_km2_s2=c3,orbit_class='High Energy',
        retrieved_at=datetime.now(timezone.utc).isoformat(),source_html_sha256=hashlib.sha256(html.encode()).hexdigest(),
        assumptions='NASA NLS-II high-energy ground rules, instantaneous launch attempt, configuration-specific recovery and adapter assumptions. Mission-specific reserves, launch-window requirements and contractual details can change capacity.',
        vehicles=vehicles,availability='no_vehicles_listed' if no_results else 'capacities_returned')

class NASAClient:
    def __init__(self):
        jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.HTTPSHandler(context=tls_context()))
    def _request(self,page,fields=None):
        headers={'User-Agent':'RoLaMGAS launch-performance lookup/1','Referer':BASE+'Query.aspx'}
        data=urllib.parse.urlencode(fields).encode() if fields is not None else None
        request=urllib.request.Request(BASE+page,data=data,headers=headers)
        with self.opener.open(request,timeout=20) as response:
            raw=response.read(1500001)
            if len(raw)>1500000:raise ValueError('NASA response exceeds the expected form size')
            if not response.url.startswith(BASE):raise ValueError('Unexpected NASA response location')
            text=raw.decode('utf-8')
        return text
    def query(self,c3):
        c3=checked_c3(c3)
        form=FormParser();form.feed(self._request('Query.aspx'))
        if PREFIX+'rblOrbit' not in form.fields:raise ValueError('NASA query form unavailable; open the source website to check its status')
        form.fields.update({PREFIX+'rblOrbit':'High Energy','__EVENTTARGET':PREFIX+'rblOrbit$2','__EVENTARGUMENT':''})
        high=FormParser();high.feed(self._request('Query.aspx',form.fields))
        if high.fields.get(PREFIX+'rblOrbit')!='High Energy' or PREFIX+'tbC3' not in high.fields:raise ValueError('NASA high-energy selection failed')
        high.fields.update({PREFIX+'tbC3':format(c3,'.12g'),PREFIX+'btnGenerate':'Execute','__EVENTTARGET':'','__EVENTARGUMENT':''})
        return parse_result(self._request('Results.aspx',high.fields),c3)

def capacity_query(c3,cache,refresh=False,client=None):
    c3=checked_c3(c3);cache=Path(cache);key=hashlib.sha256(format(c3,'.12g').encode()).hexdigest()[:20];path=cache/(key+'.json')
    if path.is_file() and not refresh:
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            if abs(value['c3_km2_s2']-c3)<1e-9 and datetime.now(timezone.utc)-datetime.fromisoformat(value['retrieved_at'])<timedelta(days=30):
                return dict(value,from_cache=True)
        except (KeyError,ValueError,TypeError):pass
    value=(client or NASAClient()).query(c3);cache.mkdir(parents=True,exist_ok=True)
    from ephemeris import atomic_json
    atomic_json(path,value)
    return dict(value,from_cache=False)

def build_curves(grid,cache,output):
    client=NASAClient();vehicles={};queries=[]
    for c3 in sorted(set(map(checked_c3,grid))):
        doc=capacity_query(c3,cache,client=client);queries.append(dict(c3=c3,retrieved_at=doc['retrieved_at'],sha256=doc['source_html_sha256']))
        for row in doc['vehicles']:
            key=row['vehicle']+' | '+row['launch_site']
            entry=vehicles.setdefault(key,dict(row,points=[]));entry.pop('capacity_kg',None);entry['points'].append([c3,row['capacity_kg']])
        print('NASA C3',c3,':',len(doc['vehicles']),'vehicle configurations',flush=True)
        if not doc['from_cache']:time.sleep(.25)
    result=dict(schema_version=1,source=doc['source'],source_url=BASE+'Query.aspx',retrieved_at=max(q['retrieved_at'] for q in queries),
                assumptions=doc['assumptions'],interpolation='Linear between cached samples only; no extrapolation or inference across missing vehicle samples.',
                queries=queries,vehicles=list(vehicles.values()))
    from ephemeris import atomic_json
    atomic_json(output,result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--c3',type=float);p.add_argument('--cache',type=Path,default=Path('cache/launch_performance'));p.add_argument('--refresh',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--curve-grid',type=float,nargs='+');args=p.parse_args()
    if args.curve_grid:
        if not args.output:p.error('--curve-grid requires --output')
        return build_curves(args.curve_grid,args.cache,args.output)
    if args.c3 is None:p.error('--c3 or --curve-grid is required')
    d=capacity_query(args.c3,args.cache,args.refresh)
    if args.output:
        from ephemeris import atomic_json
        atomic_json(args.output,d)
    print('NASA C3:',d['c3_km2_s2'],'km²/s²; retrieved',d['retrieved_at'])
    for row in d['vehicles']:print(row['vehicle'],'|',row['launch_site'],'|',format(row['capacity_kg'],',.0f'),'kg')
    print(d['assumptions'])
if __name__=='__main__':main()
