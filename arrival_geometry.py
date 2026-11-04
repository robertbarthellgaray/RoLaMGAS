"""Terminal B-plane inclination targeting in geometric Ecliptic J2000 axes.

Pole coefficients are the eight-planet subset of JPL NAIF pck00011.tpc.
The periodic RA (sine) and DEC (cosine) terms are retained for Mars,
Jupiter and Neptune. Earth uses the text-PCK approximation, not binary EOP.
Source: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc
Orientation convention: https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/pck.html
B-plane geometry: https://help.agi.com/stk/12.9.0/Content/gator/eq-bplane.htm
"""
import math
import numpy as np

POLE_SOURCE='JPL NAIF pck00011.tpc (IAU text-PCK north pole at encounter epoch)'
POLE_URL='https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc'
# RA_0, RA_rate, DEC_0, DEC_rate, followed by periodic
# (phase_deg, rate_deg_per_Julian_century, RA_sine_deg, DEC_cosine_deg).
_POLES={
 'Mercury':(281.0103,-.0328,61.4155,-.0049,()),
 'Venus':(272.76,0.,67.16,0.,()),
 'Earth':(0.,-.641,90.,-.557,()),
 'Mars':(317.269202,-.10927547,54.432516,-.05827105,(
     (198.991226,19139.4819985,.000068,0.),
     (226.292679,38280.8511281,.000238,0.),
     (249.663391,57420.7251593,.000052,0.),
     (266.183510,76560.6367950,.000009,0.),
     (79.398797,.5042615,.419057,0.),
     (122.433576,19139.9407476,0.,.000051),
     (43.058401,38280.8753272,0.,.000141),
     (57.663379,57420.7517205,0.,.000031),
     (79.476401,76560.6495004,0.,.000005),
     (166.325722,.5042615,0.,1.591274))),
 'Jupiter':(268.056595,-.006499,64.495303,.002413,(
     (99.360714,4850.4046,.000117,.000050),
     (175.895369,1191.9605,.000938,.000404),
     (300.323162,262.5475,.001432,.000617),
     (114.012305,6070.2476,.000030,-.000013),
     (49.511251,64.3000,.002150,.000926))),
 'Saturn':(40.589,-.036,83.537,-.004,()),
 'Uranus':(257.311,0.,-15.175,0.,()),
 'Neptune':(299.36,0.,43.46,0.,((357.85,52.316,.70,-.51),)),
}
# NAIF ECLIPJ2000: IAU 1976 mean obliquity, 84381.448 arcseconds.
_OBLIQUITY=math.radians(84381.448/3600.)


def unit(value):
    value=np.asarray(value,dtype=float)
    length=float(np.linalg.norm(value))
    if value.shape!=(3,) or not np.all(np.isfinite(value)) or length<1e-12:
        raise ValueError('Require a finite nonzero three-vector')
    return value/length


def validate_inclination(value):
    if value is None:return None
    value=float(value)
    if not math.isfinite(value) or not 0<=value<=180:
        raise ValueError('Arrival inclination must be between 0 and 180 degrees')
    return value


def planet_pole(body,epoch_jd_tdb):
    """IAU text-PCK north pole, expressed in Horizons Ecliptic J2000 axes."""
    if body not in _POLES:
        raise ValueError('Arrival inclination targeting requires a supported planet with known pole and GM')
    epoch=float(epoch_jd_tdb)
    if not math.isfinite(epoch):raise ValueError('Arrival epoch must be finite')
    century=(epoch-2451545.)/36525.
    ra0,ra_rate,dec0,dec_rate,terms=_POLES[body]
    ra=ra0+ra_rate*century;dec=dec0+dec_rate*century
    for phase,rate,ra_amp,dec_amp in terms:
        angle=math.radians((phase+rate*century)%360.)
        ra+=ra_amp*math.sin(angle);dec+=dec_amp*math.cos(angle)
    ra,dec=math.radians(ra),math.radians(dec)
    x=math.cos(dec)*math.cos(ra);y=math.cos(dec)*math.sin(ra);z=math.sin(dec)
    c,s=math.cos(_OBLIQUITY),math.sin(_OBLIQUITY)
    return unit([x,c*y+s*z,-s*y+c*z])


