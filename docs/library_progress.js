// File progress has a known denominator. Live pagination does not.
export function libraryProgress(root,companions=[]){
 const label=root.querySelector('[data-load-label]'),detail=root.querySelector('[data-load-detail]'),bar=root.querySelector('progress');
 let completed=0,total=0;
 const phase=(state,text,note='')=>{const busy=['files','preparing','live'].includes(state);root.hidden=!busy;for(const region of companions)region.hidden=!busy;root.dataset.state=state;root.setAttribute('aria-busy',String(['files','preparing','live'].includes(state)));label.textContent=text;detail.textContent=note;};
 const indeterminate=()=>bar.removeAttribute('value');
 return {
  start(files){completed=0;total=files;bar.max=total;bar.value=0;phase('files','Loading trajectory list…',`0 of ${total} saved files`);},
  async file(task){try{return await task;}finally{completed++;if(root.dataset.state==='files'){bar.value=completed;detail.textContent=`${completed} of ${total} saved files`;}}},
  preparing(text='Preparing saved trajectories…'){indeterminate();phase('preparing',text,'Applying saved routes and mission data…');},
  live(progress={}){indeterminate();phase('live','Loading shared candidates…',progress.pages?`${progress.count.toLocaleString('en-US')} records received · ${progress.pages.toLocaleString('en-US')} pages`:'Checking for new submissions…');},
  complete(count){bar.max=1;bar.value=1;phase('ready','Trajectory library ready',`${count.toLocaleString('en-US')} interactive trajectories · checked ${new Date().toLocaleTimeString()}`);},
  interrupted(count){bar.max=1;bar.value=0;phase('paused','Live update interrupted · retrying automatically',`${count.toLocaleString('en-US')} trajectories available · completed pages retained`);},
  failed(){bar.max=1;bar.value=0;phase('failed','Saved library could not load','Reload this page to retry.');}
 };
}

// An older request must not hide the spinner belonging to a newer selection.
export function selectionLoading(region){
 let latest=0;
 return {start(){region.hidden=false;return ++latest;},finish(token){if(token===latest)region.hidden=true;}};
}
