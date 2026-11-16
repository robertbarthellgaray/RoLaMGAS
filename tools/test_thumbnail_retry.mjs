import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
const helper=source.slice(source.indexOf('function candidateThumbnail('),source.indexOf('\nfunction message('));
function setup(){
 const timers=[],nodes=[];
 const node=tag=>({tag,isConnected:true,children:[],append(...xs){this.children.push(...xs);},replaceWith(other){this.replacement=other;}});
 const context={Date,setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout:id=>{timers[id-1].cancelled=true;},element:(tag,text,cls)=>{const e=node(tag);Object.assign(e,{text,cls});nodes.push(e);return e;}};
 vm.createContext(context);vm.runInContext(helper,context);return {...context,timers,nodes,node};
}
test('thumbnail retries transient errors with cache-busting and stops on success',()=>{
 const s=setup(),img=s.node('img');s.candidateThumbnail(img,'/files/run/candidates/id.png');
 assert.equal(img.src,'/files/run/candidates/id.png');img.onerror();assert.equal(s.timers[0].ms,500);
 s.timers[0].fn();assert.match(img.src,/\.png\?thumbnail_retry=/);img.onerror();assert.equal(s.timers[1].ms,1000);
 img.onload();assert.equal(s.timers[1].cancelled,true);
});
test('persistent failure shows an explicit retry control instead of broken image',()=>{
 const s=setup(),img=s.node('img');s.candidateThumbnail(img,'/image.png?generation=1');
 img.onerror();s.timers[0].fn();img.onerror();s.timers[1].fn();img.onerror();
 const box=img.replacement;assert.equal(box.cls,'image-placeholder');const button=box.children[1];assert.equal(button.text,'Retry thumbnail');
 let stopped=false;button.onclick({stopPropagation(){stopped=true;}});assert.equal(stopped,true);assert.equal(box.replacement,img);assert.match(img.src,/generation=1&thumbnail_retry=/);
});
test('queued retry does not fetch an image from an abandoned card',()=>{
 const s=setup(),img=s.node('img');s.candidateThumbnail(img,'/old.png');img.onerror();img.isConnected=false;s.timers[0].fn();assert.equal(img.src,'/old.png');
});