def inclination_bounds(direction,pole):
    """All planes containing a fixed incoming asymptote must obey h dot S=0."""
    angle=math.degrees(math.asin(min(1.,abs(float(unit(direction)@unit(pole))))))
    return [angle,180.-angle]


def target_plane_axis(direction,pole,reference,inclination_deg):
    """Choose the closest of the two admissible B-plane orientations.

    S is the incoming velocity direction; h must be orthogonal to S and have
    h dot pole=cos(i). A requested plane can be unavailable for fixed S.
    """
    desired=validate_inclination(inclination_deg)
    if desired is None:raise ValueError('Specify an arrival inclination')
    s,k,reference=unit(direction),unit(pole),unit(reference)
    lower,upper=inclination_bounds(s,k)
    if desired<lower-1e-8 or desired>upper+1e-8:
        raise ValueError(f'Arrival inclination {desired:.6g} deg is not reachable with this incoming asymptote. '
                         f'Choose {lower:.6f} to {upper:.6f} deg, or search a different arrival geometry. '
                         'No unbudgeted plane-change burn has been added.')
    projected=k-float(k@s)*s;length=float(np.linalg.norm(projected))
    if length<1e-12:
        projected=reference-float(reference@s)*s
        if np.linalg.norm(projected)<1e-12:
            projected=np.cross(s,[1.,0.,0.])
            if np.linalg.norm(projected)<1e-12:projected=np.cross(s,[0.,1.,0.])
        return unit(projected)
    along=projected/length;across=unit(np.cross(s,along))
    fraction=float(np.clip(math.cos(math.radians(desired))/length,-1.,1.))
    complement=math.sqrt(max(0.,1.-fraction*fraction))
    choices=[fraction*along+sign*complement*across for sign in (-1.,1.)]
    return unit(max(choices,key=lambda h:float(h@reference)))


def capture_assessment(body,date,mu,incoming,position,velocity,requested=None):
    """Describe the arrival plane and an unapplied, coplanar circular capture."""
    pole=planet_pole(body,date);r=np.asarray(position,dtype=float);v=np.asarray(velocity,dtype=float)
    h=unit(np.cross(r,v));speed=float(np.linalg.norm(v));rp=float(np.linalg.norm(r))
    incoming=np.asarray(incoming,dtype=float);vinf=float(np.linalg.norm(incoming))
    achieved=math.degrees(math.acos(float(np.clip(h@pole,-1.,1.))))
    circular=math.sqrt(mu/rp);delta=(circular-speed)*unit(v)
    bmag=rp*math.sqrt(1+2*mu/(rp*vinf*vinf))
    return dict(requested_inclination_deg=validate_inclination(requested),
        achieved_inclination_deg=achieved,reference_plane='Planet equator; IAU north-pole convention',
        pole_model=POLE_SOURCE,pole_source_url=POLE_URL,pole_vector_ecliptic_j2000=pole.tolist(),
        fixed_asymptote_inclination_range_deg=inclination_bounds(incoming,pole),
        b_plane_vector_km=(bmag*np.cross(unit(incoming),h)).tolist(),
        circular_capture_radius_km=rp,circular_speed_kms=circular,
        hypothetical_circular_capture_delta_v_kms=float(np.linalg.norm(delta)),
        hypothetical_circular_capture_burn_vector_kms=delta.tolist(),
        hypothetical_circular_state_km_kms=np.r_[r,circular*unit(v)].tolist(),
        capture_applied=False,capture_cost_included_in_onboard_budget=False,
        note='B-plane orientation is chosen only during finite-radius export, not constrained in the Lambert search. '
             'All finite-patch junction burns are reported separately. The coplanar impulsive circular-capture '
             'estimate is not executed or included in the maneuver budget; atmospheric drag, rings, J2 and moons '
             'are omitted. IAU north defines 0 deg; Venus and Uranus retrograde spin does not reverse that pole. '
             'The Earth pole uses the approximate text-PCK model, not Earth-orientation measurements.')
