import bootstrap
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from launch_performance import FormParser,parse_result,capacity_query,checked_c3

def table(c3=28,orbit='High Energy',empty=False):
    head='<table><tr><td>Orbit Class:</td><td>'+orbit+'</td></tr><tr><td>C3 (km2/sec2):</td><td>'+str(c3)+'</td></tr></table>'
    if empty:return head+'There are no results.'
    return head+'<table><tr><th>Plot</th><th>Vehicle</th><th>Launch Site</th><th>Capability, kg</th><th>Fairing</th><th>Adapter</th><th>Ground Rules</th></tr><tr><td></td><td>Falcon Heavy<br>(Recovery)</td><td>KSC</td><td>2,955</td><td>5.2m</td><td>1194mm</td><td><li>Recovery included</li><li>3-sigma reserves</li></td></tr><tr><td></td><td>Falcon Heavy<br>(Expendable)</td><td>KSC</td><td>8585</td><td>5.2m</td><td>1194mm</td><td>Instantaneous launch</td></tr></table>'

class LaunchPerformanceTests(unittest.TestCase):
    def test_real_table_shape_keeps_distinct_configurations_and_ground_rules(self):
        result=parse_result(table(),28);self.assertEqual(len(result['vehicles']),2)
        self.assertEqual(result['vehicles'][0]['vehicle'],'Falcon Heavy (Recovery)')
        self.assertEqual(result['vehicles'][0]['capacity_kg'],2955)
        self.assertIn('3-sigma',result['vehicles'][0]['ground_rules'])
        self.assertEqual(result['vehicles'][1]['capacity_kg'],8585)
    def test_wrong_condition_or_changed_table_never_produces_fake_capacity(self):
        for html in (table(c3=30),table(orbit='LEO Circular'),'<html>Service unavailable</html>'):
            with self.assertRaises(ValueError):parse_result(html,28)
        empty=parse_result(table(empty=True),28);self.assertEqual(empty['availability'],'no_vehicles_listed');self.assertEqual(empty['vehicles'],[])
    def test_invalid_c3_is_rejected_before_any_request(self):
        with tempfile.TemporaryDirectory() as tmp,patch('launch_performance.NASAClient') as client:
            for value in (-1,float('nan'),float('inf'),251):
                with self.assertRaises(ValueError):capacity_query(value,Path(tmp))
            client.assert_not_called()
    def test_cache_uses_exact_c3_instead_of_relabeling_a_previous_query(self):
        with tempfile.TemporaryDirectory() as tmp,patch('launch_performance.NASAClient') as client:
            client.return_value.query.side_effect=lambda value:parse_result(table(c3=value),value)
            a=capacity_query(28,tmp);b=capacity_query(28,tmp);c=capacity_query(29,tmp)
            self.assertFalse(a['from_cache']);self.assertTrue(b['from_cache']);self.assertEqual(client.return_value.query.call_count,2)
            self.assertEqual(c['c3_km2_s2'],29)
    def test_postback_preserves_hidden_state_and_only_checked_enabled_controls(self):
        p=FormParser();p.feed('<input name="__VIEWSTATE" value="state"><input type="radio" name="orbit" value="LEO"><input type="radio" name="orbit" value="High Energy" checked><input name="altitude" value="200" disabled><select name="site"><option value="KSC">KSC</option><option value="VAFB" selected>VAFB</option></select>')
        self.assertEqual(p.fields,{'__VIEWSTATE':'state','orbit':'High Energy','site':'VAFB'})
if __name__=='__main__':unittest.main()
