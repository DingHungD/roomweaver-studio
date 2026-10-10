import * as THREE from 'three';
import type {AssemblyRuntime} from './assemblyScene';
import type {Scene} from './api';

/** Closed horizontal sections only; open/non-manifold contours are left unfilled. */
export function sectionGeometry(mesh:THREE.Mesh,height:number){
  const position=mesh.geometry.getAttribute('position'),index=mesh.geometry.index;
  if(!position)return null;
  const points:THREE.Vector2[]=[],ids=new Map<string,number>(),edges=new Set<string>();
  const id=(p:THREE.Vector3)=>{
    const key=`${Math.round(p.x*1e5)},${Math.round(p.z*1e5)}`;
    if(!ids.has(key)){ids.set(key,points.length);points.push(new THREE.Vector2(p.x,-p.z));}
    return ids.get(key)!;
  };
  for(let i=0;i<(index?.count??position.count);i+=3){
    const vertices=[0,1,2].map(j=>new THREE.Vector3().fromBufferAttribute(position,index?index.getX(i+j):i+j).applyMatrix4(mesh.matrixWorld));
    if(vertices.every(v=>Math.abs(v.y-height)<1e-7))continue;
    const hits:THREE.Vector3[]=[];
    for(let j=0;j<3;j++){
      const a=vertices[j],b=vertices[(j+1)%3],da=a.y-height,db=b.y-height;
      if(Math.abs(da)<1e-7)hits.push(a);
      if(da*db<0)hits.push(a.clone().lerp(b,da/(da-db)));
    }
    const unique=[...new Set(hits.map(id))];
    if(unique.length===2){unique.sort((a,b)=>a-b);edges.add(unique.join(','));}
  }
  const neighbors=new Map<number,number[]>();
  for(const edge of edges){const [a,b]=edge.split(',').map(Number);neighbors.set(a,[...(neighbors.get(a)||[]),b]);neighbors.set(b,[...(neighbors.get(b)||[]),a]);}
  const used=new Set<number>(),loops:THREE.Vector2[][]=[];
  for(const start of neighbors.keys()){
    if(used.has(start))continue;
    const loop:number[]=[];let current=start,previous=-1,closed=false;
    while(!used.has(current)){
      used.add(current);loop.push(current);const next=neighbors.get(current)!;
      if(next.length!==2)break;
      const target=next.find(n=>n!==previous)!;previous=current;current=target;
      if(current===start){closed=true;break;}
    }
    if(closed&&loop.length>=3)loops.push(loop.map(i=>points[i]));
  }
  const inside=(p:THREE.Vector2,polygon:THREE.Vector2[])=>{
    let result=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
      const a=polygon[i],b=polygon[j];if((a.y>p.y)!==(b.y>p.y)&&p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x)result=!result;
    }return result;
  };
  const depth=loops.map(loop=>loops.filter(other=>other!==loop&&inside(loop[0],other)).length);
  const vertices:number[]=[];
  loops.forEach((contour,i)=>{
    if(depth[i]%2)return;
    const holes=loops.filter((loop,j)=>depth[j]===depth[i]+1&&inside(loop[0],contour));
    const flat=[...contour,...holes.flat()];
    for(const face of THREE.ShapeUtils.triangulateShape(contour,holes))for(const j of face){const p=flat[j];vertices.push(p.x,height-.001,-p.y);}
  });
  if(!vertices.length)return null;
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.computeVertexNormals();return geometry;
}

export class PlanCaps {
  root=new THREE.Group();
  private cache=new Map<THREE.Mesh,{key:string;cap:THREE.Mesh}>();
  update(assembly:AssemblyRuntime,scene:Scene,planes:THREE.Plane[],height=1.3){
    this.root.visible=true;this.cache.forEach(({cap})=>{cap.visible=false;});
    assembly.root.updateMatrixWorld(true);
    for(const spec of scene.groups){
      if(!/^wall(?:$|[-_\s])|divider|牆/i.test(spec.name))continue;
      const group=assembly.groups.get(spec.id);if(!group?.visible)continue;
      group.traverse(o=>{
        if(!(o instanceof THREE.Mesh))return;
        const key=o.matrixWorld.elements.join(',')+':'+height;let entry=this.cache.get(o);
        if(entry&&entry.key!==key){entry.cap.geometry.dispose();(entry.cap.material as THREE.Material).dispose();this.root.remove(entry.cap);this.cache.delete(o);entry=undefined;}
        if(!entry){
          const geometry=sectionGeometry(o,height);if(!geometry)return;
          const material=new THREE.MeshStandardMaterial({color:'#d5d2ca',roughness:.85,side:THREE.DoubleSide});
          const cap=new THREE.Mesh(geometry,material);cap.castShadow=true;cap.receiveShadow=true;cap.userData.planSource=o;
          entry={key,cap};this.cache.set(o,entry);this.root.add(cap);
        }
        entry.cap.visible=true;const material=entry.cap.material as THREE.Material;material.clippingPlanes=planes;material.clipShadows=true;
      });
    }
  }
  dispose(){this.cache.forEach(({cap})=>{cap.geometry.dispose();(cap.material as THREE.Material).dispose();});this.cache.clear();this.root.clear();}
}
