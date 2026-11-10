"""Find official Decadal mission reports; cache PDFs locally for seed research.

python tools/fetch_decadal_reports.py --inventory
python tools/fetch_decadal_reports.py --ids vv2011_14_io_observer --extract
PDFs and extracted text stay in ignored cache/decadal_reports, not in releases.
"""
from pathlib import Path
import argparse,hashlib,json,re,sys,urllib.request,urllib.parse
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
from network import tls_context
ROOT=Path(__file__).resolve().parents[1]
INDEX='https://nap.nationalacademies.org/reports/13117/appendix_g.html'
NASA='https://science.nasa.gov/planetary-science/resources/documents/'
CATALOG=ROOT/'departure_seeds/decadal_sources.json'

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.href=None;self.label=[];self.heading_tag=None;self.heading_parts=[];self.heading='';self.section='';self.context={}
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href');self.label=[]
        if tag in ('h2','h3'):self.heading_tag=tag;self.heading_parts=[]
    def handle_data(self,data):
        if self.href:self.label.append(data)
        if self.heading_tag:self.heading_parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href:
            self.links.append((self.href,''.join(self.label).strip()));self.context[self.href]=(self.section,self.heading);self.href=None
        if tag==self.heading_tag:
            self.heading=' '.join(''.join(self.heading_parts).split())
            if tag=='h2':self.section=self.heading
            self.heading_tag=None

def download(url,maximum=64*1024*1024):
    parts=urllib.parse.urlsplit(url);url=urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path,safe='/%')))
    request=urllib.request.Request(url,headers={'User-Agent':'RoLaMGAS scientific report research/1'})
    with urllib.request.urlopen(request,context=tls_context(),timeout=50) as response:
        size=response.headers.get('Content-Length')
        if size and int(size)>maximum:raise ValueError('Report exceeds the configured 64 MiB download limit')
        raw=response.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Report exceeds the configured 64 MiB download limit')
    return raw

def inventory():
    reports=[]
    parser=Links();parser.feed(download(INDEX).decode('utf-8'))
    for href,label in parser.links:
        name=urllib.parse.unquote(href).split('/')[-1]
        if not name.lower().endswith('.pdf') or not name.startswith('App G '):continue
        ident='vv2011_'+re.sub('[^a-z0-9]+','_',name[6:-4].lower()).strip('_')
        url=urllib.parse.urljoin(INDEX,href);url=urllib.parse.quote(url,safe=':/%')
        reports.append(dict(id=ident,title=name[6:-4].replace('_',' '),cycle='2013–2022',url=url,index_url=INDEX))
    parser=Links();parser.feed(download(NASA).decode('utf-8'))
    for href,label in parser.links:
        name=urllib.parse.unquote(href).split('/')[-1]
        section,title=parser.context[href]
        if not name.lower().endswith('.pdf') or not ('/2020/' in href or 'Completed 2020' in section or 'Completed 2022' in section):continue
        prefix='owl2022_' if 'Completed 2022' in section else 'owl2020_'
        ident=prefix+re.sub('[^a-z0-9]+','_',name[:-4].lower()).strip('_')
        reports.append(dict(id=ident,title=title or name[:-4].replace('_',' '),cycle='2023–2032',url=urllib.parse.urljoin(NASA,href),index_url=NASA))
    for r in reports:
        if 'enceladus_orbilander' in r['id']:r['alternate_urls']=['https://ntrs.nasa.gov/api/citations/20205008712/downloads/enceladusorbilander_2020pmcs.pdf']
    unique={r['url']:r for r in reports}
    if len([r for r in reports if r['id'].startswith('vv2011')])<25:raise ValueError('Appendix G report listing was incomplete')
    CATALOG.write_text(json.dumps(dict(schema_version=1,indices=[INDEX,NASA],reports=list(unique.values())),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Found {len(unique)} official report links',flush=True)

def fetch_report(report,cache,extract):
    cache.mkdir(parents=True,exist_ok=True);pdf=cache/(report['id']+'.pdf')
    metadata=pdf.with_suffix('.json')
    downloaded_from=json.loads(metadata.read_text(encoding='utf-8')).get('downloaded_from',report['url']) if metadata.exists() else report['url']
    if not pdf.exists():
        error=None
        for url in [report['url'],*report.get('alternate_urls',[])]:
            try:raw=download(url);downloaded_from=url;break
            except (ValueError,OSError) as exc:error=exc
        else:raise error
        if not raw.startswith(b'%PDF'):raise ValueError('Server returned a non-PDF response')
        pdf.write_bytes(raw)
    raw=pdf.read_bytes();result=dict(report,downloaded_from=downloaded_from,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    if extract:
        try:from pypdf import PdfReader
        except ImportError:raise RuntimeError('PDF extraction needs the optional dependency: python -m pip install pypdf') from None
        reader=PdfReader(pdf);pages=[]
        for i,page in enumerate(reader.pages):pages.append(f'\n===== PDF PAGE {i+1} =====\n'+page.extract_text(extraction_mode='layout'))
        pdf.with_suffix('.txt').write_text('\n'.join(pages),encoding='utf-8',errors='replace');result['pages']=len(reader.pages)
    pdf.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return {k:result[k] for k in ('id','bytes','pages') if k in result}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',action='store_true');p.add_argument('--ids',nargs='*',default=[]);p.add_argument('--extract',action='store_true');p.add_argument('--cache',type=Path,default=ROOT/'cache/decadal_reports');a=p.parse_args()
    if a.inventory:inventory()
    if not a.ids:return
    reports=json.loads(CATALOG.read_text(encoding='utf-8'))['reports'];selected=[r for r in reports if r['id'] in a.ids]
    if {r['id'] for r in selected}!=set(a.ids):raise ValueError('Unknown report IDs')
    with ThreadPoolExecutor(max_workers=3) as pool:
        failures=0
        futures={pool.submit(fetch_report,r,a.cache,a.extract):r['id'] for r in selected}
        for future in as_completed(futures):
            try:print(json.dumps(future.result()),flush=True)
            except Exception as exc:
                failures+=1;print(json.dumps(dict(id=futures[future],error=str(exc))),flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
