import * as THREE from 'three';
import {doorLines,doorEndpoints} from './doorGeometry.ts';
import type {DoorPlan} from './doorGeometry.ts';
export function updateDoorPreview(root:THREE.Group,doors:DoorPlan[],assetModel?:THREE.Group){
 root.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.dispose();(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());}});root.clear();
 for(const d of doors){
  let matched=false;
  assetModel?.traverse(o=>{if(o instanceof THREE.Mesh&&o.userData.doorId===d.id){const mesh=new THREE.Mesh(o.geometry.clone(),Array.isArray(o.material)?o.material.map(m=>m.clone()):o.material.clone());mesh.applyMatrix4(o.matrixWorld);mesh.userData={...o.userData};const part=o.userData.doorPart as 'frame'|'leaf-0'|'leaf-1';const override=d.control.materials?.[part];if(override&&!d.control.assets?.[part])for(const m of (Array.isArray(mesh.material)?mesh.material:[mesh.material])){if(m instanceof THREE.MeshStandardMaterial){m.color.set(override.color);m.roughness=override.roughness;m.map=null;m.roughnessMap=null;m.normalMap=null;m.needsUpdate=true;}}root.add(mesh);matched=true;}});
  if(matched)continue;
  const [a,b]=doorEndpoints(d),c=d.control,h=d.height;
  if(d.pose?.preview_parts){
   for(const p of d.pose.preview_parts){
    const part=p.part.startsWith('leaf-')?p.part as 'leaf-0'|'leaf-1':'frame';
    const metal=p.part.startsWith('handle')||p.part==='sliding-guide';
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(p.vertices.flatMap(v=>[v[0],v[2],-v[1]]),3));
    geometry.setIndex([3,2,1,3,1,0,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7]);geometry.computeVertexNormals();
    const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:metal?'#62676a':c.materials?.[part]?.color||'#bca07b',roughness:metal?.23:c.materials?.[part]?.roughness??.6}));
    mesh.userData.doorId=d.id;mesh.userData.doorPart=part;root.add(mesh);
   }
   continue;
  }
  function box(p:[number,number],q:[number,number],height:number,y:number,part:"frame"|"leaf-0"|"leaf-1"="frame"){
   const w=Math.hypot(q[0]-p[0],q[1]-p[1]);
   const mesh=new THREE.Mesh(new THREE.BoxGeometry(Math.max(w,.035),height,c.kind==='folding'?.035:.045),new THREE.MeshStandardMaterial({color:c.materials?.[part]?.color||(c.kind?'#bca07b':'#578b8c'),roughness:c.materials?.[part]?.roughness??.6,transparent:!c.kind,opacity:c.kind?1:.4}));
   mesh.position.set((p[0]+q[0])/2,y,-(p[1]+q[1])/2);mesh.rotation.y=Math.atan2(q[1]-p[1],q[0]-p[0]);mesh.userData.doorId=d.id;mesh.userData.doorPart=part;root.add(mesh);
  }
  box(a,a,h,h/2);box(b,b,h,h/2);box(a,b,.04,h);
  if(!c.kind||c.kind==='frame')continue;
  const lines=doorLines(d);
  if(c.kind==='sliding'){
   const mid:[number,number]=[(a[0]+b[0])/2,(a[1]+b[1])/2];box(a,mid,h-.06,h/2,'leaf-0');box(mid,b,h-.06,h/2,'leaf-1');
  }else if(lines.length>1){box(lines[1][0],lines[1][1],h-.06,h/2,'leaf-0');if(c.kind==='folding')box(lines[2][0],lines[2][1],h-.06,h/2,'leaf-1');if(c.kind==='double')box(lines[3][0],lines[3][1],h-.06,h/2,'leaf-1');}
 }
}
