import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import '../mission_metrics.js';
import {chartSettingsFromHash,withChartSettings} from '../docs/library_analysis.js';
const m=globalThis.MissionMetrics;
const rows=[{id:'a',sequence:'EVEEJ',status:'passes_configured_patched_conic_screen',dates_jd_tdb:[2462502.5,2465424.5],launch_c3_km2_s2:12,arrival_vinf_kms:5,total_dsm_kms:.2},
 {id:'b',sequence:'EJ',status:'passes_configured_patched_conic_screen',dates_jd_tdb:[2462867.75,2465059.25],launch_c3_km2_s2:40,arrival_vinf_kms:9,total_dsm_kms:0}];
test('all 36 axis combinations retain the exact saved values, including date fractions',()=>{
 for(const x of Object.keys(m.chartMetrics))for(const y of Object.keys(m.chartMetrics)){
  const plot=m.chartModel(rows,{x,y});assert.equal(plot.points.length,2);
  for(const p of plot.points){assert.equal(p.x,m.chartValue(p.row,x));assert.equal(p.y,m.chartValue(p.row,y));assert.ok(Number.isFinite(m.chartPosition(p.x,plot.xDomain)));}
 }
 assert.equal(m.chartValue(rows[1],'departure'),2462867.75);assert.equal(m.chartValue(rows[1],'years'),6);
 assert.equal(m.chartValue(rows[0],'burns'),200);assert.equal(m.chartValue(rows[1],'burns'),0);
});
test('public summaries and app candidates use identical plotted costs and dates',()=>{
 const site={sequence:'EVEEJ',start:2462502.5,end:2465424.5,c3:12,vinf:5,burns_mps:200,years:99};
 for(const metric of Object.keys(m.chartMetrics))assert.equal(m.chartValue(rows[0],metric),m.chartValue(site,metric));
 assert.equal(m.chartEpoch({launch_date:'2030-01-01T06:00:00 TDB'}),2462502.75);
 assert.equal(m.chartEpoch({launch_date:'2030-01-01'}),2462502.5);
 assert.ok(Number.isNaN(m.chartEpoch({launch_date:'garbage'})));
});
test('date domains zoom to actual epochs and never extrapolate to Julian day zero',()=>{
 const model=m.chartModel(rows,{x:'departure',y:'arrival',color:'c3'});
 assert.ok(model.xDomain[0]>2462000);assert.ok(model.yDomain[0]>2465000);assert.equal(model.sampledDates,true);
 assert.match(m.chartGrid(model),/2030-\d{2}-\d{2}/);assert.doesNotMatch(m.chartGrid(model),/NaN|Infinity/);
 assert.match(m.chartColorLegend(model),/Color: Launch C3/);
 assert.notEqual(model.points[0].fill,model.points[1].fill);
});
test('missing or nonfinite metrics are skipped rather than silently plotted as zero',()=>{
 const a={...rows[0],arrival_vinf_kms:null},b={...rows[1],arrival_vinf_kms:Infinity};
 const model=m.chartModel([a,b],{y:'vinf'});assert.equal(model.points.length,0);assert.equal(model.skipped,2);
 const missing=m.chartModel([a,rows[1]],{color:'vinf'});assert.equal(missing.points.length,1);assert.equal(missing.skipped,1);
 assert.deepEqual(m.chartOptions({x:'__proto__',y:'toString',color:'constructor'}),{x:'years',y:'c3',color:'sequence'});
});
test('single-valued and empty ranges remain finite with stable midpoint colors',()=>{
 for(const model of [m.chartModel([rows[0]],{x:'departure',y:'arrival',color:'c3'}),m.chartModel([])]){
  assert.ok(model.xDomain[1]>model.xDomain[0]);assert.ok(model.yDomain[1]>model.yDomain[0]);assert.doesNotMatch(m.chartGrid(model),/NaN|Infinity/);
 }
 assert.match(m.chartColor(12,[12,12]),/^rgb\(\d+,\d+,\d+\)$/);
 assert.match(m.chartTick(2462502.75,'departure',.1),/01-01 06:00/);
});
test('chart deep links retain mission filters and upgrade legacy axis links',()=>{
 const hash=withChartSettings('#mission=abc&target=Jupiter&axis=vinf&max_c3=30',{x:'departure',y:'arrival',color:'c3'});
 assert.deepEqual(chartSettingsFromHash(hash),{x:'departure',y:'arrival',color:'c3'});assert.match(hash,/mission=abc/);assert.match(hash,/max_c3=30/);
 assert.deepEqual(chartSettingsFromHash('#axis=vinf'),{x:'years',y:'vinf',color:'sequence'});
 assert.deepEqual(chartSettingsFromHash(withChartSettings(hash,{x:'years',y:'c3',color:'sequence'})),{x:'years',y:'c3',color:'sequence'});
 assert.deepEqual(chartSettingsFromHash('#chart_x=unknown&chart_y=bad&chart_color=evil'),{x:'years',y:'c3',color:'sequence'});
});
function app(){
 const elements={};const node=tag=>({tag,children:[],attrs:{},style:{},dataset:{},value:'',set innerHTML(v){this.html=v;this.children=[]},get innerHTML(){return this.html},append(...v){this.children.push(...v)},prepend(v){this.children.unshift(v)},replaceChildren(...v){this.children=[...v]},setAttribute(k,v){this.attrs[k]=String(v)},closest(){return this}});
 for(const id of ['resultsChart','resultsChartLegend','resultsChartTitle','resultsChartStatus','chartColorLegend','chartSamplingNote','chartX','chartY','chartColor','chartYearFrom','chartYearTo'])elements[id]=node('div');
 const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:node,createElementNS:(_,tag)=>node(tag)}});
 vm.runInContext(fs.readFileSync(new URL('../mission_metrics.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8').split("$('reuse').onclick=")[0],context);
 const run=code=>vm.runInContext(code,context);run('state.rows='+JSON.stringify(rows)+';state.limits={}');return {run,elements,context};
}
test('desktop swaps both axes and date points still inspect using the original candidate ID',()=>{
 const a=app();a.elements.chartX.value='c3';a.elements.chartY.value='years';a.run('renderResultsChart(state.rows)');
 let dots=a.elements.resultsChart.children;assert.ok(+dots[0].attrs.cx<+dots[1].attrs.cx);assert.ok(+dots[0].attrs.cy<+dots[1].attrs.cy);
 a.elements.chartX.value='departure';a.elements.chartY.value='arrival';a.elements.chartColor.value='c3';a.run('inspect=id=>globalThis.chosen=id;renderResultsChart(state.rows)');
 dots=a.elements.resultsChart.children;assert.notEqual(dots[0].attrs.fill,dots[1].attrs.fill);assert.equal(a.elements.chartSamplingNote.hidden,false);assert.equal(a.elements.chartColorLegend.hidden,false);
 a.elements.resultsChart.onkeydown({type:'keydown',key:'Enter',target:dots[1],preventDefault(){}});assert.equal(a.context.chosen,'b');
});
test('website uses shared chart values and keeps sequence filters independent of numeric colors',()=>{
 const elements={};for(const id of ['chart-x','chart-y','chart-color','tradeoff-chart','tradeoff-svg','chart-color-legend','chart-sampling-note','tradeoff-legend','tradeoff-status'])elements[id]={value:'',setAttribute(){},replaceChildren(){}};
 elements['chart-x'].value='departure';elements['chart-y'].value='arrival';elements['chart-color'].value='c3';
 const publicRows=rows.map(r=>({...r,start:r.dates_jd_tdb[0],end:r.dates_jd_tdb.at(-1),c3:r.launch_c3_km2_s2,years:m.chartValue(r,'years'),vinf:r.arrival_vinf_kms,burns_mps:r.total_dsm_kms*1000,launch_date:'2030-01-01',arrival_date:'2038-01-01'}));
 const context=vm.createContext({MissionMetrics:m,$:id=>elements[id],selectedTarget:()=> 'Jupiter',visibleRows:()=>publicRows,matchingRows:()=>publicRows,targetRows:()=>publicRows,sequenceColors:()=>new Map([['EVEEJ','red'],['EJ','blue']]),selectedSequence:'',selected:null,escapeHtml:s=>String(s).replaceAll('<','&lt;'),fmt:v=>String(v),launchYear:r=>new Date((r.start-2440587.5)*86400000).getUTCFullYear()});
 const source=fs.readFileSync(new URL('../docs/app.js',import.meta.url),'utf8');vm.runInContext(source.slice(source.indexOf('function webChartOptions()'),source.indexOf('function renderFlybyDiagnostics(c)')),context);vm.runInContext('drawTradeoff()',context);
 assert.equal((elements['tradeoff-svg'].innerHTML.match(/class="tradeoff-point"/g)||[]).length,2);assert.match(elements['tradeoff-legend'].innerHTML,/data-sequence="EVEEJ"/);assert.doesNotMatch(elements['tradeoff-legend'].innerHTML,/sequence-swatch/);assert.equal(elements['chart-sampling-note'].hidden,false);
});
