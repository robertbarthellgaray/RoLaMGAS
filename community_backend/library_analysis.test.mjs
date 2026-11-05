import test from 'node:test';
import assert from 'node:assert/strict';
import {bodyCategory,encounterDayKey,betterDuplicate,filteredYears,sequenceColors,resolveAlias,filterStateFromHash,filterHash} from '../docs/library_analysis.js';
import {bodyName,summaryFor} from '../docs/community.js';
const base={id:'base',target:'Saturn',start:2463232.5,c3:40,years:8,vinf:6,burns_mps:500};
test('Sedna uses its JPL identity and targets split into distinct categories',()=>{
 assert.equal(bodyName('20090377'),'Sedna');assert.equal(bodyCategory('Sedna','20090377'),'Dwarf planets');assert.equal(bodyCategory('Ceres','20000001'),'Dwarf planets');assert.equal(bodyCategory('1P/Halley','1000036'),'Comets');assert.equal(bodyCategory('2026 ED138','54667839'),'Asteroids');assert.equal(bodyCategory('Titan','606'),'Other bodies');assert.equal(bodyCategory('Saturn','699'),'Planets');
});
test('same-day dedup respects TDB midnight and ordered encounters, independent of sequence annotation',()=>{
 const a={body_ids:['399','299','399','599'],dates_jd_tdb:[2463232.5,2463598.5,2463963.5,2465000.5]};
 assert.equal(encounterDayKey(a),encounterDayKey({...a,sequence:'EdvVEJ',dates_jd_tdb:a.dates_jd_tdb.map(t=>t+.99)}));assert.notEqual(encounterDayKey(a),encounterDayKey({...a,dates_jd_tdb:a.dates_jd_tdb.map(t=>t-.001)}));assert.notEqual(encounterDayKey(a),encounterDayKey({...a,body_ids:['399','399','299','599']}));
 const r={...a,id:'x',classification:'pass',metrics:{launch_c3_km2_s2:50,total_dsm_kms:.2,arrival_vinf_kms:5}};assert.equal(betterDuplicate({...r,id:'y',metrics:{...r.metrics,launch_c3_km2_s2:40}},r),true);assert.equal(betterDuplicate({...r,classification:'yellow',metrics:{...r.metrics,launch_c3_km2_s2:1}},r),false);
});
test('launch-year selection is inclusive and assist colors are distinct',()=>{
 assert.equal(filteredYears([base,{...base,start:2463598.5}],2032,2032).length,1);const colors=sequenceColors([{sequence:'EJ'},{sequence:'EVEEJ'},{sequence:'EdvEJ'}]);assert.equal(new Set(colors.values()).size,3);assert.equal(resolveAlias('old',{old:'new',new:'curated'}),'curated');assert.equal(resolveAlias('a',{a:'b',b:'a'}),'a');
});

test('target charts preserve launch-year range in shared deep links',()=>{
 const hash=filterHash({target:'Sedna',mission:'saved-id',launchMin:'2032',launchMax:'2038'});assert.deepEqual(filterStateFromHash(hash),{target:'Sedna',mission:'saved-id',launchMin:'2032',launchMax:'2038'});
 assert.deepEqual(filterStateFromHash('#mission=old-link'),{target:null,mission:'old-link',launchMin:'',launchMax:''});assert.equal(filterStateFromHash('#launch_from=NaN&launch_to=2038').launchMin,'');
});
