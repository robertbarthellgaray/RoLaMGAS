import test from 'node:test';import assert from 'node:assert/strict';import {sharedExportDownloads,exportRecordId} from '../docs/export_downloads.js';
test('integrated downloads use the science record, never a local candidate ID or untrusted link',async()=>{
 const original=globalThis.fetch,c={id:'short',desktop_record:{id:'a'.repeat(64)}};assert.equal(exportRecordId(c),'a'.repeat(64));
 try{globalThis.fetch=async()=>Response.json({storage_ready:true,exports:[{candidate_id:'a'.repeat(64),export_id:'b'.repeat(64),added_at:'2026-11-19T00:00:00Z',url:'https://untrusted.test'},{candidate_id:'a',export_id:'../bad'}]});const rows=await sharedExportDownloads(c,'https://example.test');assert.equal(rows.length,1);assert.equal(rows[0].url,'https://example.test/v1/exports/'+'a'.repeat(64)+'/'+'b'.repeat(64));
 globalThis.fetch=async()=>Response.json({storage_ready:false,exports:[]});assert.deepEqual(await sharedExportDownloads(c,'https://example.test'),[]);assert.deepEqual(await sharedExportDownloads({id:'local'},'https://example.test'),[]);
 }finally{globalThis.fetch=original}
});
