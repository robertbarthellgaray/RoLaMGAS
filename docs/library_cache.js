// Cache public science records only. A changed bundled snapshot starts a new cache.
export async function openLibraryCache(baseline){
 if(!globalThis.indexedDB)return null;
 try{
  const db=await new Promise((resolve,reject)=>{const q=indexedDB.open('rolamgas-live-library-'+baseline,1);q.onupgradeneeded=()=>{q.result.createObjectStore('records',{keyPath:'id'});q.result.createObjectStore('meta');};q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);q.onblocked=()=>reject(Error('Cache blocked'));});
  const read=(store,key)=>new Promise((resolve,reject)=>{const tx=db.transaction(store),q=key===undefined?tx.objectStore(store).getAll():tx.objectStore(store).get(key);q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);});
  return {
   load:async()=>({records:await read('records'),checkpoint:await read('meta','checkpoint'),watermark:await read('meta','watermark')}),
   save:async(records,checkpoint,watermark)=>new Promise((resolve,reject)=>{const tx=db.transaction(['records','meta'],'readwrite');for(const r of records)tx.objectStore('records').put(r);if(checkpoint)tx.objectStore('meta').put(checkpoint,'checkpoint');if(watermark){tx.objectStore('meta').put(watermark,'watermark');tx.objectStore('meta').delete('checkpoint');}tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);})
  };
 }catch{return null;}
}
