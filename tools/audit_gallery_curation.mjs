/** Reproduce the browser cleanup from the saved archive and optional live snapshot.
 * node tools/audit_gallery_curation.mjs [--snapshot live.json] [--output audit.json]
 * Original science records are never modified or deleted.
 */
import fs from 'node:fs';
import {summaryFor,registerBodyNames} from '../docs/community.js';
import {encounterDayKey,betterDuplicate} from '../docs/library_analysis.js';
import {trimAlternatives,groupLaunches,CURATION_RULE} from '../docs/library_curation.js';
import {historicalMatch} from '../docs/historical_labels.js';
const load=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url),'utf8'));
registerBodyNames(load('docs/data/body_names.json'));
const archive=load('docs/data/community_seed_catalog.json'),annotations=load('docs/data/mission_annotations.json').missions,profiles=load('docs/data/historical_labels.json').missions;
const catalog=load('docs/data/index.json').cases,byId=new Map(catalog.map(c=>[c.id,c])),days=new Map();
const args=process.argv.slice(2),option=key=>{const i=args.indexOf(key);if(i<0)return null;if(!args[i+1]||args[i+1].startsWith('--'))throw Error('Missing value for '+key);return args[i+1];};
const snapshot=option('--snapshot'),extra=snapshot?JSON.parse(fs.readFileSync(snapshot,'utf8')):[];
const seen=new Set();
for(const record of [...archive.candidates,...extra]){
 if(seen.has(record.id))continue;seen.add(record.id);
 let summary;try{summary=summaryFor(record);summary.historical_match=historicalMatch(record,profiles)}catch{continue}
 const alias=archive.curated_aliases?.[record.id],key=encounterDayKey(record),previous=days.get(key);
 if(alias&&byId.has(alias)){days.set(key,{record,id:alias,curated:true});continue;}
 if(previous){if(previous.curated||!betterDuplicate(record,previous.record))continue;byId.delete(previous.id);}
 byId.set(record.id,summary);days.set(key,{record,id:record.id});
}
const rows=[...byId.values()],protectedIds=new Set(rows.filter(c=>annotations[c.id]||c.historical_match||c.spotlight||/^(?:Rebuilding|Low-energy|Tianwen|Claudius)/.test(c.title)).map(c=>c.id));
const curated=trimAlternatives(rows,protectedIds),families={};
for(const c of rows){const key=c.target+' / '+c.sequence;families[key]??={target:c.target,sequence:c.sequence,total:0,trimmed:0,retained:0,launch_month_groups:0};families[key].total++;families[key][curated.hidden.has(c.id)?'trimmed':'retained']++;}
for(const group of groupLaunches(curated.rows))families[group.target+' / '+group.sequence].launch_month_groups++;
const report={generated_at:new Date().toISOString(),rule:CURATION_RULE,note:'Reversible default-gallery cleanup only. Same target, ordered sequence, launch within three years; no worse C3, flight time, arrival V-infinity or cruise burns, with at least 20% and 2 km2/s2 C3 or 1 year flight-time improvement. Named/featured missions retained. Filters are applied BEFORE curation in the browser, so restricting launch years can restore an otherwise hidden opportunity. Full archive and direct links remain intact.',total:rows.length,retained:curated.rows.length,trimmed:curated.hidden.size,launch_month_groups:groupLaunches(curated.rows).length,families:Object.values(families).sort((a,b)=>b.trimmed-a.trimmed),trimmed_alternatives:Object.fromEntries(curated.hidden)};
const output=option('--output');if(output)fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,trimmed_alternatives:undefined,families:report.families.slice(0,18)},null,2));
