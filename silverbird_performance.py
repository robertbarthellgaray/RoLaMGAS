"""Collect permitted scenario outputs from John Schilling's hosted calculator.

Only public form choices and computed results are used. No launcher engineering
database or third-party calculator Javascript is bundled or redistributed.
"""
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone
import argparse, ast, hashlib, json, math, re, time, urllib.parse, urllib.request
from network import tls_context

ROOT=Path(__file__).resolve().parent
SOURCE='https://silverbirdastronautics.com/LVperform.html'
ENDPOINT='https://silverbirdastronautics.com/cgi-bin/LVPcalc.pl'
SCRIPT='https://silverbirdastronautics.com/LaunchScriptSB7.js'
GRID=[0,5,10,15,20,30,40,60,100,158,200]
# IDs select only documented public form choices, not engineering records.
SPECS=[
 ('f9-exp','USA','Falcon 9 Block 5 · expendable','208',[5,1,2,0],'001'),
 ('fh-exp','USA','Falcon Heavy · expendable','209',[1,1,2,0],'001'),
 ('fh-recovery','USA','Falcon Heavy · booster and core ocean recovery','209',[2,2,2,0],'001'),
 ('vulcan-6','USA','Vulcan VC6S','213',[7,0,0,0],'001'),
 ('sls-1','USA','SLS Block 1 · iCPS · cargo','210',[1,2,1,2],'001'),
 ('lm5','China','Long March 5 / CZ-5','212',[1,1,1,2],'022'),
 ('lm3b','China','Long March 3B','109',[6,0,0,0],'009'),
 ('ariane62','Europe','Ariane 62','219',[1,1,0,0],'010'),
 ('ariane64','Europe','Ariane 64','219',[2,1,0,0],'010'),
 ('pslv-six','India','PSLV · six boosters','111',[4,0,0,0],'011'),
 ('gslv2','India','GSLV Mark II','121',[2,0,0,0],'011'),
 ('lvm3','India','LVM3 / GSLV Mark III','121',[3,0,0,0],'011'),
 ('proton-m','Russia','Proton M · Breeze M','115',[2,2,2,0],'013'),
 ('soyuz-21b','Russia','Soyuz 2-1B · Fregat','116',[5,2,5,0],'013'),
 ('angara-a5','Russia','Angara A5 · Breeze M','204',[4,2,1,0],'014'),
 ('h3-24','Japan','H3-24','125',[2,1,0,0],'012'),
 ('electron-photon','USA / New Zealand','Electron · Photon IP','215',[4,1,0,0],'024'),
]

EXPECTED_OPTIONS={'f9-exp': ['Block 5', 'None', 'Long'], 'fh-exp': ['None', 'None', 'Long'], 'fh-recovery': ['Ocean Recovery', 'Ocean Recovery', 'Long'], 'vulcan-6': ['Vulcan VC6S'], 'sls-1': ['Block 1', 'iCPS', 'FSB', '27-meter Cargo'], 'lm5': ['Long March 5', 'CZ-5', 'None', 'Long'], 'lm3b': ['Long March LM-3B'], 'ariane62': ['Ariane 62', '14-meter'], 'ariane64': ['Ariane 64', '14-meter'], 'pslv-six': ['6'], 'gslv2': ['Mark II'], 'lvm3': ['Mark III'], 'proton-m': ['Proton M', 'Breeze M', 'Commercial 4.35x13.3m'], 'soyuz-21b': ['Soyuz 2-1B', 'Fregat', 'Type ST'], 'angara-a5': ['Angara A5', 'Breeze-M', '4.35-meter'], 'h3-24': ['H3-24', '5.2-meter standard'], 'electron-photon': ['Photon IP', '1.2-meter standard']}

def checked_c3(value):
    value=float(value)
    if not math.isfinite(value) or not 0<=value<=200:raise ValueError('SilverBird C3 must be finite and between 0 and 200 km²/s²')
    return value

def read_url(url,fields=None):
    headers={'User-Agent':'RoLaMGAS-permitted-launch-scenarios/1.0','Referer':SOURCE}
    request=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode() if fields else None,headers=headers)
    with urllib.request.urlopen(request,context=tls_context(),timeout=100) as response:
        if urllib.parse.urlsplit(response.url).hostname!='silverbirdastronautics.com':raise ValueError('Unexpected calculator redirect')
        raw=response.read(500001)
        if len(raw)>500000:raise ValueError('Unexpected calculator response size')
    return raw.decode('utf-8',errors='strict')

