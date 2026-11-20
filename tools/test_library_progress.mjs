import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {libraryProgress} from '../docs/library_progress.js';
function setup(){const nodes={label:{},detail:{},bar:{removeAttribute(key){delete this[key]}}},root={dataset:{},setAttribute(k,v){this[k]=v},querySelector(key){return nodes[key==='progress'?'bar':key.includes('label')?'label':'detail']}};return {nodes,root,progress:libraryProgress(root)};}
test('saved files advance only when a real request settles and preserve its result',async()=>{
 const {nodes,root,progress}=setup();progress.start(2);let resolve;const pending=progress.file(new Promise(r=>resolve=r));
 assert.equal(nodes.bar.value,0);resolve('saved data');assert.equal(await pending,'saved data');assert.equal(nodes.bar.value,1);assert.equal(nodes.bar.max,2);
 await assert.rejects(progress.file(Promise.reject(Error('optional metadata unavailable'))));assert.equal(nodes.bar.value,2);assert.equal(root['aria-busy'],'true');
});
test('unknown live totals use an indeterminate bar and count pages honestly',()=>{
 const {nodes,root,progress}=setup();progress.start(11);progress.live({pages:7,count:642});assert.equal(nodes.bar.value,undefined);assert.match(nodes.detail.textContent,/642.*7 pages/);
 progress.complete(8765);assert.equal(nodes.bar.value,1);assert.equal(nodes.bar.max,1);assert.equal(root['aria-busy'],'false');assert.match(nodes.detail.textContent,/8,765/);
});
test('interruption shows retained results, never falsely completes, and can resume',()=>{
 const {nodes,root,progress}=setup();progress.interrupted(4000);assert.equal(root.dataset.state,'paused');assert.equal(nodes.bar.value,0);assert.match(nodes.detail.textContent,/4,000.*retained/);
 progress.live({count:100,pages:1});assert.equal(root.dataset.state,'live');assert.equal(root['aria-busy'],'true');progress.failed();assert.equal(root.dataset.state,'failed');assert.equal(root['aria-busy'],'false');
});
test('loading UI is present before JS, mobile friendly, and wired into live sync and initial files',()=>{
 const read=p=>fs.readFileSync(new URL('../'+p,import.meta.url),'utf8'),html=read('docs/index.html'),js=read('docs/app.js'),css=read('docs/style.css');
 assert.ok(html.indexOf('id="library-loading"')<html.indexOf('<main>'));assert.match(html,/<progress aria-label="Trajectory library loading">/);
 assert.ok(css.includes('@media(max-width:760px){.library-loading'));assert.ok(js.includes('loading.live(progress)'));assert.ok(js.includes('loading.interrupted(catalog.length)'));assert.ok(js.includes('loading.complete(catalog.length)'));
 const initial=js.split('\n').find(line=>line.includes('const [data,archive,settings'));assert.equal((initial.match(/loadSaved\(/g)||[]).length,11);
});
