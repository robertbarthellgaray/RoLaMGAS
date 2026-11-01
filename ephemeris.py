"""Geometric Sun-centered Ecliptic J2000 JPL Horizons vectors; TDB, km, km/s."""
import bootstrap  # noqa: F401
from pathlib import Path
from datetime import datetime, timedelta
import csv
import hashlib
import json
import re
import urllib.parse
import urllib.request
import tempfile
import time
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from horizons_targets import identity, cache_stem

DAY = 86400.0
AU = 149597870.7
MU_SUN = 132712440041.27942
JD0 = 2451544.5  # 2000-01-01 00:00 TDB
EPOCH = datetime(2000, 1, 1)
# GMs (km^3/s^2), reference equatorial radii (km), analyst screening floors (km).
# Planet-center GMs, not system masses. Sources and limitations in README.
BODIES = {
    'Mercury': (199, 22031.86855, 2439.7, 200.),
    'Venus': (299, 324858.592, 6051.8, 300.),
    'Earth': (399, 398600.435436, 6378.137, 200.),
    'Mars': (499, 42828.375816, 3396.19, 200.),
    'Jupiter': (599, 126686531.9, 71492., 10000.),
    'Saturn': (699, 37931206.234, 60268., 10000.),
    'Uranus': (799, 5793950.6103, 25559., 1000.),
    'Neptune': (899, 6835099.5, 24764., 1000.),
}


def jd(text):
    return JD0 + (datetime.fromisoformat(text) - EPOCH).total_seconds() / DAY


def calendar(value):
    return (EPOCH + timedelta(days=float(value) - JD0)).isoformat(timespec='seconds') + ' TDB'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw=json.dumps(value,indent=2,allow_nan=False)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                     prefix=path.name+'.',suffix='.tmp',delete=False) as handle:
        handle.write(raw);tmp=Path(handle.name)
    try:
        for attempt in range(12):
            try:tmp.replace(path);break
            except PermissionError:
                if attempt==11:raise
                time.sleep(min(.01*2**attempt,.25))
    finally:
        tmp.unlink(missing_ok=True)


def parse_horizons(text, body):
    header, data = text.split('$$SOE', 1)
    descriptor = identity(body)
    checks = [r'Center body name:\s*Sun \(10\)', r'Output units\s*:\s*KM-S',
              r'GEOMETRIC cartesian states', r'Ecliptic of J2000\.0', r'JDTDB,']
    if body in BODIES or descriptor.get('kind')!='small_body':
        target_ok=bool(re.search(rf'Target body name:\s*.*?\s+\({re.escape(str(descriptor["id"]))}\)',header))
    else:
        # Horizons small-body vector headers name the object but do not print
        # its SPK ID. Match the canonical SBDB identity/primary designation,
        # rather than requiring the major-body header format.
        line=re.search(r'Target body name:\s*([^\n]+)',header)
        actual=line[1].split('{')[0].strip() if line else ''
        compact=lambda s:re.sub(r'[^A-Za-z0-9]','',s).casefold()
        target_ok=compact(actual)==compact(descriptor['name'])
        designation=descriptor.get('designation','')
        if not target_ok and designation and not designation.isdigit():
            target_ok=bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(designation)+r'(?![A-Za-z0-9])',actual,re.I))
    if not target_ok or not all(re.search(p, header) for p in checks):
        raise ValueError(f'{body}: require the resolved target ID and geometric Sun/ECLIPJ2000 KM-S TDB CSV vectors')
    rows = list(csv.reader(data.split('$$EOE', 1)[0].strip().splitlines()))
    # Calendar timestamps retain subsecond precision even in old tables with rounded JDs.
    dates = [datetime.strptime(r[1].strip().removeprefix('A.D. '), '%Y-%b-%d %H:%M:%S.%f') for r in rows]
    times = np.array([(d - EPOCH).total_seconds() for d in dates])
    states = np.array([[float(v) for v in r[2:8]] for r in rows])
    printed = np.array([float(r[0]) for r in rows])
    if (len(times) < 4 or np.any(np.diff(times) <= 0) or not np.all(np.isfinite(states))
            or np.max(np.abs((printed - JD0) * DAY - times)) > 1.):
        raise ValueError(f'{body}: invalid states or timestamps')
    return times, states


