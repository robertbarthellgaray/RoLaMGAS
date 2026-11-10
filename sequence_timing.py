"""Broad search envelopes, not promises of feasible transfers."""
from copy import deepcopy

PLANETS=('Mercury','Venus','Earth','Mars','Jupiter','Saturn','Uranus','Neptune')
PLANET_DEFAULT_DAYS=[30.,20*365.25]
OTHER_DEFAULT_DAYS=[30.,50*365.25]
ADDITIONAL_PAIR_DAYS={
    'Mars-Jupiter':[250.,2500.], 'Jupiter-Mars':[250.,2500.],
    'Uranus-Neptune':[900.,6000.], 'Neptune-Uranus':[900.,6000.],
}


def pair_bounds(a,b,database):
    key=a+'-'+b
    return list(database.get('pair_days',{}).get(key,ADDITIONAL_PAIR_DAYS.get(key,PLANET_DEFAULT_DAYS if a in PLANETS and b in PLANETS else OTHER_DEFAULT_DAYS)))


def complete_pairs(existing):
    result=deepcopy(existing)
    for a in PLANETS:
        for b in PLANETS:result.setdefault(a+'-'+b,pair_bounds(a,b,{'pair_days':existing}))
    return result