def parse_catalog(script):
    def values(text):return ast.literal_eval('['+text+']')
    named={name:values(text) for name,text in re.findall(r'var\s+(cname|cflag|cval|sname|sflag|sval)\s*=\s*new Array\((.*?)\);',script)}
    tables={name:[values(m) for m in re.findall(name+r'\[[^\]]+\]\s*=\s*new Array\((.*?)\)[ \t]*;?(?=[ \t]*\r?$)',script,re.M)] for name in ('iswitch','jswitch','kswitch','lswitch','sswitch')}
    if set(named)!=set(('cname','cflag','cval','sname','sflag','sval')):raise ValueError('SilverBird form catalog changed')
    if len(tables['iswitch'])!=len(tables['sswitch']):raise ValueError('SilverBird site table changed')
    return dict(named=named,tables=tables,script_sha256=hashlib.sha256(script.encode()).hexdigest())

def scenario(spec,catalog,c3):
    key,country,label,family,choices,site=spec;c3=checked_c3(c3)
    if family not in catalog['named']['cval']:raise ValueError('Launcher is no longer in the source Current catalog: '+label)
    i,j,k,l=choices;tables=catalog['tables'];index=next((n for n,r in enumerate(tables['iswitch']) if str(r[0])==family),None)
    if index is None:raise ValueError('Launcher configuration missing: '+label)
    row=tables['iswitch'][index];labels=[]
    if not 1<=i<=int(row[6]):raise ValueError('Launcher model changed: '+label)
    labels.append(row[6+i])
    for table,selected in [('jswitch',j),('kswitch',k),('lswitch',l)]:
        options=next((r for r in tables[table] if str(r[0])==family and int(r[1])<=i<=int(r[2])),None)
        if options:
            if not 1<=selected<=int(options[4]):raise ValueError('Launcher option changed: '+label+' / '+table)
            labels.append(options[4+selected])
        elif selected:raise ValueError('Unexpected launcher option: '+label+' / '+table)
    if key in EXPECTED_OPTIONS and labels!=EXPECTED_OPTIONS[key]:raise ValueError('Source configuration changed; review preset '+key)
    # The website indexes sites by configuration-row index, not family ID.
    sites=tables['sswitch'][index]
    if site not in sites[2:2+int(sites[1])]:raise ValueError('Source launch site changed: '+label)
    fields=dict(LVclass='1',lvf=family,lvi=str(i),lvj=str(j),lvk=str(k),lvl=str(l),LSclass='1',lsi=site,
                isEscape='1',apo=format(c3,'.12g'),peri='200',inc='0',Ttype='3' if int(row[2])==3 else str(row[2]),
                isGCS='1',CalMode='2',EOLburn='0')
    return fields,labels

class ResultTable(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=[];self.cell=None
    def end_cell(self):
        if self.cell is not None:self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).replace('\xa0',' ').strip());self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.end_cell();self.rows.append(self.row);self.row=[]
        elif tag in ('td','th'):self.end_cell();self.cell=[]
    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if tag in ('td','th'):self.end_cell()
        elif tag=='tr':self.end_cell();self.rows.append(self.row);self.row=[]

def parse_result(text,fields):
    parser=ResultTable();parser.feed(text);parser.end_cell();pairs={r[0].rstrip(': &nbsp'):r[1] for r in parser.rows+[parser.row] if len(r)==2}
    trajectory=pairs.get('Escape Trajectory','');match=re.search(r'C3\s*=\s*([-+\d.eE]+)\s*km2/s2,\s*([-+\d.eE]+)\s*deg',trajectory)
    if not match or abs(float(match[1])-float(fields['apo']))>1e-7 or abs(float(match[2])-float(fields['inc']))>1e-7:raise ValueError('SilverBird returned different or missing escape conditions')
    if not pairs.get('Launch Vehicle') or not pairs.get('Launch Site'):raise ValueError('Missing source launcher or launch site')
    payload=re.fullmatch(r'\s*([\d,.]+)\s*kg\s*',pairs.get('Estimated Payload',''))
    interval=re.fullmatch(r'\s*([\d,.]+)\s*-\s*([\d,.]+)\s*kg\s*',pairs.get('95% Confidence Interval',''))
    if not payload or not interval:raise ValueError('SilverBird did not return a numeric payload and uncertainty interval')
    mass=float(payload[1].replace(',',''));lo,hi=(float(x.replace(',','')) for x in interval.groups())
    if not 0<=lo<=mass<=hi:raise ValueError('Invalid source payload interval')
    return dict(capacity_kg=mass,confidence95_kg=[lo,hi],reported_vehicle=pairs.get('Launch Vehicle'),launch_site=pairs.get('Launch Site'),
        c3_km2_s2=float(match[1]),declination_deg=float(match[2]),retrieved_at=datetime.now(timezone.utc).isoformat(),source_html_sha256=hashlib.sha256(text.encode()).hexdigest())

