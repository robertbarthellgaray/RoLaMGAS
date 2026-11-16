// A shared launch day alone is not sufficient: preserve material differences
// in flyby dates, launch energy, cruise burns and arrival speed.
export function launchVariantKey(record){return JSON.stringify([record.body_ids,record.sequence,Math.floor(record.dates_jd_tdb[0]+.5)]);}
export function nearDuplicate(a,b){
 const preserved=['864ca8c31892f68454fb39dbed6bbeb3a76f8af3b7d676552f097cb870e862b0','faaebce61e7087814c1e25522e0daa12697e5c8526c11d68c7bfa3e749d7023d','72be12f1d7161478b149716766f4432aeaa5f495f29bd8fcdc9437aebf42d5af'];
 if(preserved.some(id=>a.id===id||b.id===id))return false;
 if(launchVariantKey(a)!==launchVariantKey(b)||a.dates_jd_tdb.length!==b.dates_jd_tdb.length)return false;
 if(a.dates_jd_tdb.some((t,i)=>Math.abs(t-b.dates_jd_tdb[i])>7))return false;
 const x=a.metrics,y=b.metrics;
 return Math.abs(x.launch_c3_km2_s2-y.launch_c3_km2_s2)<=Math.max(.5,.02*Math.min(x.launch_c3_km2_s2,y.launch_c3_km2_s2))
  &&Math.abs(x.total_dsm_kms-y.total_dsm_kms)<=.05
  &&Math.abs(x.arrival_vinf_kms-y.arrival_vinf_kms)<=.2
  &&Math.abs(x.max_vinf_mismatch_mps-y.max_vinf_mismatch_mps)<=1;
}
