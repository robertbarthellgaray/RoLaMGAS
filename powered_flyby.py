"""A conservative, explicit impulse joining two hyperbolas at common periapsis."""
import math
import numpy as np
from scipy.optimize import brentq


def geometry(mu,minimum_radius,incoming,outgoing,maximum_radius):
    incoming=np.asarray(incoming,dtype=float);outgoing=np.asarray(outgoing,dtype=float)
    ni=float(np.linalg.norm(incoming));no=float(np.linalg.norm(outgoing))
    a=incoming/ni;b=outgoing/no;c=float(np.clip(a@b,-1,1))
    normal=np.cross(a,b);s=float(np.linalg.norm(normal))
    if min(ni,no)<1e-8 or s<1e-10:raise ValueError('Degenerate common-periapsis powered-flyby geometry')
    angle=math.atan2(s,c)
    def natural(radius):return math.asin(1/(1+radius*ni*ni/mu))+math.asin(1/(1+radius*no*no/mu))
    radius=float(minimum_radius)
    if maximum_radius<=radius:raise ValueError('Powered-flyby periapsis lies outside the patch boundary')
    if angle<natural(radius):
        if angle<natural(maximum_radius):raise ValueError('Common-periapsis powered flyby requires a periapsis outside the patch boundary')
        radius=brentq(lambda r:natural(r)-angle,radius,maximum_radius,xtol=1e-7)
    si=1/(1+radius*ni*ni/mu);so=1/(1+radius*no*no/mu)
    # Incoming a.p=sin(alpha_in); outgoing b.p=-sin(alpha_out).
    x=(si+c*so)/(1-c*c);y=(-so-c*si)/(1-c*c)
    p0=x*a+y*b
    if p0@p0>1+1e-8:raise ValueError('No common above-floor periapsis for these asymptotes')
    p=p0+math.sqrt(max(0.,1-float(p0@p0)))*normal/s;p/=np.linalg.norm(p)
    ti=(a-si*p)/math.sqrt(1-si*si);to=(b+so*p)/math.sqrt(1-so*so)
    vi=math.sqrt(ni*ni+2*mu/radius)*ti;vo=math.sqrt(no*no+2*mu/radius)*to
    return dict(periapsis_radius_km=radius,peri_position_km=(radius*p).tolist(),
                peri_in_velocity_kms=vi.tolist(),peri_out_velocity_kms=vo.tolist(),
                delta_v_vector_kms=(vo-vi).tolist(),magnitude_kms=float(np.linalg.norm(vo-vi)),
                model='One ideal impulse at a common periapsis, preserving both asymptotes and the altitude floor. Conservative feasible construction, not a minimum-fuel powered flyby.')
