// PDF reports use the selected candidate's saved numbers and optional, labeled
// JPL-context flyby estimates. No trajectory search or propagation is performed.
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const number=(value,digits=2)=>finite(value)?value.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'Not available';
const sameEpoch=(a,b)=>finite(a)&&finite(b)&&Math.abs(a-b)<1e-4;
const nonzeroBurn=burn=>finite(burn.magnitude_mps)&&burn.magnitude_mps>1e-6&&!(/(?:coast.*targeting correction|targeting correction.*coast)/i.test(burn.kind||'')&&burn.magnitude_mps<.005);

export function reportModel(candidate,{title='',estimates=[],estimateNote='',sourceUrl=''}={}){
 const c=candidate,events=(c.events||[]).map((event,index)=>{
  const saved=(c.flybys||[]).find(f=>sameEpoch(f.jd,event.jd)&&(!f.body||f.body===event.body));
  const estimate=estimates.find(f=>sameEpoch(f.jd,event.jd)&&f.body===event.body);
  let altitude=null,altitudeBasis='';
  if(finite(event.altitude_km)){altitude=event.altitude_km;altitudeBasis='Saved';}
  else if(finite(saved?.altitude_km)){altitude=saved.altitude_km;altitudeBasis='Inferred';}
  else if(finite(estimate?.estimated_altitude_km)){altitude=estimate.estimated_altitude_km;altitudeBasis='Estimated';}
  const details=[event.kind|| (index===0?'Departure':index===(c.events.length-1)?'Arrival':'Flyby')];
  const gap=saved?.mismatch_mps??estimate?.mismatch_mps;
  if(finite(gap))details.push(`V∞ gap ${number(gap,gap<.01?6:3)} m/s`);
  if(finite(saved?.powered_mps)&&saved.powered_mps>0)details.push(`Powered ${number(saved.powered_mps,2)} m/s`);
  return {name:event.body||event.kind||'Encounter',jd:event.jd,date:event.date||'',altitude,altitudeBasis,isFlyby:index>0&&index<c.events.length-1,details:details.join('\n')};
 });
 const burns=(c.burns||[]).filter(nonzeroBurn).map(b=>({name:b.kind||'DSM',jd:b.jd,date:b.date||'',altitude:null,altitudeBasis:'',details:`Δv ${number(b.magnitude_mps,3)} m/s`,burn:true}));
 const rows=[...events,...burns].sort((a,b)=>a.jd-b.jd),notes=[];
 if(events.some(e=>e.altitudeBasis==='Inferred'))notes.push('Inferred altitudes come from saved asymptotic flyby turns; they are not propagated closest approaches.');
 if(events.some(e=>e.altitudeBasis==='Estimated'))notes.push('Estimated altitudes use interpolated JPL context and a common-periapsis construction; they are not finite-radius validation.');
 if(events.some((e,i)=>i>0&&i<events.length-1&&e.altitude===null))notes.push('Not available means no usable flyby altitude was saved or could be estimated for this encounter.');
 if(estimateNote)notes.push(estimateNote);
 notes.push('DSM / cruise Δv is the saved modeled cruise budget. Launch injection and capture are excluded; unresolved flyby gaps are not correction burns.');
 const mismatch=c.validation?.max_vinf_mismatch_mps??c.community_record?.metrics?.max_vinf_mismatch_mps??c.mismatch_max_mps;
 if(finite(mismatch)&&mismatch>100)notes.push(`Unresolved flyby continuity: maximum saved V∞ speed gap ${number(mismatch,2)} m/s.`);
 if(c.research_altitude_exception)notes.push(c.research_altitude_exception);
 if(c.review_warning)notes.push('Needs flyby revalidation: '+c.review_warning.reason+'.');
 if(c.trajectory_files?.finite_radius)notes.push('Figures describe the selected preview candidate. Its finite-radius trajectory download can have adjusted dates and additional patch burns.');
 return {sequence:c.sequence||c.title||'Trajectory',title,id:String(c.id||''),target:c.target||'',rows,notes,
  metrics:[{label:'Launch C3',value:number(c.c3,3),unit:'km²/s²'},
   {label:'DSM / cruise Δv',value:number(c.burns_mps,finite(c.burns_mps)&&c.burns_mps>0&&c.burns_mps<.1?3:1),unit:'m/s'},
   {label:'Arrival V∞',value:number(c.vinf,3),unit:'km/s'},
   {label:'Flight time',value:number(c.years,3),unit:'years'}],
  dates:`${c.launch_date||''} → ${c.arrival_date||''} · TDB`,sourceUrl,credit:c.provenance?.credit||'',model:c.model||'Saved trajectory'};
}

