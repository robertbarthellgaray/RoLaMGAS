"""Resolve named Horizons targets; never substitute an unconfirmed fuzzy match."""
from pathlib import Path
import json
import re
import urllib.parse
from network import request_json

TARGETS = {}


def satellite_parent(descriptor):
    """Planetary-satellite SPK families; do not confuse asteroid numbers with IDs."""
    if not descriptor or descriptor.get('kind') == 'small_body':
        return None
    value = int(descriptor.get('id',0))
    family, member = divmod(value,100)
    return {3:'Earth',4:'Mars',5:'Jupiter',6:'Saturn',7:'Uranus',8:'Neptune',9:'Pluto'}.get(family) if 0 < member < 99 else None


def moon_model_notice(descriptor):
    parent = satellite_parent(descriptor)
    if not parent and (descriptor or {}).get('kind') != 'natural_satellite':
        return None
    location = parent or 'its parent body'
    return (f"{descriptor['name']} is a moon of {location}. Its identity is resolved, but "
            'direct heliocentric moon targeting is not supported. '
            f'Search {location} arrivals first; a parent-centered arrival targeting stage '
            'is required to account for gravitational bending before the moon encounter. '
            'Atmospheric entry and landing are not modeled.')


def register_target(descriptor):
    if not descriptor:
        return
    if (not isinstance(descriptor,dict) or not isinstance(descriptor.get('name'),str)
            or not re.fullmatch(r'-?\d+',str(descriptor.get('id','')))
            or not isinstance(descriptor.get('command'),str)):
        raise ValueError('A resolved Horizons target with name, numeric ID and command is required')
    if len(descriptor['name']) > 160 or len(descriptor['command']) > 160:
        raise ValueError('Horizons target identifier is too long')
    descriptor=dict(descriptor)
    if descriptor.get('kind')=='small_body' and str(descriptor.get('designation','')).isdigit():
        descriptor['command']=str(int(descriptor['designation']))+';'
    TARGETS[descriptor['name']] = descriptor


def identity(body):
    from ephemeris import BODIES
    if body in BODIES:
        return dict(name=body,id=str(BODIES[body][0]),command=str(BODIES[body][0]),kind='planet')
    if body not in TARGETS:
        raise ValueError(f'Resolve the Horizons target before requesting vectors: {body}')
    return TARGETS[body]


def is_comet(descriptor):
    """Recognize older cached comet descriptors as well as fresh lookup metadata."""
    if descriptor.get('kind') != 'small_body':
        return False
    designation = str(descriptor.get('designation', '')).strip()
    return bool(descriptor.get('is_comet') or descriptor.get('object_type', '').startswith('comet')
                or re.match(r'^\d+[PDCX](?:-|$)', designation, re.I)
                or re.match(r'^[PCDX]/', designation, re.I)
                or re.match(r'^[PCDX]/', descriptor.get('name',''), re.I)
                or 'comet' in str(descriptor.get('orbit_class', '')).lower())


def command_for_epoch(body, start_jd):
    """Pin a comet apparition once, including descriptors saved by older releases.

    Horizons DES=1P; returns thirty records rather than vectors. CAP<JD selects
    the last solution before the requested epoch, without unstable record IDs.
    Keeping this in the registered identity also keeps chunked downloads on the
    same apparition. New resolutions already carry a launch-epoch selection.
    """
    from math import isfinite
    descriptor = identity(body)
    if not is_comet(descriptor):
        return descriptor['command']
    before = descriptor.get('comet_apparition_before_jd')
    if before is None:
        before = float(start_jd)
    if not isfinite(float(before)):
        raise ValueError('A finite epoch is required to select the comet apparition')
    designation = str(descriptor.get('designation', '')).strip()
    if not designation:
        raise ValueError('Resolve this comet again to obtain its primary designation before downloading vectors')
    descriptor = dict(descriptor, command=f'DES={designation};CAP<{float(before):.9f};',
                      is_comet=True, comet_apparition_before_jd=float(before),
                      comet_apparition_policy='last apparition before requested launch/cache epoch')
    register_target(descriptor)
    return descriptor['command']


def target_for_epoch(descriptor, start_jd):
    """Normalize a saved target identity for a new mission's launch epoch."""
    normalized = dict(descriptor)
    if is_comet(normalized):
        normalized.pop('comet_apparition_before_jd', None)
    register_target(normalized)
    command_for_epoch(normalized['name'], start_jd)
    return dict(identity(normalized['name']))


def cache_stem(body):
    from ephemeris import BODIES
    return body if body in BODIES else 'object_'+str(identity(body)['id']).replace('-','minus')


