"""Hosted calculator parsing, caching and safe refresh regression checks."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from silverbird_performance import parse_result,parse_catalog,scenario,SilverBirdClient,checked_c3

SPEC=('test','India','Example launcher','121',[1,0,0,0],'011')
def form_script():
    return """var cname = new Array('Example');
var cflag = new Array('India');
var cval = new Array('121');
var sname = new Array('Example site');
var sflag = new Array('India');
var sval = new Array('011');
iswitch[0] = new Array('121',0,3,0,0,0,1,'Example model')
sswitch[0] = new Array('121',1,'011');
"""

def result(c3=10,declination=0,mass=1000,interval='500 - 1500'):
    # Mirrors the source's implicit th closing tag, with entirely synthetic values.
    return ('<table><tr><th>Launch Vehicle</th><td>Example model</td></tr>'
      '<tr><th>Launch Site</th><td>Example site</td></tr>'
      f'<tr><th>Escape Trajectory<td>C3 = {c3} km2/s2, {declination} deg</td></tr>'
      f'<tr><th>Estimated Payload</th><td>{mass} kg</td></tr>'
      f'<tr><th>95% Confidence Interval</th><td>{interval} kg</td></tr></table>')

class SilverBirdTests(unittest.TestCase):
    def test_form_options_and_implicit_cell_close(self):
        catalog=parse_catalog(form_script());fields,labels=scenario(SPEC,catalog,10)
        self.assertEqual(labels,['Example model']);self.assertEqual(fields['Ttype'],'3')
        self.assertEqual(fields['peri'],'200');self.assertEqual(fields['inc'],'0')
        parsed=parse_result(result(),fields)
        self.assertEqual(parsed['capacity_kg'],1000);self.assertEqual(parsed['confidence95_kg'],[500,1500])

    def test_bad_input_and_changed_conditions_fail_instead_of_inventing_capacity(self):
        for c3 in (-1,201,float('nan'),float('inf')):
            with self.assertRaises(ValueError):checked_c3(c3)
        fields,_=scenario(SPEC,parse_catalog(form_script()),10)
        for html in [result(c3=20),result(declination=5),result(interval='1100 - 1500'),'<html>Unavailable</html>']:
            with self.assertRaises(ValueError):parse_result(html,fields)
        zero=parse_result(result(mass=0,interval='0 - 100'),fields)
        self.assertEqual(zero['capacity_kg'],0)

    def test_cache_is_keyed_by_exact_conditions_and_refreshes_form(self):
        with tempfile.TemporaryDirectory() as tmp,patch('silverbird_performance.read_url') as read,patch('silverbird_performance.time.sleep'):
            read.side_effect=lambda url,fields=None:form_script() if fields is None else result(c3=fields['apo'])
            client=SilverBirdClient(tmp);a=client.query(SPEC,10);b=client.query(SPEC,10);c=client.query(SPEC,15)
            self.assertFalse(a['from_cache']);self.assertTrue(b['from_cache']);self.assertEqual(c['c3_km2_s2'],15)
            self.assertEqual(read.call_count,3)
            SilverBirdClient(tmp);self.assertEqual(read.call_count,3)
            SilverBirdClient(tmp,refresh_catalog=True);self.assertEqual(read.call_count,4)

    def test_rebuilder_preserves_sampled_curves_without_synthetic_models(self):
        from tools.extend_launch_capacity import extend
        data=json.loads((Path(__file__).parent/'gui_assets/launch_performance_curves.json').read_text(encoding='utf-8'))
        before=[v for v in data['vehicles'] if v.get('silverbird_id')]
        after=extend({'vehicles':before})
        self.assertEqual(after['vehicles'],before)

if __name__=='__main__':unittest.main()
