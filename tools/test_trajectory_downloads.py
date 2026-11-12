"""Scientific/export regression checks; entirely offline."""
from pathlib import Path
import sys,hashlib,json,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import DAY,MU_SUN
from dynamics import kepler
from build_trajectory_downloads import sample_coasts

DOCS=Path(__file__).resolve().parents[1]/'docs'
class DownloadTests(unittest.TestCase):
    def test_every_public_candidate_has_consistent_downloads(self):
        index=json.loads((DOCS/'data/index.json').read_text())
        for row in index['cases']:
            with self.subTest(candidate=row['id']):
                c=json.loads((DOCS/'data/cases'/(row['id']+'.json')).read_text());files=c['trajectory_files']
                for key in ['csv','xyzv']:
                    file=DOCS/files[key];self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),files[key+'_sha256'])
                a=np.loadtxt(DOCS/files['csv'],delimiter=',',skiprows=1,encoding='utf-8');b=np.loadtxt(DOCS/files['xyzv'],comments='#',encoding='utf-8')
                self.assertEqual(a.shape,(files['rows'],7));self.assertTrue(np.isfinite(a).all());np.testing.assert_allclose(a,b,rtol=0,atol=1e-5)
                if c['model'] in ('Lambert candidate','Research patched-conic recreation'):
                    self.assertTrue(np.all(np.diff(a[:,0])>0));self.assertLessEqual(files['max_checked_hermite_position_error_km'],10.000001)
                else:self.assertEqual(files['xyzv_sha256'],c['provenance']['sha256'])
                self.assertTrue((DOCS/files['readme']).is_file())
    def test_eccentric_coast_retains_kepler_velocity_and_interpolation_accuracy(self):
        r=np.array([60000000.,0,0]);v=np.array([0.,50.,2.]);start=2451545.;coast=dict(start_jd=start,end_jd=start+120,r=r.tolist(),v=v.tolist())
        data,error=sample_coasts([coast]);self.assertLessEqual(error,10.)
        for a,b in zip(data[:-1],data[1:]):
            t=(b[0]-a[0])*DAY;fit=CubicHermiteSpline([0.,t],np.vstack([a[1:4],b[1:4]]),np.vstack([a[4:],b[4:]]))
            for f in [.1,.37,.63,.9]:
                dt=((a[0]+f*(b[0]-a[0]))-start)*DAY;rp,vp=kepler(r,v,dt)
                self.assertLess(np.linalg.norm(fit(f*t)-rp),12.)
            _,vp=kepler(r,v,(a[0]-start)*DAY);np.testing.assert_allclose(a[4:],vp,atol=1e-10)
    def test_velocity_jumps_are_bracketed_without_duplicate_epochs(self):
        r=np.array([149597870.7,0,0]);v=np.array([0.,29.78,0.]);start=2451545.;burn=start+5;rb,vb=kepler(r,v,5*DAY)
        coasts=[dict(start_jd=start,end_jd=burn,r=r.tolist(),v=v.tolist()),dict(start_jd=burn,end_jd=burn+5,r=rb.tolist(),v=(vb+np.array([.5,0,0])).tolist())]
        data,_=sample_coasts(coasts);self.assertTrue(np.all(np.diff(data[:,0])>0))
        k=int(np.flatnonzero(data[:,0]==burn)[0]);self.assertAlmostEqual((data[k,0]-data[k-1,0])*DAY,1.,delta=.0001)
        np.testing.assert_allclose(data[k,4:],vb+[.5,0,0],atol=1e-10)
if __name__=='__main__':unittest.main()