def save_table(cache, body, text, source):
    times, states = parse_horizons(text, body)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    key = f'{cache_stem(body)}_{digest[:16]}'
    raw = cache / (key + '.txt')
    raw.write_text(text, encoding='utf-8')
    packed = cache / (key + '.npz')
    np.savez_compressed(packed, times=times, states=states)
    atomic_json(cache / (key + '.json'), dict(body=body, source=source, sha256=digest,
                raw_file=raw.name, target_identity=identity(body),
                npz_sha256=hashlib.sha256(packed.read_bytes()).hexdigest(),
                format='Sun-centered Ecliptic J2000, km, km/s, TDB',
                start_jd=JD0 + times[0] / DAY, end_jd=JD0 + times[-1] / DAY,
                max_step_days=float(np.max(np.diff(times)) / DAY), records=len(times)))
    return cache / (key + '.npz')


class Ephemerides:
    def __init__(self, cache, bodies, start, end, max_step_days=2., mercury_fine=True):
        self.splines = {}
        self.manifest = {}
        for body in sorted(set(bodies)):
            body_step = min(max_step_days,.25) if body == 'Mercury' and mercury_fine else max_step_days
            choices = []
            available = []
            for p in Path(cache).glob(cache_stem(body) + '_*.json'):
                m = json.loads(p.read_text(encoding='utf-8'))
                if m['max_step_days'] <= body_step:
                    available.append((p,m))
                if m['start_jd'] <= start and m['end_jd'] >= end and m['max_step_days'] <= body_step:
                    choices.append((m['max_step_days'], m['end_jd'] - m['start_jd'], p, m))
            if choices:
                _,_,path,metadata = min(choices,key=lambda x:(x[0],x[1],str(x[2])))
                selected = [(path,metadata)]
            else:
                selected, cursor = [],start
                while cursor < end:
                    covering = [(p,m) for p,m in available if m['start_jd'] <= cursor+1e-9 and m['end_jd'] > cursor+1e-9]
                    if not covering:
                        raise ValueError(f'No cached {body} coverage for {calendar(start)} through {calendar(end)}. Run prepare first.')
                    p,m = max(covering,key=lambda row:row[1]['end_jd'])
                    selected.append((p,m))
                    cursor = m['end_jd']
            chunks = []
            for path,metadata in selected:
                raw = path.parent / metadata['raw_file']
                if hashlib.sha256(raw.read_text(encoding='utf-8').encode()).hexdigest() != metadata['sha256']:
                    raise ValueError(f'Cached source checksum changed: {raw}')
                packed = path.with_suffix('.npz')
                if hashlib.sha256(packed.read_bytes()).hexdigest() != metadata['npz_sha256']:
                    raise ValueError(f'Cached derived vectors changed: {packed}')
                with np.load(packed,allow_pickle=False) as z:
                    chunks.append((z['times'],z['states']))
            times = np.concatenate([c[0] for c in chunks])
            states = np.concatenate([c[1] for c in chunks])
            times,indices = np.unique(times,return_index=True)
            states = states[indices]
            if np.max(np.diff(times)) > body_step*DAY+.01:
                raise ValueError(f'{body}: gap in ephemeris coverage')
            self.splines[body] = CubicHermiteSpline(times, states[:, :3], states[:, 3:], extrapolate=False)
            self.manifest[body] = [m for p,m in selected]

    def state(self, body, date):
        t = (float(date) - JD0) * DAY
        ep = self.splines[body]
        if not ep.x[0] <= t <= ep.x[-1]:
            raise ValueError('Ephemeris extrapolation prohibited')
        return np.r_[ep(t), ep(t, 1)]


def fetch(cache, body, start, end, step_days=1.):
    params = dict(COMMAND=identity(body)['command'], EPHEM_TYPE='VECTORS', CENTER='500@10',
                  START_TIME='JD' + str(start), STOP_TIME='JD' + str(end),
                  STEP_SIZE=f'{int(round(step_days * DAY))} s', OUT_UNITS='KM-S', REF_PLANE='ECLIPTIC',
                  REF_SYSTEM='ICRF', VEC_CORR='NONE', VEC_TABLE='2', CSV_FORMAT='YES', TIME_TYPE='TDB')
    # Horizons step sizes use minutes, hours or days; integral minutes permit fractional-day caches.
    params['STEP_SIZE'] = f'{int(round(step_days * 1440))} m'
    url = 'https://ssd.jpl.nasa.gov/api/horizons.api?' + urllib.parse.urlencode(
        {'format': 'json', **{k: "'" + v + "'" for k, v in params.items()}})
    print(f'Downloading {body}: {calendar(start)} to {calendar(end)}', flush=True)
    with urllib.request.urlopen(url, timeout=180) as response:
        result = json.load(response)
    if result.get('error') or '$$SOE' not in result.get('result', ''):
        raise ValueError(f"Horizons: {result.get('error', result.get('result', 'No vectors'))}")
    return save_table(cache, body, result['result'], url)