class SilverBirdClient:
    def __init__(self,cache,refresh_catalog=False):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True);self.last_request=0.
        path=self.cache/'form_catalog.json'
        if path.exists() and not refresh_catalog and time.time()-path.stat().st_mtime<30*86400:self.catalog=json.loads(path.read_text(encoding='utf-8'))
        else:
            self.catalog=parse_catalog(read_url(SCRIPT));path.write_text(json.dumps(self.catalog),encoding='utf-8')
    def query(self,spec,c3,refresh=False):
        fields,labels=scenario(spec,self.catalog,c3)
        key=hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest();path=self.cache/(key+'.json')
        if path.exists() and not refresh:
            value=json.loads(path.read_text(encoding='utf-8'))
            if value.get('fields')==fields:return dict(value,from_cache=True)
        time.sleep(max(0,1-(time.monotonic()-self.last_request)));self.last_request=time.monotonic()
        text=read_url(ENDPOINT,fields);result=parse_result(text,fields)
        value=dict(result,fields=fields,configuration_labels=labels,form_catalog_sha256=self.catalog['script_sha256'],source_url=SOURCE)
        path.write_text(json.dumps(value,indent=2),encoding='utf-8')
        (self.cache/(key+'.html')).write_text(text,encoding='utf-8')
        return dict(value,from_cache=False)

def collect(grid=GRID,countries=None,refresh=False):
    from ephemeris import atomic_json
    client=SilverBirdClient(ROOT/'cache/silverbird',refresh_catalog=refresh);vehicles=[];failures=[]
    specs=[s for s in SPECS if not countries or any(c in countries for c in s[1].split(' / '))]
    if not specs:raise ValueError('No supported launcher presets for these countries: '+str(countries))
    for spec in specs:
        key,country,label,*_=spec;points=[];intervals=[];queries=[]
        for c3 in sorted(set(map(checked_c3,grid))):
            try:
                d=client.query(spec,c3,refresh);points.append([c3,d['capacity_kg']]);intervals.append([c3,*d['confidence95_kg']]);queries.append(d)
                print(label,'C3',c3,'=',d['capacity_kg'],'kg',flush=True)
            except (ValueError,OSError) as exc:
                failures.append(dict(vehicle=key,c3=c3,error=str(exc)));print('UNAVAILABLE',label,c3,str(exc),flush=True)
        if not points:continue
        sample=queries[0]
        vehicles.append(dict(silverbird_id=key,country=country,countries=country.split(' / '),vehicle=label+' · SilverBird',
            launch_site=sample['launch_site'],points=points,query_grid_c3=sorted(set(map(float,grid))),confidence95_points=intervals,
            source_label='SilverBird model · John Schilling',source_url=SOURCE,data_kind='silverbird_model',
            retrieved_at=max(q['retrieved_at'] for q in queries),queries=[{k:q[k] for k in ('c3_km2_s2','capacity_kg','reported_vehicle','fields','configuration_labels','retrieved_at','source_html_sha256','form_catalog_sha256')} for q in queries],
            ground_rules='Hosted SilverBird calculator output, used with permission. Escape trajectory; 200 km perigee; departure declination 0 degrees; mixed calibration; no end-of-life disposal burn. Configuration: '+', '.join(sample['configuration_labels'])+'. Trajectory mode '+sample['fields']['Ttype']+' as supported by the source form. Payload includes attachment fittings/adapters. Source 95% intervals are model uncertainty, not a provider guarantee. Linear interpolation only between neighboring successful samples; no extrapolation.'))
    snapshot=dict(schema_version=1,source='SilverBird Astronautics Launch Vehicle Performance Calculator · John Schilling',source_url=SOURCE,
        retrieved_at=datetime.now(timezone.utc).isoformat(),permission='Project-owner confirmation 2026-11-22: permitted use of hosted calculator scenarios; underlying engineering database excluded.',vehicles=vehicles,unavailable_samples=failures)
    atomic_json(ROOT/'studies/international_launch_performance/silverbird_scenarios.json',snapshot)
    if len(vehicles)!=len(specs):raise ValueError('One or more requested launchers returned no usable samples; existing published curves were not replaced')
    for name in ('gui_assets/launch_performance_curves.json','docs/data/launch_performance_curves.json'):
        path=ROOT/name;doc=json.loads(path.read_text(encoding='utf-8'))
        replaced={s[0] for s in specs};doc['vehicles']=[v for v in doc['vehicles'] if v.get('silverbird_id') not in replaced]+vehicles
        doc['silverbird_retrieved_at']=snapshot['retrieved_at'];atomic_json(path,doc)
    print('Saved',len(vehicles),'launcher configurations,',sum(len(v['points']) for v in vehicles),'successful samples and',len(failures),'unavailable samples.',flush=True)
    return snapshot

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--grid',type=float,nargs='+',default=GRID);p.add_argument('--countries',nargs='+');p.add_argument('--refresh',action='store_true');a=p.parse_args();collect(a.grid,a.countries,a.refresh)