def resolve(query,epoch='2030-01-01'):
    from ephemeris import BODIES, AU, DAY, jd
    query = str(query).strip()
    if not query or len(query)>100 or not re.fullmatch(r'[\w\s./()+*=\-]+',query,re.ASCII):
        raise ValueError('Enter an object name, designation or numeric Horizons ID')
    for name in BODIES:
        if query.lower() == name.lower() or query==str(BODIES[name][0]):
            return identity(name)
    # Search BOTH Horizons indexes first. SBDB-only HTTP errors used to prevent
    # the major-body fallback from running at all (e.g. Titan).
    # '(SVI)' is a display label, rather than a literal Horizons query string.
    search = re.sub(r'\s*\([EMJSUN][IVXLCDM]+\)\s*$','',query,flags=re.I).strip()
    explicit_id = re.fullmatch(r'SPK=(-?\d+)',search,re.I)
    if explicit_id:
        search = explicit_id[1]
    lookup_url = 'https://ssd.jpl.nasa.gov/api/horizons_lookup.api?'+urllib.parse.urlencode({'sstr':search})
    lookup = request_json(lookup_url)
    if lookup.get('signature',{}).get('version') not in ('1.0','1.1'):
        raise ValueError('Unrecognized Horizons Lookup API version; no target was selected')
    matches = lookup.get('result',[])
    if explicit_id:
        matches = [x for x in matches if str(x.get('spkid')) == search]
    if len(matches)>1:
        choices = [{'name':x['name'], 'designation':'SPK='+str(x['spkid']),
                    'id':str(x['spkid']),'type':x.get('type')} for x in matches[:30]]
        return dict(ambiguous=True,query=query,choices=choices,message='Choose a specific designation and resolve it again.')
    if not matches:
        raise ValueError('No matching Horizons object. Try its canonical name or SPK ID.')
    match_object = matches[0]
    object_type = match_object.get('type','').lower()
    small_body = object_type.startswith(('asteroid (integrated','comet (integrated'))
    sb = {}
    sb_url = None
    if small_body:
        sb_url = 'https://ssd-api.jpl.nasa.gov/sbdb.api?'+urllib.parse.urlencode(
            {'spk':match_object['spkid'],'phys-par':'1','full-prec':'1'})
        sb = request_json(sb_url)
    obj = sb.get('object')
    if obj:
        if str(obj['spkid']) != str(match_object['spkid']):
            raise ValueError('SBDB identity differs from the selected Horizons lookup identity; no target was selected')
        command=str(int(obj['des']))+';' if obj['des'].isdigit() else 'DES='+obj['des']+';'
        descriptor = dict(name=obj['fullname'],id=str(obj['spkid']),command=command,
                          designation=obj['des'],kind='small_body',orbit_class=obj.get('orbit_class',{}).get('name'),
                          source=sb_url,orbit_solution=sb.get('orbit',{}).get('orbit_id'),query=query,
                          object_type=object_type,is_comet=object_type.startswith('comet'))
        elements = {e['name']:e['value'] for e in sb.get('orbit',{}).get('elements',[])}
        for field, key in [('semimajor_axis_au','a'), ('perihelion_au','q'),
                           ('inclination_deg','i'), ('eccentricity','e'),
                           ('aphelion_au','ad'), ('period_days','per')]:
            value = elements.get(key)
            descriptor[field] = float(value) if value is not None else None
        descriptor['retrograde'] = (descriptor['inclination_deg'] is not None and descriptor['inclination_deg'] > 90)
        physical = {p['name']:p for p in sb.get('phys_par',[])}
        diameter = physical.get('diameter',{})
        if diameter.get('value') is not None and diameter.get('units') == 'km':
            descriptor['effective_radius_km'] = float(diameter['value'])/2
            descriptor['radius_source'] = diameter.get('ref')
            descriptor['radius_note'] = 'Half the SBDB effective diameter; not a shape or surface-clearance model.'
        register_target(descriptor)
        if descriptor['is_comet']:
            command_for_epoch(descriptor['name'], jd(epoch))
            descriptor = identity(descriptor['name'])
        return descriptor
    if small_body:
        raise ValueError('Horizons found the small body, but SBDB did not return a unique orbit. Try again later.')
    # Horizons also catalogs spacecraft, moons and major bodies not in SBDB.
    # Request a short vector table to identify them unambiguously and verify
    # that they actually have ephemeris coverage at the requested launch epoch.
    params = dict(COMMAND=str(match_object['spkid']),EPHEM_TYPE='VECTORS',CENTER='500@10',START_TIME='JD'+str(jd(epoch)),
                  STOP_TIME='JD'+str(jd(epoch)+3),STEP_SIZE='1 d',REF_PLANE='ECLIPTIC',OUT_UNITS='KM-S',
                  VEC_CORR='NONE',VEC_TABLE='2',CSV_FORMAT='YES',TIME_TYPE='TDB')
    url = 'https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(
        {'format':'json',**{k:"'"+v+"'" for k,v in params.items()}})
    result = request_json(url)
    text = result.get('result','')
    match = re.search(r'Target body name:\s*(.*?)\s+\((-?\d+)\)',text)
    if not match or '$$SOE' not in text:
        message = result.get('error') or text or sb.get('message','No matching object')
        raise ValueError('Horizons could not resolve a unique target with coverage at this epoch. '+message[:1800])
    descriptor = dict(name=match[1].strip(),id=match[2],command=match[2],kind='horizons_object',
                      source=url,query=query,lookup_source=lookup_url,object_type=object_type)
    if descriptor['id'] != str(match_object['spkid']):
        raise ValueError('Horizons vector identity differs from the selected lookup identity')
    if 'satellite' in object_type or satellite_parent(descriptor):
        descriptor['kind']='natural_satellite'
        descriptor['parent_body']=satellite_parent(descriptor)
        descriptor['model_limitation']=moon_model_notice(descriptor)
    if descriptor['id'] == '10':
        raise ValueError('The Sun cannot be a terminal Lambert target in this heliocentric model')
    register_target(descriptor)
    return descriptor
