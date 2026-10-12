import * as THREE from 'three';

/** Ignore hidden rooms/parts and editor outlines before expensive triangle tests. */
export function pickMeshes(...roots:THREE.Object3D[]){
 const meshes:THREE.Mesh[]=[];
 for(const root of roots)root.traverseVisible(o=>{if(o instanceof THREE.Mesh){if(!o.geometry.boundingBox)o.geometry.computeBoundingBox();meshes.push(o);}});
 return meshes;
}

/** Yield between texture uploads so a large import does not freeze the whole editor. */
export async function prepareTextures(root:THREE.Object3D,upload:(texture:THREE.Texture)=>void,
 options:{cancelled:()=>boolean;progress:(done:number,total:number)=>void;yieldUI?:()=>Promise<void>}){
 const textures=new Set<THREE.Texture>();
 root.traverse(o=>{if(o instanceof THREE.Mesh){for(const m of Array.isArray(o.material)?o.material:[o.material])for(const value of Object.values(m))if(value instanceof THREE.Texture)textures.add(value);}});
 const yieldUI=options.yieldUI||(()=>new Promise<void>(resolve=>setTimeout(resolve,0)));
 let done=0,start=performance.now();options.progress(0,textures.size);await yieldUI();
 for(const texture of textures){
  if(options.cancelled())return false;upload(texture);done++;
  if(performance.now()-start>=8||done===textures.size){options.progress(done,textures.size);await yieldUI();start=performance.now();}
 }
 return !options.cancelled();
}

/** Optional high-contrast aid: bound CPU work for detailed imported furniture. */
export function outlineGeometry(source:THREE.BufferGeometry){
 const count=source.index?.count??source.getAttribute('position')?.count??0;
 if(count<=9000)return new THREE.EdgesGeometry(source,35);
 source.computeBoundingBox();const bounds=source.boundingBox!;
 const box=new THREE.BoxGeometry(...bounds.getSize(new THREE.Vector3()).toArray());
 box.translate(...bounds.getCenter(new THREE.Vector3()).toArray());
 const edges=new THREE.EdgesGeometry(box);box.dispose();return edges;
}
