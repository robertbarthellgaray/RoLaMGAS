import assert from 'node:assert/strict';
import {reportModel} from './docs/trajectory_pdf.js';
const c={sequence:'EVEEJ',id:'abc123',target:'Jupiter',c3:11.97,burns_mps:0,vinf:7.123,years:5.4,
 launch_date:'2030-01-01',arrival_date:'2035-05-26',events:[
  {body:'Earth',jd:2462502.5,date:'2030-01-01T00:00:00 TDB',kind:'Departure'},
  {body:'Venus',jd:2462602.5,date:'2030-04-11T00:00:00 TDB',kind:'Flyby'},
  {body:'Earth',jd:2462802.5,date:'2030-10-28T00:00:00 TDB',altitude_km:0,kind:'Flyby'},
  {body:'Jupiter',jd:2464475.5,date:'2035-05-26T00:00:00 TDB',kind:'Arrival'}],
 flybys:[{body:'Venus',jd:2462602.5,altitude_km:352.45,mismatch_mps:.012}],
 burns:[{kind:'Coast 1 targeting correction',jd:2462600,magnitude_mps:.004},{kind:'DSM',jd:2462700,date:'2030-07-18T00:00:00 TDB',magnitude_mps:123.45},{kind:'DSM',jd:2462550,magnitude_mps:0}]};
const report=reportModel(c,{estimates:[{body:'Venus',jd:2462602.5,estimated_altitude_km:999}],title:'Example'});
assert.equal(report.sequence,'EVEEJ');assert.equal(report.metrics[1].value,'0.0');
assert.equal(report.rows.find(r=>r.name==='Venus').altitude,352.45,'Saved flyby takes priority over estimates');
assert.equal(report.rows.find(r=>r.name==='Earth'&&r.isFlyby).altitude,0,'Zero altitude is an actual value');
assert.equal(report.rows.find(r=>r.burn).details,'Δv 123.450 m/s');assert.equal(report.rows.length,5);
assert.deepEqual(report.rows.map(r=>r.jd),report.rows.map(r=>r.jd).sort((a,b)=>a-b));
const missing=reportModel({...c,flybys:[],events:c.events.map(e=>({...e,altitude_km:null}))});
assert.equal(missing.rows.find(r=>r.name==='Venus').altitude,null);assert.ok(missing.notes.some(n=>n.includes('Not available')));
const estimated=reportModel({...c,flybys:[]},{estimates:[{body:'Venus',jd:2462602.5,estimated_altitude_km:800}]});
assert.equal(estimated.rows.find(r=>r.name==='Venus').altitudeBasis,'Estimated');
assert.ok(report.notes.some(n=>n.includes('Launch injection and capture are excluded')));
console.log('PASS: report metrics, zero/missing/estimated altitudes, DSM chronology, hidden zero corrections and budget labels.');
