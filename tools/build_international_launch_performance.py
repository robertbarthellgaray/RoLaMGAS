"""Rebuild international C3 data from independently published fits and a study point.

No network requests or invented extrapolations. NASA refreshes can be followed
by this script to reattach the additional, explicitly labeled source rows.
"""
from pathlib import Path
import argparse,csv,json,math,sys
ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'studies/international_launch_performance'
WISE='https://repository.gatech.edu/server/api/core/bitstreams/2578ccee-732e-421b-adda-de8458be849a/content'
STUDY2025='https://www.mdpi.com/2226-4310/12/4/271'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def polynomial(coefficients,c3):
    return sum(coefficient*c3**power for power,coefficient in enumerate(coefficients))


def build():
    # Wise, Lafleur & Saleh (2010), Table 1 (p.7), ascending powers of C3.
    specs=[('LM-3A',[1450.,-47.06,-.4361,.037,-.000616],[.55,29.67]),
           ('LM-3B',[3413.,-81.02,-.0512,.026,-.000349],[1.02,47.32]),
           ('LM-3C',[2329.,-71.89,.5289,.0021,-.0000903],[.55,38.17])]
    vehicles=[]
    for name,coefficients,(lo,hi) in specs:
        grid=sorted(set([lo,hi]+[float(n) for n in range(math.ceil(lo),math.floor(hi)+1)]+[6.25,28.]))
        grid=[n for n in grid if lo<=n<=hi]
        points=[[n,polynomial(coefficients,n)] for n in grid]
        assert all(m>0 for _,m in points)
        vehicles.append(dict(international_id='wise2010_'+name,vehicle='Long March '+name+' (historical baseline)',launch_site='Source manual baseline',
            source_label='Published fit · 2010',source_url=WISE,data_kind='published_historical_fit',source_year=2010,
            fairing='Source configuration',adapter='Source convention',
            ground_rules='Wise, Lafleur & Saleh, IAC-10.D2.P06, Table 1, p.7. Historical configuration; not an enhanced/current-vehicle rating. Printed rounded polynomial coefficients; curve-fit residuals are not launch-performance uncertainty. Valid C3 '+str(lo)+'–'+str(hi)+' km²/s². No extrapolation.',
            polynomial_ascending=coefficients,valid_c3_range=[lo,hi],query_grid_c3=grid,points=points))
    vehicles.append(dict(international_id='wang2025_lm5_point',vehicle='Long March 5 · 2025 study point',launch_site='Wenchang',
        source_label='Published study · 2025',source_url=STUDY2025,data_kind='published_study_point',source_year=2025,
        fairing='Unspecified in study',adapter='Unspecified in study',points=[[30.,3000.]],query_grid_c3=[30.],
        ground_rules='Wang et al., Aerospace 2025, 12(4), 271, Section 5.1: approximately 3 tonnes at C3=30. Mission-study assumption, not a provider guarantee. A single anchor point; never interpolated/extrapolated into a full curve.'))
    doc=dict(schema_version=1,source='Published historical fits and a published mission-study point',
        interpolation='Within each vehicle\'s own sampled coverage only. Source types and assumptions remain separate.',vehicles=vehicles)
    for path in (ROOT/'gui_assets/international_launch_performance.json',ROOT/'docs/data/international_launch_performance.json'):save(path,doc)
    for path in (ROOT/'gui_assets/launch_performance_curves.json',ROOT/'docs/data/launch_performance_curves.json'):
        base=json.loads(path.read_text(encoding='utf-8'))
        base['vehicles']=[v for v in base['vehicles'] if not v.get('international_id')]+vehicles
        base['additional_sources']=[dict(label='Wise et al. 2010 historical fits',url=WISE),dict(label='Wang et al. 2025 LM-5 study point',url=STUDY2025)]
        save(path,base)
    with (STUDY/'capacity_samples.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(['vehicle','source_type','c3_km2_s2','payload_system_mass_kg','source_url'])
        for v in vehicles:
            writer.writerows([v['vehicle'],v['data_kind'],x,y,v['source_url']] for x,y in v['points'])
    print('Added',len(vehicles),'international source/configuration rows')
    return doc


def plot(doc):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,6));colors=['#2677a5','#387e44','#b47a2e','#bf3333']
    for i,v in enumerate(doc['vehicles']):
        x,y=zip(*v['points']);ax.plot(x,y,'s' if len(x)==1 else '-',lw=1.8,ms=6,color=colors[i],label=v['vehicle'])
    ax.grid(alpha=.2);ax.set(xlabel='Launch C3 (km²/s²)',ylabel='Payload system mass (kg)',ylim=(0,None),title='Published Chinese launch-performance examples')
    ax.legend(fontsize=8)
    fig.text(.5,.025,'Historical LM-3 fits and a separate LM-5 mission-study point. Conditions differ by source; no extrapolation.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(STUDY/'international_launch_performance.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plot',action='store_true');args=parser.parse_args()
    doc=build()
    if args.plot:plot(doc)
