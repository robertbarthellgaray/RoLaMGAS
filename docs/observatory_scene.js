import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {targetContext,pickPlanet} from './observatory_target.js?v=20261119motion';
// Display only: positions and transfer samples are supplied by the existing app.
const colors={Mercury:0xa8a29c,Venus:0xdac898,Earth:0x71a8df,Mars:0xcb7056,Jupiter:0xd8b790,Saturn:0xd9c59a,Uranus:0x8fcad0,Neptune:0x527dcc};
// Fixed illustrative radii in AU: zooming or moving the camera never resizes planets.
const radiiAU={Mercury:.004,Venus:.006,Earth:.006,Mars:.005,Jupiter:.11,Saturn:.09,Uranus:.07,Neptune:.07};
const v=p=>new THREE.Vector3(p[0],p[2],-p[1]);
function texture(body){
 const c=document.createElement('canvas');c.width=512;c.height=256;const g=c.getContext('2d'),base='#'+colors[body].toString(16).padStart(6,'0');g.fillStyle=base;g.fillRect(0,0,512,256);
 if(body==='Jupiter'||body==='Saturn')for(let i=0;i<45;i++){g.fillStyle=`rgba(${i%2?'106,69,46':'246,228,198'},${.09+.12*Math.sin(i*3)**2})`;g.fillRect(0,i*6,512,3+Math.sin(i)*3);}
 else if(body==='Earth'){
  g.fillStyle='#91b8a0';for(const [x,y]of [[72,70],[118,120],[230,60],[288,110],[350,180]]){g.beginPath();for(let i=0;i<20;i++){const a=i*Math.PI/10,r=18+12*Math.sin(i*13+x);g.lineTo(x+Math.cos(a)*r*1.8,y+Math.sin(a)*r)}g.closePath();g.fill();}
  g.fillStyle='#d5e6e1';g.fillRect(0,0,512,14);g.fillRect(0,244,512,12);
 }
 else{g.fillStyle='#ffffff10';for(let i=0;i<100;i++){g.beginPath();g.ellipse((i*71)%512,(i*109)%256,3+(i%6),2,0,0,Math.PI*2);g.fill();}}
 const map=new THREE.CanvasTexture(c);map.colorSpace=THREE.SRGBColorSpace;return map;
}
function glowTexture(){const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d'),r=g.createRadialGradient(64,64,0,64,64,64);r.addColorStop(0,'#ffe8b1');r.addColorStop(.12,'#ffd980a0');r.addColorStop(.4,'#dba84b20');r.addColorStop(1,'#ffbd3500');g.fillStyle=r;g.fillRect(0,0,128,128);return new THREE.CanvasTexture(c);}
export class ObservatoryScene{
 constructor(stage,onSelect){
  this.stage=stage;this.planetScale=.45;this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#050b14');this.camera=new THREE.PerspectiveCamera(42,1,.003,1500);this.camera.position.set(8,10,14);
  this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true,powerPreference:'low-power'});this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.75));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.1;
  const el=this.renderer.domElement;el.className='observatory-canvas';el.tabIndex=0;el.setAttribute('aria-label','3D solar system: drag to orbit, scroll or pinch to zoom, click a planet to follow it or show routes visiting it. Arrow keys pan the view.');stage.prepend(el);
  this.controls=new OrbitControls(this.camera,el);this.controls.enableDamping=true;this.controls.dampingFactor=.09;this.controls.minDistance=.4;this.controls.maxDistance=200;this.controls.maxPolarAngle=Math.PI*.96;this.controls.listenToKeyEvents(el);
  this.scene.add(new THREE.AmbientLight(0xa1b8d2,.16));const sunLight=new THREE.PointLight(0xffedce,3.5,0,0);this.scene.add(sunLight);
  this.sun=new THREE.Mesh(new THREE.SphereGeometry(1,40,24),new THREE.MeshBasicMaterial({color:0xffdc8e}));this.scene.add(this.sun);this.halo=new THREE.Sprite(new THREE.SpriteMaterial({map:glowTexture(),transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));this.scene.add(this.halo);
  const stars=[];for(let i=0;i<1000;i++){const a=i*2.39996323,z=1-2*(i+.5)/1000,r=Math.sqrt(1-z*z);stars.push(350*r*Math.cos(a),350*z,350*r*Math.sin(a));}const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.Float32BufferAttribute(stars,3));this.scene.add(new THREE.Points(sg,new THREE.PointsMaterial({color:0x8cabc1,size:.4,sizeAttenuation:true,transparent:true,opacity:.45,depthWrite:false})));
  this.meshes={};this.labels={};this.labelLayer=document.createElement('div');this.labelLayer.className='scene-labels';stage.append(this.labelLayer);
  for(const body of Object.keys(colors)){
   const mesh=new THREE.Mesh(new THREE.SphereGeometry(1,40,28),new THREE.MeshStandardMaterial({map:texture(body),roughness:.92,metalness:0}));mesh.userData.body=body;this.meshes[body]=mesh;this.scene.add(mesh);this.label(body);
   if(body==='Saturn'){mesh.geometry.scale(1,.9,1);const ring=new THREE.Mesh(new THREE.RingGeometry(1.35,2.05,64),new THREE.MeshStandardMaterial({color:0xc2b292,side:THREE.DoubleSide,transparent:true,opacity:.6,roughness:1}));ring.rotation.x=-Math.PI/2+.4;mesh.add(ring);}
  }
  this.targetBody=new THREE.Mesh(new THREE.IcosahedronGeometry(1,3),new THREE.MeshStandardMaterial({color:0xbfd5ca,roughness:1}));this.targetBody.visible=false;this.scene.add(this.targetBody);this.label('Target','target-body');
  this.ship=new THREE.Mesh(new THREE.SphereGeometry(1,16,12),new THREE.MeshBasicMaterial({color:0xc8ffe9}));this.scene.add(this.ship);this.label('Spacecraft','spacecraft');this.label('Sun');this.route=new THREE.Group();this.orbits=new THREE.Group();this.encounters=new THREE.Group();this.scene.add(this.route,this.orbits,this.encounters);this.arcs=[];this.onSelect=onSelect;
  const ray=new THREE.Raycaster();let down=null;el.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);el.addEventListener('pointerup',e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const r=el.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),this.camera);const hit=ray.intersectObjects(Object.values(this.meshes).filter(m=>m.visible),false)[0];const points=Object.entries(this.meshes).filter(([,m])=>m.visible).map(([body,m])=>{const p=m.position.clone().project(this.camera);return {body,x:(p.x+1)*r.width/2,y:(1-p.y)*r.height/2,z:p.z,inner:['Mercury','Venus','Earth','Mars'].includes(body)};}).filter(p=>p.z>=-1&&p.z<=1);const body=hit?.object.userData.body||pickPlanet(points,e.clientX-r.left,e.clientY-r.top,e.pointerType==='touch');if(body)this.onSelect(body);});
  this.updateBodySizes();new ResizeObserver(()=>this.resize()).observe(stage);this.resize();this.frame=()=>{if(this.following||this.followedBody){const anchor=this.followedBody?this.meshes[this.followedBody]:this.ship;this.camera.position.add(anchor.position.clone().sub(this.controls.target));this.controls.target.copy(anchor.position);}this.controls.update();this.updateLabels();this.renderer.render(this.scene,this.camera);this.raf=requestAnimationFrame(this.frame);};this.frame();
  document.getElementById('focus-system').onclick=()=>this.fit(34);document.getElementById('focus-mission').onclick=()=>this.setFollowing(!this.following);
  document.getElementById('planet-size').addEventListener('input',e=>{this.planetScale=Number(e.target.value);this.updateBodySizes();});
 }
 updateBodySizes(){this.sun.scale.setScalar(.045);this.halo.scale.setScalar(.27);for(const [body,mesh]of Object.entries(this.meshes)){mesh.scale.setScalar(radiiAU[body]*this.planetScale);}if(this.targetBody)this.targetBody.scale.setScalar((this.targetBody.userData.radiusAU||.004)*this.planetScale);}
 setFollowing(value){const damping=this.controls.enableDamping;this.controls.enableDamping=false;this.controls.update();this.controls.enableDamping=damping;this.followedBody=null;this.following=Boolean(value);this.controls.enablePan=!this.following;if(this.following){this.camera.position.add(this.ship.position.clone().sub(this.controls.target));this.controls.target.copy(this.ship.position);this.controls.update();}document.getElementById('scene-status').textContent=this.following?'Following spacecraft':'';const button=document.getElementById('focus-mission');button.textContent=this.following?'Stop following':'Follow spacecraft';button.setAttribute('aria-pressed',String(this.following));}
 setBodyFollowing(body){if(!this.meshes[body])return;this.setFollowing(false);this.followedBody=body;this.controls.enablePan=false;this.camera.position.add(this.meshes[body].position.clone().sub(this.controls.target));this.controls.target.copy(this.meshes[body].position);this.controls.update();document.getElementById('scene-status').textContent='Following '+body+' · planet centered in the view';}
 label(name,cls=''){const el=document.createElement('span');el.className='scene-label '+cls;el.textContent=name;this.labelLayer.append(el);this.labels[name]=el;}
 resize(){const w=this.stage.clientWidth,h=this.stage.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
 fit(radius){this.setFollowing(false);this.controls.target.set(0,0,0);const vertical=THREE.MathUtils.degToRad(this.camera.fov),horizontal=2*Math.atan(Math.tan(vertical/2)*this.camera.aspect),distance=radius/Math.sin(Math.min(vertical,horizontal)/2);this.camera.position.copy(new THREE.Vector3(.55,.72,1.12).normalize().multiplyScalar(distance));this.camera.near=Math.max(.001,radius/5000);this.camera.far=Math.max(1500,radius*20);this.controls.maxDistance=Math.max(200,radius*8);this.camera.updateProjectionMatrix();this.controls.update();}
 setView(mode){if(!this.missionRadius)return;const following=this.following,d=(this.camera.position.distanceTo(this.controls.target)||this.missionRadius*2),t=this.controls.target;if(mode==='xy')this.camera.position.set(t.x,t.y+d,t.z+.0001);else if(mode==='xz')this.camera.position.set(t.x,t.y,t.z+d);else if(mode==='yz')this.camera.position.set(t.x+d,t.y,t.z);else{this.fit(this.missionRadius);if(following)this.setFollowing(true);}this.controls.update();}
 clear(group){for(const child of [...group.children]){group.remove(child);child.geometry?.dispose();const m=child.material;if(Array.isArray(m))m.forEach(x=>x.dispose());else m?.dispose();}}
 line(points,color,opacity=1){const geometry=new THREE.BufferGeometry().setFromPoints(points.map(v));return new THREE.Line(geometry,new THREE.LineBasicMaterial({color,transparent:opacity<1,opacity,depthWrite:false}));}
 build(mission){
  const following=this.following;this.clear(this.route);this.clear(this.encounters);this.arcs=[];const palette=[0x87d9c0,0xdfbf83,0xa5a0e2,0x7ab8df,0xd5909f,0xa6d4e4];
  for(const [i,p]of mission.paths.entries()){const ghost=this.line(p.points,palette[i%palette.length],.42),trace=this.line(p.points,palette[i%palette.length],1);this.route.add(ghost,trace);this.arcs.push({path:p,trace});}
  for(const event of mission.events){const marker=new THREE.Mesh(new THREE.SphereGeometry(.002,10,8),new THREE.MeshBasicMaterial({color:0xfff1a8,toneMapped:false}));marker.userData.body=event.body;marker.position.copy(v(event.position_au));this.encounters.add(marker);}
  this.missionRadius=Math.max(1,...mission.paths.flatMap(p=>p.points.map(p=>Math.hypot(...p))))*1.12;this.fit(this.missionRadius);if(following)this.setFollowing(true);this.id=mission.id;this.contextId=null;
 }
 update({mission,jd,position,ephemerides,interpolate,visible}){
  if(!mission)return;if(this.id!==mission.id)this.build(mission);this.last={mission,jd,position,visible};
  const contextId=mission.id+(ephemerides?'dated':'');if(this.contextId!==contextId){this.clear(this.orbits);this.targetOrbitId=null;if(ephemerides)for(const body of Object.keys(colors)){
   const t=ephemerides.bodies[body];if(!t)continue;const mid=(mission.start+mission.end)/2,seg=t.segments.find(s=>s.start<=mid&&s.end>=mid);if(!seg)continue;const a=Math.max(seg.start,mid-t.period_days/2),b=Math.min(seg.end,mid+t.period_days/2),pts=Array.from({length:361},(_,i)=>position(body,a+(b-a)*i/360)).filter(Boolean);if(pts.length>1){const line=this.line(pts,colors[body],.16);line.userData.body=body;this.orbits.add(line);}
  }this.contextId=contextId;}
  for(const [body,mesh]of Object.entries(this.meshes)){const p=position(body,jd);mesh.visible=Boolean(p)&&visible(body,'markers');if(p)mesh.position.copy(v(p));}
  const target=targetContext(mission,jd,position);this.targetBody.visible=Boolean(target)&&visible(target.name,'markers');if(target){this.targetBody.position.copy(v(target.point));this.targetBody.userData.body=target.name;this.targetBody.userData.radiusAU=target.radiusAU;this.targetBody.scale.setScalar(target.radiusAU*this.planetScale);this.labels.Target.textContent=target.label;if(target.orbit&&this.targetOrbitId!==mission.id){const orbit=this.line(target.orbit,0xb6d7c8,.35);orbit.userData.body=target.name;this.orbits.add(orbit);this.targetOrbitId=mission.id;}}else this.targetOrbitId=null;
  for(const arc of this.orbits.children)arc.visible=visible(arc.userData.body,'orbits');
  for(const {path,trace}of this.arcs){let n=0;if(jd>=path.end)n=path.points.length;else if(jd>path.start){if(path.times){let lo=0,hi=path.times.length;while(lo<hi){const m=(lo+hi)>>1;if(path.times[m]<=jd)lo=m+1;else hi=m;}n=lo;}else n=1+Math.floor((jd-path.start)/(path.end-path.start)*(path.points.length-1));}trace.geometry.setDrawRange(0,n);}
  const p=mission.paths.find(p=>jd>=p.start&&jd<=p.end)||(jd<mission.start?mission.paths[0]:mission.paths.at(-1));this.ship.position.copy(v(interpolate(p,jd)));for(const marker of this.encounters.children)marker.visible=visible(marker.userData.body,'markers');
 }
 updateLabels(){
  const h=this.stage.clientHeight,w=this.stage.clientWidth,pixel=mesh=>2*this.camera.position.distanceTo(mesh.position)*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))/h;
  this.ship.scale.setScalar(pixel(this.ship)*2.5);
  const objects={Sun:this.sun,...this.meshes,Target:this.targetBody,Spacecraft:this.ship};const priority=['Target','Spacecraft','Sun',...Object.keys(this.meshes).reverse()];
  for(const name of priority){const mesh=objects[name],el=this.labels[name],p=mesh.position.clone().project(this.camera),x=(p.x+1)*w/2,y=(1-p.y)*h/2;let hidden=!mesh.visible||p.z< -1||p.z>1||x<0||x>w-40||y<0||y>h;const labelY=y+(name==='Spacecraft'?14:-10);el.hidden=hidden;if(!hidden){el.style.left=x+'px';el.style.top=labelY+'px';}}
 }
}
