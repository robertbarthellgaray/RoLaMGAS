export function exportRecordId(c){return c?.community_record?.id||c?.desktop_record?.id||c?.id||'';}
export async function sharedExportDownloads(c,endpoint){
 const id=exportRecordId(c);if(!/^[a-f0-9]{64}$/.test(id)||!endpoint)return [];
 const response=await fetch(endpoint+'/v1/exports?'+new URLSearchParams({candidate:id}));if(!response.ok)return [];
 const data=await response.json();if(!data.storage_ready)return [];
 return (data.exports||[]).filter(row=>/^[a-f0-9]{64}$/.test(row.export_id)&&/^[a-f0-9]{64}$/.test(row.candidate_id)).sort((a,b)=>b.added_at.localeCompare(a.added_at)).map(row=>({...row,url:endpoint+'/v1/exports/'+row.candidate_id+'/'+row.export_id}));
}
export function appendSharedExports(container,rows){
 if(!rows.length)return;const section=document.createElement('section');section.className='shared-export-downloads';const title=document.createElement('h3');title.textContent='Shared integrated trajectories';section.append(title);
 const note=document.createElement('p');note.className='quiet small';note.textContent='Propagated files uploaded by desktop users, with their numerical/clearance checks. The server does not independently validate dynamics. Each export can have different flyby dates, altitude or inclination settings.';section.append(note);
 for(const row of rows){const group=document.createElement('div'),label=document.createElement('p');label.textContent=`${row.export_kind==='moon'?'Moon-targeted':'Planet flyby'} export · ${row.added_at.replace('T',' ').replace('Z',' UTC')} · ${(row.rows||0).toLocaleString()} states · C3 ${Number(row.exported_launch_c3_km2_s2).toFixed(2)} · Total onboard Δv ${Number(row.total_onboard_delta_v_kms).toFixed(4)} km/s · Patch corrections ${Number(row.patch_join_delta_v_kms||0).toFixed(4)} km/s`;group.append(label);
  if(row.passes_original_onboard_budget===false){const warning=document.createElement('p');warning.className='warning small';warning.textContent='This export exceeds its original maneuver budget.';group.append(warning);}
  for(const [file,label]of [['trajectory.xyzv','Integrated XYZV ↓'],['trajectory.csv','Integrated CSV ↓'],['burns.csv','Burn table ↓'],['validation.json','Validation summary ↓']]){const a=document.createElement('a');a.className='text-link small';a.href=row.url+'/'+file;a.textContent=label;a.setAttribute('download','');group.append(a,document.createTextNode('  '));}section.append(group);
 }container.append(section);container.hidden=false;
}
