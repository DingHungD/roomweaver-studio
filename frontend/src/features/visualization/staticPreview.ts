import * as THREE from 'three';

type Entry={source:THREE.Mesh;group:THREE.Object3D;proxy?:THREE.Mesh;batch?:THREE.InstancedMesh;slot:number;reflected:boolean};
const hiddenMatrix=new THREE.Matrix4().makeScale(0,0,0);
const affineNormal=`mat3 im = mat3( instanceMatrix );
 transformedNormal = mat3(cross(im[1],im[2]),cross(im[2],im[0]),cross(im[0],im[1])) * transformedNormal;`;
export const affineNormalShader=THREE.ShaderChunk.defaultnormal_vertex.replace(
 /mat3 im = mat3\( instanceMatrix \);[\s\S]*?transformedNormal = im \* transformedNormal;/,affineNormal);

/** Display-only batching. Source meshes remain authoritative for selection and editing. */
export class StaticPreview {
 readonly root=new THREE.Group();
 readonly enabled:boolean;
 private entries:Entry[]=[];
 private byGroup=new Map<THREE.Object3D,Entry[]>();
 private batches:THREE.InstancedMesh[]=[];
 private materials:THREE.Material[][]=[];
 private modes=new Map<THREE.Material,string>();
 private meshes:THREE.Mesh[]=[];
 private mirrored=new Map<THREE.BufferGeometry,THREE.BufferGeometry>();
 private wrappers=new Map<THREE.Material,{material:THREE.Material;version:number}>();
 private source:THREE.Object3D;
 private topology='';
 private boundsCache=new Map<THREE.Object3D,{matrix:number[];box:THREE.Box3}>();
 constructor(source:THREE.Object3D,threshold=2000){
  this.source=source;
  let unsupported=false;
  source.traverse(o=>{if(o instanceof THREE.Mesh){this.meshes.push(o);if((o as THREE.SkinnedMesh).isSkinnedMesh||(o as THREE.InstancedMesh).isInstancedMesh||o.morphTargetInfluences?.length)unsupported=true;}else if((o as THREE.Line).isLine||(o as THREE.Points).isPoints)unsupported=true;});
  this.enabled=!unsupported&&this.meshes.length>=threshold;
  if(this.enabled)this.rebuild();
 }
 private batchable(mesh:THREE.Mesh){
  if(Array.isArray(mesh.material)||mesh.material.transparent||(mesh.material as THREE.MeshPhysicalMaterial).transmission>0)return false;
  return Math.abs(mesh.matrixWorld.determinant())>1e-12;
 }
 private mirroredGeometry(source:THREE.BufferGeometry){
  let geometry=this.mirrored.get(source);if(geometry)return geometry;
  geometry=source.clone();geometry.scale(-1,1,1);
  if(!geometry.index)geometry.setIndex(Array.from({length:geometry.getAttribute('position').count},(_,i)=>i));
  const indices=geometry.index!;for(let i=0;i<indices.count;i+=3){const b=indices.getX(i+1);indices.setX(i+1,indices.getX(i+2));indices.setX(i+2,b);}
  const tangent=geometry.getAttribute('tangent');if(tangent)for(let i=0;i<tangent.count;i++)tangent.setW(i,-tangent.getW(i));
  this.mirrored.set(source,geometry);return geometry;
 }
 private displayMaterial(source:THREE.Material){
  let entry=this.wrappers.get(source);
  if(!entry){entry={material:source.clone(),version:source.version};this.wrappers.set(source,entry);}
  entry.material.copy(source);
  if(entry.version!==source.version){entry.material.needsUpdate=true;entry.version=source.version;}
  entry.material.onBeforeCompile=(shader,renderer)=>{source.onBeforeCompile.call(entry!.material,shader,renderer);shader.vertexShader=shader.vertexShader.replace('#include <defaultnormal_vertex>',affineNormalShader);};
  entry.material.customProgramCacheKey=()=>source.customProgramCacheKey()+':roomweaver-affine-instances-v1';
  return entry.material;
 }
 private clear(){
  this.batches.forEach(b=>b.dispose());this.batches=[];
  // Object3D.clear spreads every child as a function argument and overflows on
  // very large imports. Detach this private display tree in linear time.
  const children=this.root.children;this.root.children=[];
  for(const child of children){child.parent=null;child.dispatchEvent({type:'removed'});this.root.dispatchEvent({type:'childremoved',child});}
  this.entries=[];this.byGroup.clear();this.boundsCache.clear();this.materials=[];this.modes.clear();
 }
 private rebuild(){
  this.clear();this.meshes=[];
  this.source.traverse(o=>{if(o instanceof THREE.Mesh)this.meshes.push(o);});
  this.topology=this.source.children.map(o=>o.uuid+':'+(o.userData.concept||'')).join('|');
  this.source.updateMatrixWorld(true);
  const buckets=new Map<string,Entry[]>();
  for(const source of this.meshes){
   let group:THREE.Object3D=source;while(group.parent&&!group.userData.group_id)group=group.parent;
   const entry:Entry={source,group,slot:-1,reflected:source.matrixWorld.determinant()<0};this.entries.push(entry);
   const members=this.byGroup.get(group)||[];members.push(entry);this.byGroup.set(group,members);
   const surfaces=Array.isArray(source.material)?source.material:[source.material];this.materials.push(surfaces);
   for(const material of surfaces)if(!this.modes.has(material))this.modes.set(material,this.materialMode(material));
   if(this.batchable(source)){
    const key=[source.geometry.uuid,entry.reflected,(source.material as THREE.Material).uuid,source.castShadow,source.receiveShadow,source.renderOrder,source.layers.mask].join(':');
    const bucket=buckets.get(key)||[];bucket.push(entry);buckets.set(key,bucket);
   }
  }
  const usedMaterials=new Set<THREE.Material>();
  for(const members of buckets.values())if(members.length>=2){
   const first=members[0].source,geometry=members[0].reflected?this.mirroredGeometry(first.geometry):first.geometry;
   usedMaterials.add(first.material as THREE.Material);
   const batch=new THREE.InstancedMesh(geometry,this.displayMaterial(first.material as THREE.Material),members.length);
   batch.name='Preview instances';batch.castShadow=first.castShadow;batch.receiveShadow=first.receiveShadow;batch.renderOrder=first.renderOrder;batch.layers.mask=first.layers.mask;
   batch.instanceMatrix.setUsage(THREE.DynamicDrawUsage);this.batches.push(batch);this.root.add(batch);
   members.forEach(e=>e.batch=batch);
  }
  for(const [source,entry] of this.wrappers)if(!usedMaterials.has(source)){entry.material.dispose();this.wrappers.delete(source);}
  for(const entry of this.entries)if(!entry.batch){
   const original=entry.source,proxy=new THREE.Mesh(original.geometry,original.material);
   proxy.name=original.name;proxy.castShadow=original.castShadow;proxy.receiveShadow=original.receiveShadow;
   proxy.layers.mask=original.layers.mask;proxy.renderOrder=original.renderOrder;proxy.frustumCulled=original.frustumCulled;
   proxy.customDepthMaterial=original.customDepthMaterial;proxy.customDistanceMaterial=original.customDistanceMaterial;
   proxy.matrixAutoUpdate=false;proxy.matrixWorldAutoUpdate=true;
   proxy.userData={planSource:entry.source};entry.proxy=proxy;this.root.add(proxy);
  }
 }
 /** Full sync after visibility/material changes; moving one group updates only that group. */
 sync(group?:THREE.Object3D){
  if(!this.enabled)return;
  if(!group&&this.topology!==this.source.children.map(o=>o.uuid+':'+(o.userData.concept||'')).join('|'))this.rebuild();
  const selected=group?this.byGroup.get(group):undefined;
  if(group&&!selected)return;
  if(group)group.updateWorldMatrix(true,true);else this.source.updateMatrixWorld(true);
  if(!group&&([...this.modes].some(([m,mode])=>mode!==this.materialMode(m))||this.entries.some((e,i)=>{
   const next=Array.isArray(e.source.material)?e.source.material:[e.source.material],old=this.materials[i];
   return next.length!==old.length||next.some((m,j)=>m!==old[j]);
  })))this.rebuild();
  if(!group)for(const source of this.wrappers.keys())this.displayMaterial(source);
  const visibility=new Map<THREE.Object3D,boolean>();
  const isVisible=(o:THREE.Object3D):boolean=>{
   const cached=visibility.get(o);if(cached!==undefined)return cached;
   const value=o.visible&&(!o.parent||isVisible(o.parent));visibility.set(o,value);return value;
  };
  const touched=new Set<THREE.InstancedMesh>();
  if(!group)this.batches.forEach(b=>b.count=0);
  const matrix=new THREE.Matrix4();
  for(const entry of selected||this.entries){
   const visible=isVisible(entry.source),batch=entry.batch;
   if(batch){
    if(!group)entry.slot=visible?batch.count++:-1;
    if(entry.slot>=0){matrix.copy(visible?entry.source.matrixWorld:hiddenMatrix);if(entry.reflected)for(let i=0;i<4;i++)matrix.elements[i]*=-1;batch.setMatrixAt(entry.slot,matrix);touched.add(batch);}
   }else if(entry.proxy){entry.proxy.visible=visible;entry.proxy.matrix.copy(entry.source.matrixWorld);entry.proxy.matrixWorldNeedsUpdate=true;}
  }
  touched.forEach(batch=>{batch.instanceMatrix.needsUpdate=true;batch.computeBoundingSphere();});
  if(!group)this.batches.forEach(batch=>batch.visible=batch.count>0);
 }
 statistics(){return {enabled:this.enabled,sourceMeshes:this.meshes.length,renderMeshes:this.enabled?this.root.children.length:this.meshes.length,instancedMeshes:this.entries.filter(e=>e.batch).length,batches:this.batches.length};}
 private materialMode(material:THREE.Material){return `${material.transparent}:${(material as THREE.MeshPhysicalMaterial).transmission>0}`;}
 private groupBounds(group:THREE.Object3D){
  group.updateWorldMatrix(true,false);const matrix=group.matrixWorld.elements,cached=this.boundsCache.get(group);
  if(cached&&cached.matrix.every((v,i)=>v===matrix[i]))return cached.box;
  const box=new THREE.Box3().setFromObject(group);this.boundsCache.set(group,{matrix:[...matrix],box});return box;
 }
 bounds(){const result=new THREE.Box3();for(const group of this.byGroup.keys())if(this.visible(group))result.union(this.groupBounds(group));return result;}
 private visible(node:THREE.Object3D):boolean{return node.visible&&(!node.parent||this.visible(node.parent));}
 /** Broad phase tests source assembly bounds before exact source-triangle picking. */
 intersections(ray:THREE.Raycaster){
  const candidates:THREE.Mesh[]=[];
  for(const [group,entries] of this.byGroup)if(this.visible(group)&&ray.ray.intersectsBox(this.groupBounds(group)))
   for(const entry of entries)if(this.visible(entry.source))candidates.push(entry.source);
  return ray.intersectObjects(candidates,false);
 }
 dispose(){this.clear();this.mirrored.forEach(g=>g.dispose());this.mirrored.clear();this.wrappers.forEach(w=>w.material.dispose());this.wrappers.clear();this.meshes=[];}
}
