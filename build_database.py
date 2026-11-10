"""Rebuild the editable sequence database from dated mission references."""
from pathlib import Path
from datetime import date
import json

HERE = Path(__file__).resolve().parent
REFERENCES = [
    dict(mission='Juno', sequence='EdvEJ',
         sources=['https://www.jpl.nasa.gov/news/press_kits/juno/facts/',
                  'https://science.nasa.gov/mission/juno/juno-orbits/',
                  'https://www.nasa.gov/history/10-years-ago-juno-launched-to-observe-jupiter/'],
         events=[['Earth','2011-08-05'], ['DSM','2012-08-30'], ['DSM','2012-09-14'],
                 ['Earth','2013-10-09'], ['Jupiter','2016-07-05']],
         note='Two real DSMs are represented by one designed impulse in the search template. Jupiter arrival is July 5 UTC (July 4 in US mission reporting).'),
    dict(mission='Galileo', sequence='EVEEJ',
         sources=['https://www.nasa.gov/history/35-years-ago-sts-34-sends-galileo-on-its-way-to-jupiter/',
                  'https://www.jpl.nasa.gov/missions/galileo/'],
         events=[['Earth','1989-10-18'], ['Venus','1990-02-10'], ['Earth','1990-12-08'],
                 ['Earth','1992-12-08'], ['Jupiter','1995-12-07']],
         note='Planet encounters only; this list is not the complete maneuver history.'),
    dict(mission='Cassini', sequence='EVdvVEJS',
         sources=['https://ntrs.nasa.gov/search.jsp?R=20000074241',
                  'https://solarsystem.nasa.gov/system/downloadable_items/1946_trajectory.pdf',
                  'https://www.nasa.gov/wp-content/uploads/2015/01/59910main_cassini.pdf'],
         events=[['Earth','1997-10-15'], ['Venus','1998-04-26'], ['DSM','1998-12-03'],
                 ['Venus','1999-06-24'], ['Earth','1999-08-18'], ['Jupiter','2000-12-30'],
                 ['Saturn','2004-07-01']],
         note='The Venus-return DSM is explicit. Search ranges are not exact mission reconstruction constraints.'),
    dict(mission='MESSENGER', sequence='EEVVMeMeMeMe',
         sources=['https://science.nasa.gov/mission/messenger/',
                  'https://www.nasa.gov/wp-content/uploads/2015/04/525164main_mercurymoi_pk.pdf'],
         events=[['Earth','2004-08-03'], ['Earth','2005-08-02'], ['Venus','2006-10-24'],
                 ['Venus','2007-06-05'], ['Mercury','2008-01-14'], ['Mercury','2008-10-06'],
                 ['Mercury','2009-09-29'], ['Mercury','2011-03-18']],
         note='Actual MESSENGER used several DSMs. The planet-only route is a screening template; a DSM variant is also supplied.'),
    {'mission': 'New Horizons', 'sequence': 'EJX', 'sources': ['https://science.nasa.gov/mission/new-horizons/'], 'events': [['Earth', '2006-01-19'], ['Jupiter', '2007-02-28'], ['Pluto', '2015-07-14']], 'note': 'Fast Earth-Jupiter flight: about 405 days. Included to avoid excluding high-energy Jupiter-assist launches from default timing ranges. Pluto is a resolved custom terminal target.'},
]


