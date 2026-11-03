"""Portable, offline search settings; no cached vectors or executable state."""
from copy import deepcopy
import json
from app_paths import APP_VERSION

FORMAT='rolamgas-search-options'
SCHEMA_VERSION=1
MAX_DOCUMENT_BYTES=1024*1024
# These values belong to a particular computer or a running solver. Importing
# them must never read another user's files or silently replace frozen states.
LOCAL_FIELDS={'cache','workers','launch_jd','event_windows_jd','arrival_window_jd',
              'local_refinement','append_flyby','effective_min_c3'}
TARGET_FIELDS={'name','id','command','designation','kind','orbit_class',
               'semimajor_axis_au','perihelion_au','inclination_deg','retrograde',
               'effective_radius_km','effective_radius_note','is_comet',
               'object_type','parent_body','model_limitation'}


def _object(value):
    if not isinstance(value,dict):
        raise ValueError('Search options must be a JSON object')
    try:
        raw=json.dumps(value,allow_nan=False,ensure_ascii=False).encode('utf-8')
    except (ValueError,TypeError,RecursionError) as exc:
        raise ValueError('Search options must contain finite JSON values') from exc
    if len(raw)>MAX_DOCUMENT_BYTES:
        raise ValueError('Search options file is larger than 1 MiB')
    return deepcopy(value)


def _target(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Target identity must be an object')
    clean={key:deepcopy(value[key]) for key in TARGET_FIELDS if key in value}
    # Store the explicit selection, rather than a private/path-like original query.
    clean['query']='SPK='+str(clean.get('id',''))
    return clean


def _settings(raw):
    from ephemeris import BODIES
    from mission_search import normalize,routes_for
    raw=_object(raw)
    notes=[]
    extension=raw.get('append_flyby')
    if extension:
        if not isinstance(extension,dict):
            raise ValueError('Cannot export malformed appended-flyby settings')
        route=extension.get('route',{})
        if not isinstance(route,dict) or not route.get('id'):
            raise ValueError('Cannot export malformed appended-flyby settings')
        if route.get('target')=='Earth' or any(body not in BODIES for body in route.get('bodies',[])):
            raise ValueError('This return search contains a frozen cruise that cannot be represented by search options alone. Export options from the original outbound search, or share its trajectory files separately; frozen spacecraft states are not included in an options file.')
        raw['sequences']=[route['id']]
        raw['route_overrides']={route['id']:{key:deepcopy(route[key]) for key in ('leg_days','branch_options')}}
        notes.append('The frozen earlier cruise is not included. These options start a fresh search of the whole assist sequence.')
    if raw.get('local_refinement'):
        notes.append('Date windows are preserved; the selected candidate and its numerical seed are not included.')
    clean={key:value for key,value in raw.items() if key not in LOCAL_FIELDS}
    if clean.get('target_object'):
        clean['target_object']=_target(clean['target_object'])
    try:
        normalized=normalize(clean)
        routes=routes_for(normalized)
    except (TypeError,KeyError,OverflowError) as exc:
        raise ValueError('Invalid search options: '+str(exc)) from exc
    effective=normalized.get('effective_min_c3',normalized['min_c3'])
    if effective>normalized['min_c3']:
        notes.append(f"The requested C3 minimum {normalized['min_c3']:.8g} is below this solver's floor; the effective minimum is {effective:.8g} km²/s².")
    result={key:deepcopy(value) for key,value in normalized.items() if key not in LOCAL_FIELDS}
    result['target_object']=_target(result.get('target_object'))
    result['sequences']=[route['id'] for route in routes]
    # Explicit effective routes avoid relying on a recipient's edited database.
    result['route_overrides']={route['id']:{key:deepcopy(route[key]) for key in ('leg_days','branch_options')} for route in routes}
    result['minimum_altitude_km']={body:normalized['minimum_altitude_km'].get(body,data[3]) for body,data in BODIES.items()}
    _object(result)
    return result,notes


def export_options(config):
    settings,notes=_settings(config)
    notes.append('Only search settings are shared. Candidate trajectories, cached JPL data, pins and local file paths are not included; CPU workers use the local worker setting selected by the recipient.')
    return dict(filename='RoLaMGAS-search-options.json',
                document=dict(format=FORMAT,schema_version=SCHEMA_VERSION,
                              app_version=APP_VERSION,settings=settings),notes=notes)


def import_options(document):
    document=_object(document)
    if document.get('format')!=FORMAT:
        raise ValueError('Not a RoLaMGAS search-options file. Use Export search options in the other client.')
    if type(document.get('schema_version')) is not int or document['schema_version']!=SCHEMA_VERSION:
        raise ValueError('Unsupported search-options version; update RoLaMGAS or request a compatible export')
    settings,notes=_settings(document.get('settings'))
    if settings.get('target_object'):
        notes.append('Confirm this Horizons target with Resolve with JPL before starting. Importing the file does not verify its identity or download vectors.')
    notes.append('Options loaded only. No search has started; missing ephemerides will use the local cache or download from JPL when you start.')
    return dict(config=settings,notes=notes,requires_target_resolution=bool(settings.get('target_object')))