let dependencies;
async function loadDependencies(){
 if(!dependencies)dependencies=(async()=>{
  if(!globalThis.jspdf?.jsPDF)await new Promise((resolve,reject)=>{
   const script=document.createElement('script'),timer=setTimeout(()=>{script.remove();reject(Error('PDF library download timed out. Try again.'));},20000);
   script.src=new URL('./vendor/pdf/jspdf.umd.min.js',import.meta.url).href;
   script.onload=()=>{clearTimeout(timer);globalThis.jspdf?.jsPDF?resolve():reject(Error('PDF library did not initialize.'));};
   script.onerror=()=>{clearTimeout(timer);script.remove();reject(Error('Could not load the PDF library. Try again.'));};document.head.append(script);
  });
  const fonts=await Promise.all(['Regular','Bold'].map(async name=>{
   const response=await fetch(new URL(`./vendor/pdf/NotoSans-${name}.ttf`,import.meta.url),{signal:AbortSignal.timeout(20000)});
   if(!response.ok)throw Error('Could not load PDF fonts. Try again.');
   const bytes=new Uint8Array(await response.arrayBuffer());let binary='';
   for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
   return {name,base64:btoa(binary)};
  }));return {jsPDF:globalThis.jspdf.jsPDF,fonts};
 })().catch(error=>{dependencies=null;throw error});
 return dependencies;
}