def build():
    for ref in REFERENCES:
        encounters = [(body, day) for body, day in ref['events'] if body != 'DSM']
        ref['planet_leg_days'] = [dict(departure=a, arrival=b,
             days=(date.fromisoformat(tb)-date.fromisoformat(ta)).days)
             for (a,ta),(b,tb) in zip(encounters, encounters[1:])]
    # Deliberately broad analyst ranges, informed by flight histories and widened
    # to admit different geometry. They do not predict feasible future windows.
    pair_days = {
        'Earth-Venus':[90,500], 'Venus-Earth':[45,500], 'Venus-Venus':[180,650],
        'Earth-Earth':[300,1200], 'Earth-Jupiter':[300,1800],
        'Jupiter-Saturn':[700,2200], 'Earth-Saturn':[900,3000],
        'Jupiter-Uranus':[1800,5000], 'Earth-Uranus':[3000,7500],
        'Jupiter-Neptune':[2500,6500], 'Earth-Neptune':[4000,10000],
        'Saturn-Uranus':[1200,4500], 'Saturn-Neptune':[2000,6000],
        'Earth-Mars':[100,600], 'Mars-Earth':[100,700], 'Venus-Mars':[120,700],
        'Earth-Mercury':[80,500], 'Venus-Mercury':[80,500],
        'Mercury-Mercury':[80,750], 'Mercury-Venus':[80,500],
    }
    codes = dict(E='Earth',V='Venus',M='Mars',Me='Mercury',J='Jupiter',S='Saturn',U='Uranus',N='Neptune')
    from sequence_timing import complete_pairs
    pair_days=complete_pairs(pair_days)
    import re

    def parse(sequence):
        tokens = re.findall(r'Me|dv|dV|[EVMJSUN]', sequence)
        if ''.join(tokens) != sequence or tokens[0] not in codes or tokens[-1] not in codes:
            raise ValueError('Use E,V,M,Me,J,S,U,N, and dv inside a leg')
        bodies, dsms = [], []
        for token in tokens:
            if token in ('dv','dV'):
                if len(bodies)-1 in dsms:
                    raise ValueError('Only one designed DSM per leg is supported')
                dsms.append(len(bodies)-1)
            else:
                bodies.append(codes[token])
        return bodies, dsms

    strings = ['EV','EM','EVM','EMe','EVMe','EVVMe','EVMeMe','EVMeMeMe','EVVMeMeMeMe','EEVVMeMeMeMeMeMeMe','EEVVMeMeMeMe','EdvEVdvVdvMedvMedvMedvMe',
               'EJ','EdvEJ','EVEEJ','EVdvEEJ','EVVEJ','EVdvVEJ','EMEJ','EEVEEJ',
               'ES','EdvES','EEJS','EVEEJS','EVdvVEJS','EdvEJS',
               'EU','EJU','EdvEJU','EVEEJU','EVdvVEJU','ESU',
               'EN','EJN','EdvEJN','EVEEJN','EVdvVEJN','ESN']
    routes = []
    for s in strings:
        bodies, dsms = parse(s)
        ranges = [pair_days[a+'-'+b] for a,b in zip(bodies,bodies[1:])]
        if s.startswith('EdvE'):
            ranges[0] = [500,1200]
        branches = []
        for a,b,(lo,hi) in zip(bodies,bodies[1:],ranges):
            max_m = 0
            if a == b:
                max_m = {'Mercury':4,'Venus':2,'Earth':2}.get(a,1)
            elif a in ('Venus','Mercury') and b in ('Venus','Mercury','Earth'):
                max_m = 1
            branches.append([[0,True]] + [[m,low] for m in range(1,max_m+1) for low in (True,False)])
        routes.append(dict(id=s, bodies=bodies, target=bodies[-1], dsm_legs=dsms,
                           leg_days=ranges, branch_options=branches,
                           provenance='Flown architecture' if s in ('EdvEJ','EVEEJ','EVdvVEJS','EEVVMeMeMeMe')
                                      else 'Analyst template; future feasibility must be searched'))
    db = dict(schema_version=1, notation=codes, references=REFERENCES, pair_days=pair_days,
              conventions=dict(time='TDB', M='Mars', Me='Mercury', dv='one optimized in-leg impulse',
                  timing='Broad analyst-selected search bounds informed by flown leg durations.',
                  branches='Prograde Lambert M/low-path choices; higher M can be added in JSON.',
                  status='Sequence templates, not a precomputed feasibility catalog.'), sequences=routes)
    (HERE/'sequence_database.json').write_text(json.dumps(db,indent=2),encoding='utf-8')


if __name__ == '__main__':
    build()
