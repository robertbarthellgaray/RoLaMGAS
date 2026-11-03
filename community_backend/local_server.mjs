// Loopback-only development adapter; production uses the D1 binding in worker.mjs.
import {DatabaseSync} from 'node:sqlite';
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import worker from './worker.mjs';
export function localEnv(path=':memory:',limit='5000'){
 const db=new DatabaseSync(path);db.exec(readFileSync(new URL('./schema.sql',import.meta.url),'utf8'));
 return {MAX_DAILY_CANDIDATES:limit,ALLOWED_ORIGINS:'https://robertbarthellgaray.github.io',database:db,
 DB:{prepare(sql){return {bind(...values){const ordered=[...sql.matchAll(/\?(\d+)/g)].map(m=>values[Number(m[1])-1]);const stmt=db.prepare(sql.replace(/\?\d+/g,'?'));values=ordered;return {async first(){return stmt.get(...values)||null},async all(){return {results:stmt.all(...values)}},async run(){return stmt.run(...values)}}}}}}};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 const port=Number(process.env.PORT||31311),env=localEnv(process.env.DATABASE||':memory:');
 const server=createServer(async(req,res)=>{
  try{const chunks=[];let total=0;for await(const chunk of req){total+=chunk.length;if(total>256001){res.writeHead(413);res.end();return}chunks.push(chunk)}
   const request=new Request('http://127.0.0.1:'+port+req.url,{method:req.method,headers:req.headers,...(['POST','PUT'].includes(req.method)?{body:Buffer.concat(chunks)}:{})});
   const response=await worker.fetch(request,env);res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
  }catch{res.writeHead(500);res.end('{}')}
 });
 server.listen(port,'127.0.0.1',()=>console.log('Local community API: http://127.0.0.1:'+port));
}
