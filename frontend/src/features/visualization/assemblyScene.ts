import * as THREE from 'three';
import type {Scene} from './api';
export type AssemblyRuntime={root:THREE.Object3D;groups:Map<string,THREE.Group>;parts:Map<string,THREE.Object3D>;bases:Map<string,THREE.Vector3>;materials:THREE.Material[]};
const appliedTransforms=new WeakMap<THREE.Object3D,string>();
const appliedMaterials=new WeakMap<THREE.Object3D,string>();
export function assemble(root:THREE.Object3D,design:Scene):AssemblyRuntime {
  root.updateMatrixWorld(true);
  const groups=new Map<string,THREE.Group>(),parts=new Map<string,THREE.Object3D>(),bases=new Map<string,THREE.Vector3>();
  root.traverse(o=>{if(o.userData.studio_id)parts.set(o.userData.studio_id,o);});
  for(const spec of design.groups||[]){
    const group=new THREE.Group();group.userData.group_id=spec.id;root.add(group);
    const bounds=new THREE.Box3();spec.children.forEach(id=>{const part=parts.get(id);if(part)bounds.expandByObject(part);});
    const center=bounds.isEmpty()?new THREE.Vector3():bounds.getCenter(new THREE.Vector3());
    group.position.copy(root.worldToLocal(center.clone()));group.updateMatrixWorld(true);
    spec.children.forEach(id=>{const part=parts.get(id);if(part){
      // Object3D.attach decomposes to TRS, losing a source's affine shear.
      // Keep the exact relative matrix for these static imported parts.
      part.updateWorldMatrix(true,false);const world=part.matrixWorld.clone();group.attach(part);
      part.matrix.copy(group.matrixWorld.clone().invert().multiply(world));part.matrixAutoUpdate=false;
      part.updateMatrixWorld(true);
    }});
    groups.set(spec.id,group);bases.set(spec.id,group.position.clone());
  }
  return {root,groups,parts,bases,materials:[]};
}
export function applyDesign(runtime:AssemblyRuntime,design:Scene){
  syncConcepts(runtime,design);
  for(const group of design.groups||[]){const node=runtime.groups.get(group.id);if(!node)continue;
    const key=JSON.stringify([group.translation,group.rotation,group.rotation_pivot,group.deleted]);
    if(appliedTransforms.get(node)===key)continue;
    const delta=new THREE.Vector3(group.translation[0],group.translation[2],-group.translation[1]);
    const pivot=new THREE.Vector3(...[group.rotation_pivot?.[0]||0,group.rotation_pivot?.[2]||0,-(group.rotation_pivot?.[1]||0)]);
    const angle=THREE.MathUtils.degToRad(group.rotation||0);
    node.position.copy(runtime.bases.get(group.id)!).sub(pivot).applyAxisAngle(new THREE.Vector3(0,1,0),angle).add(pivot).add(delta);
    node.rotation.set(0,angle,0);node.visible=!group.deleted;
    node.updateMatrixWorld(true);appliedTransforms.set(node,key);
  }
  for(const spec of design.objects){const part=runtime.parts.get(spec.id);if(!part)continue;
    const requested=spec.material.color||spec.material.render_roughness!=null?`${spec.material.color}:${spec.material.render_roughness??spec.material.roughness}`:'';
    if(appliedMaterials.get(part)===requested)continue;
    part.traverse(o=>{if(!(o instanceof THREE.Mesh))return;
      o.userData.originalMaterial??=o.material;
      const key=spec.material.color||spec.material.render_roughness!=null?`${spec.material.color}:${spec.material.render_roughness??spec.material.roughness}`:'';
      if(o.userData.materialKey===key)return;
      if(key){
        if(!o.userData.studioMaterial){
          const clone=(source:THREE.Material)=>{const surface=source as THREE.MeshStandardMaterial;const m=surface.isMeshStandardMaterial?surface.clone():new THREE.MeshStandardMaterial({map:(source as THREE.MeshBasicMaterial).map||null});runtime.materials.push(m);return m;};
          o.userData.studioMaterial=Array.isArray(o.userData.originalMaterial)?o.userData.originalMaterial.map(clone):clone(o.userData.originalMaterial);
        }
        o.material=o.userData.studioMaterial;
        const originals=Array.isArray(o.userData.originalMaterial)?o.userData.originalMaterial:[o.userData.originalMaterial];
        (Array.isArray(o.material)?o.material:[o.material]).forEach((m,i)=>{const surface=m as THREE.MeshStandardMaterial;if(spec.material.color)surface.color.set(spec.material.color);else if(originals[i].color)surface.color.copy(originals[i].color);surface.roughness=spec.material.render_roughness??spec.material.roughness;});
      }else o.material=o.userData.originalMaterial;
      o.userData.materialKey=key;
    });
    appliedMaterials.set(part,requested);
  }
  runtime.root.updateMatrixWorld();
}
function syncConcepts(runtime:AssemblyRuntime,design:Scene){
  const wanted=new Set((design.concept_furniture||[]).map(f=>f.id));
  for(const [id,node] of runtime.groups){if(!node.userData.concept||wanted.has(id))continue;
    node.traverse(o=>{if(o instanceof THREE.Mesh){runtime.parts.delete(o.userData.studio_id);o.geometry.dispose();const m=o.userData.originalMaterial||o.material;if(m instanceof THREE.Material)m.dispose();}});
    node.removeFromParent();runtime.groups.delete(id);runtime.bases.delete(id);
  }
  for(const f of design.concept_furniture||[]){
    let group=runtime.groups.get(f.id);
    const key=JSON.stringify(f.parts);
    if(group?.userData.concept===key)continue;
    if(group){group.traverse(o=>{if(o instanceof THREE.Mesh){runtime.parts.delete(o.userData.studio_id);o.geometry.dispose();const m=o.userData.originalMaterial||o.material;if(m instanceof THREE.Material)m.dispose();}});group.removeFromParent();}
    group=new THREE.Group();group.userData={group_id:f.id,concept:key};runtime.root.add(group);
    runtime.groups.set(f.id,group);runtime.bases.set(f.id,new THREE.Vector3());
    for(const p of f.parts){const mesh=new THREE.Mesh(new THREE.BoxGeometry(p.size[0],p.size[2],p.size[1]),new THREE.MeshStandardMaterial({color:new THREE.Color().setRGB(.55,.42,.29),roughness:.7}));
      mesh.position.set(p.center[0],p.center[2],-p.center[1]);mesh.name=p.name;mesh.userData={studio_id:p.id,role:'furniture'};mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);runtime.parts.set(p.id,mesh);
    }
  }
}
export function visible(object:THREE.Object3D):boolean {let o:THREE.Object3D|null=object;while(o){if(!o.visible)return false;o=o.parent;}return true;}