export async function trajectoryPdf(candidate,options){
 const model=reportModel(candidate,options),{jsPDF,fonts}=await loadDependencies();
 const doc=new jsPDF({unit:'mm',format:'a4',compress:true,putOnlyUsedFonts:true});
 for(const font of fonts){const name=`NotoSans-${font.name}.ttf`;doc.addFileToVFS(name,font.base64);doc.addFont(name,'NotoSans',font.name==='Bold'?'bold':'normal');}
 doc.setProperties({title:`${model.sequence} · ${model.target} · ${model.id}`,subject:'RoLaMGAS trajectory and flyby itinerary',author:'RoLaMGAS — Robert Barthell Garay',creator:'RoLaMGAS website'});
 const left=17,width=176,bottom=278,line=4.1,ink=[25,43,57],muted=[82,103,117],accent=[27,108,131];let y=16;
 const font=(size=9,bold=false)=>{doc.setFont('NotoSans',bold?'bold':'normal');doc.setFontSize(size);};
 const pdfText=value=>String(value).replaceAll('∞','-inf').replaceAll('→','to');
 function text(value,x,at,size=9,bold=false,color=ink){font(size,bold);doc.setTextColor(...color);doc.text(Array.isArray(value)?value.map(pdfText):pdfText(value),x,at,{lineHeightFactor:1.35});}
 function wrap(value,w,size=9,bold=false){font(size,bold);return doc.splitTextToSize(pdfText(value),w);}
 function nextPage(){doc.addPage();y=18;text(`${model.sequence} · ${model.target}`,left,y,11,true);y+=7;text(`ID ${model.id}`,left,y,7,false,muted);y+=10;}
 function paragraph(value,size=8.1){const lines=wrap(value,width,size);for(const item of lines){if(y+line>bottom)nextPage();text(item,left,y,size,false,muted);y+=line;}y+=2;}
 text('RoLaMGAS / TRAJECTORY REPORT',left,y,8,true,accent);y+=11;
 const heading=wrap(`${model.sequence} · ${model.target}`,width,21,true);text(heading,left,y,21,true);y+=heading.length*9;
 text(`ID ${model.id}`,left,y,7.5,false,muted);y+=7;
 if(model.title&&model.title!==model.sequence){const lines=wrap(model.title,width,9);text(lines,left,y,9,false,muted);y+=lines.length*4.5+2;}
 const imageHeight=width*options.plot.height/options.plot.width;
 doc.addImage(options.plot,'JPEG',left,y,width,imageHeight,undefined,'FAST');y+=imageHeight+4;
 text(model.dates,left,y,8,false,muted);y+=6;
 doc.setFillColor(237,244,247);doc.roundedRect(left,y,width,23,2,2,'F');
 model.metrics.forEach((metric,i)=>{const x=left+i*width/4+4;text(metric.label,x,y+5.5,7.5,false,muted);text(metric.value,x,y+13.5,14,true);text(metric.unit,x,y+19,7.5,false,muted);});y+=32;
 const columns=[{label:'Event',width:34},{label:'Calendar · TDB',width:39},{label:'Julian date · TDB',width:32},{label:'Altitude · km',width:30},{label:'Details',width:41}];
 function tableHeading(){doc.setFillColor(...ink);doc.rect(left,y,width,8,'F');let x=left;for(const col of columns){text(col.label,x+2,y+5.2,7.2,true,[255,255,255]);x+=col.width;}y+=8;}
 if(y+25>bottom)nextPage();text('Itinerary',left,y,11,true);y+=5;tableHeading();
 for(const row of model.rows){
  const date=row.date.replace('T',' ').replace(/\.[0-9]+(?=\s|Z|$)/,'').replace(/\s*TDB$|Z$/,'');
  const cells=[row.name,date.replace(' ','\n'),finite(row.jd)?row.jd.toFixed(6):'Not available',
   row.altitude!==null?`${number(row.altitude,1)}\n${row.altitudeBasis}`:(row.isFlyby?'Not available':'—'),row.details];
  const lines=cells.map((value,i)=>wrap(value,columns[i].width-4,7.4)),height=Math.max(2,...lines.map(a=>a.length))*line+4;
  if(y+height>bottom){nextPage();text('Itinerary · continued',left,y,11,true);y+=5;tableHeading();}
  doc.setFillColor(...(row.burn?[243,248,250]:[255,255,255]));doc.rect(left,y,width,height,'F');
  let x=left;lines.forEach((items,i)=>{text(items,x+2,y+4.8,7.4,i===0);x+=columns[i].width;});
  y+=height;doc.setDrawColor(213,224,231);doc.line(left,y,left+width,y);
 }
 y+=7;for(const note of model.notes)paragraph(note);
 if(model.credit)paragraph('Trajectory credit: '+model.credit);
 if(y+12>bottom)nextPage();paragraph('Model: '+model.model);
 if(model.sourceUrl){const lines=wrap(model.sourceUrl,width,7);for(const item of lines){if(y+line>bottom)nextPage();font(7);doc.setTextColor(...accent);doc.textWithLink(item,left,y,{url:model.sourceUrl});y+=line;}}
 const pages=doc.getNumberOfPages();for(let page=1;page<=pages;page++){doc.setPage(page);doc.setDrawColor(213,224,231);doc.line(left,284,left+width,284);text('RoLaMGAS · Robert Barthell Garay',left,289,7,false,muted);text(`${page} / ${pages}`,left+width-13,289,7,false,muted);}
 const filename=`RoLaMGAS-${model.sequence}-${model.id.slice(0,16)}.pdf`.replace(/[^A-Za-z0-9_.-]/g,'_');
 return {blob:doc.output('blob'),filename,pages,model};
}
