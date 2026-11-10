"""Horizons tables must bracket requested windows without extrapolation."""
import bootstrap
import math,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse
import numpy as np
from ephemeris import AU,DAY,JD0,Ephemerides,fetch,jd
from horizons_targets import register_target
from mission_search import normalize,routes_for,prepare,get_ephemerides

TARGET=dict(name='486958 Arrokoth (2014 MU69)',id='20486958',command='486958;',kind='small_body',designation='486958')

class DownloadCoverageTests(unittest.TestCase):
    @staticmethod
    def horizons_response(url,**kwargs):
        # Horizons emits START + n*STEP samples through (not beyond) STOP.
        params={k:v[0].strip("'") for k,v in parse_qs(urlparse(url).query).items()}
        start=float(params['START_TIME'][2:]);stop=float(params['STOP_TIME'][2:])
        step=int(params['STEP_SIZE'].split()[0])/1440
        earth=params['COMMAND']=='399'
        header=('Target body name: Earth (399)' if earth else 'Target body name: '+TARGET['name'])
        header+='\nCenter body name: Sun (10)\nOutput units : KM-S\nGEOMETRIC cartesian states\nEcliptic of J2000.0\nJDTDB,\n$$SOE\n'
        rows=[]
        for n in range(math.floor((stop-start)/step+1e-7)+1):
            date=datetime(2000,1,1)+timedelta(days=start-JD0+n*step)
            # Real API calendar dates are rounded to four fractional seconds.
            seconds=round((date-datetime(2000,1,1)).total_seconds(),4)
            date=datetime(2000,1,1)+timedelta(seconds=seconds)
            rows.append(f"{JD0+seconds/DAY:.10f}, A.D. {date.strftime('%Y-%b-%d %H:%M:%S.%f')}, {AU+seconds},0,0,1,0,0,")
        return dict(result=header+'\n'.join(rows)+'\n$$EOE')

    def setUp(self):register_target(TARGET)

    def test_fractional_start_and_unaligned_stop_are_fully_covered(self):
        start=2453338.500009949;end=2459294.5
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=self.horizons_response) as network:
            fetch(cache,TARGET['name'],start,end,1.)
            ep=Ephemerides(cache,[TARGET['name']],start,end,1.)
            self.assertTrue(np.isfinite(ep.state(TARGET['name'],start)).all())
            self.assertTrue(np.isfinite(ep.state(TARGET['name'],end)).all())
            self.assertEqual(network.call_count,1)
            spline=ep.splines[TARGET['name']]
            with self.assertRaisesRegex(ValueError,'extrapolation'):
                ep.state(TARGET['name'],JD0+spline.x[-1]/DAY+1)

    def test_short_window_has_enough_samples_for_parser(self):
        start=jd('2030-01-01T00:00:00.123456');end=start+5/1440
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=self.horizons_response):
            fetch(cache,TARGET['name'],start,end,1.)
            ep=Ephemerides(cache,[TARGET['name']],start,end,1.)
            self.assertGreaterEqual(len(ep.splines[TARGET['name']].x),4)
            ep.state(TARGET['name'],end)

    def test_date_only_vector_response_retries_and_validates_full_state(self):
        def response(url,**kwargs):
            result=self.horizons_response(url,**kwargs)
            table=parse_qs(urlparse(url).query)['VEC_TABLE'][0].strip("'")
            if table=='2':
                header,data=result['result'].split('$$SOE')
                rows=data.split('$$EOE')[0].strip().splitlines()
                result['result']=header+'$$SOE\n'+'\n'.join(','.join(r.split(',')[:2])+',' for r in rows)+'\n$$EOE'
            else:
                self.assertEqual(table,'2x')
                result['result']=result['result'].replace('JDTDB,','JDTDB             Calendar Date (TDB),')
            return result
        start=jd('1997-10-01');end=start+8
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=response) as network:
            fetch(cache,'Earth',start,end,1.)
            self.assertEqual(network.call_count,2)
            ep=Ephemerides(cache,['Earth'],start,end,1.)
            self.assertTrue(np.isfinite(ep.state('Earth',start+2)).all())

    def test_date_only_retry_cannot_be_saved_as_an_ephemeris(self):
        def response(url,**kwargs):
            good=self.horizons_response(url,**kwargs)['result'];header,data=good.split('$$SOE')
            rows=data.split('$$EOE')[0].strip().splitlines()
            return dict(result=header+'$$SOE\n'+'\n'.join(','.join(r.split(',')[:2])+',' for r in rows)+'\n$$EOE')
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=response) as network:
            with self.assertRaisesRegex(ValueError,'missing position/velocity'):
                fetch(cache,'Earth',jd('1997-10-01'),jd('1997-10-09'),1.)
            self.assertEqual(network.call_count,2)
            self.assertEqual(list(Path(cache).iterdir()),[])

    def test_prepare_handles_fractional_epochs_and_second_pass_is_offline(self):
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=self.horizons_response) as network:
            c=normalize(dict(target_object=TARGET,sequences=['EX'],cache=cache,launch_start='2004-12-01T00:00:00.8596',launch_end='2004-12-02',custom_leg_days=[120,500]))
            routes=routes_for(c)
            prepare(c,routes)
            calls=network.call_count
            self.assertEqual(calls,2)
            prepare(c,routes)
            ep=get_ephemerides(c,routes)
            from mission_search import coverage
            start,end=coverage(c,routes)
            for body in routes[0]['bodies']:
                ep.state(body,start);ep.state(body,end)
            self.assertEqual(network.call_count,calls)

    def test_fractional_minute_cadence_does_not_exceed_requested_maximum(self):
        with tempfile.TemporaryDirectory() as cache,patch('ephemeris.request_json',side_effect=self.horizons_response):
            start=jd('2030-01-01');end=start+10/1440
            fetch(cache,TARGET['name'],start,end,1.6/1440)
            Ephemerides(cache,[TARGET['name']],start,end,1.6/1440)

if __name__=='__main__':unittest.main()
