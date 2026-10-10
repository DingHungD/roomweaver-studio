import * as THREE from 'three';

// Imported photometric lights must never be added to the editor's own light rig.
// The lighting editor builds its separate preview from the adopted light settings.
export function hideImportedLights(root:THREE.Object3D){
  root.traverse(o=>{if(o instanceof THREE.Light)o.visible=false;});
}

/** Temporary, unlit base-color view. Textures are borrowed, never modified/disposed. */
export class PlanDisplay {
  private originals=new Map<THREE.Mesh,THREE.Material|THREE.Material[]>();
  private previews:THREE.Material[]=[];
  apply(root:THREE.Object3D,floors:Set<THREE.Mesh>){
    this.restore();
    root.traverse(o=>{
      if(!(o instanceof THREE.Mesh))return;
      this.originals.set(o,o.material);
      const convert=(source:THREE.Material)=>{
        const surface=source as THREE.MeshStandardMaterial;
        const floor=floors.has(o);
        const material=new THREE.MeshBasicMaterial({
          color:floor?'#d4d9cc':surface.color??0xffffff,
          map:floor?null:surface.map??null,
          alphaMap:surface.alphaMap??null,opacity:source.opacity,
          transparent:source.transparent,alphaTest:source.alphaTest,
          side:source.side,depthTest:source.depthTest,depthWrite:source.depthWrite,
          vertexColors:floor?false:source.vertexColors,toneMapped:false,
        });
        this.previews.push(material);return material;
      };
      o.material=Array.isArray(o.material)?o.material.map(convert):convert(o.material);
    });
  }
  restore(){
    this.originals.forEach((material,mesh)=>{mesh.material=material;});
    this.originals.clear();this.previews.forEach(m=>m.dispose());this.previews=[];
  }
}
