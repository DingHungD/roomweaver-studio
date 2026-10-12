import * as THREE from 'three';
import type {Scene,StudioLight} from './api';
import {lightPosition,lightRotation} from './lightGeometry.ts';
import {eyeVector} from './viewpointGeometry.ts';

// Blender uses Z-up and local -Z for light emission; the viewer uses Y-up.
export function lightDirection(spec:StudioLight){
  const v=new THREE.Vector3(0,0,-1).applyEuler(new THREE.Euler(...spec.rotation,'ZYX'));
  return new THREE.Vector3(v.x,v.z,-v.y).normalize();
}
export function previewSpecs(scene:Scene,selected:string){
  const setup=scene.lighting_setup;
  if(!setup?.enabled)return [];
  return setup.lights.filter(l=>l.enabled&&l.power>0&&l.color.some(c=>c>0)&&!scene.groups.find(g=>g.id===l.group_id)?.deleted&&(setup.mode!=='indoor'||l.kind!=='SUN'))
    .sort((a,b)=>Number(b.id===selected)-Number(a.id===selected)).slice(0,24);
}
export function clearPreview(root:THREE.Group){
  root.traverse(o=>{
    if(o instanceof THREE.Mesh||o instanceof THREE.Line){o.geometry.dispose();(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());}
    if(o instanceof THREE.Light&&'shadow' in o)(o as THREE.SpotLight).shadow?.dispose();
  });root.clear();
}
export type PreviewOptions={soften?:boolean;floorArea?:number};

/** Finite emitter samples: conserve total power while spreading shadow edges. */
export function areaSamples(spec:StudioLight){
  const rotation=new THREE.Euler(...spec.rotation,'ZYX');
  return [[-1,-1],[1,-1],[-1,1],[1,1]].map(([x,y])=>{
    const v=new THREE.Vector3(x*spec.size*.25,y*spec.size*.25,0).applyEuler(rotation);
    return new THREE.Vector3(v.x,v.z,-v.y);
  });
}

export function buildPreview(root:THREE.Group,scene:Scene,selected:string,options:PreviewOptions={}){
  clearPreview(root);
  const specs=previewSpecs(scene,selected);let shadowCount=0,softAreas=0;
  for(const original of specs){
    const spec={...original,rotation:lightRotation(original,scene)};
    const color=new THREE.Color().setRGB(...spec.color),pos=eyeVector(lightPosition(spec,scene));
    const spread=options.soften&&spec.kind==='AREA'&&softAreas<2;
    if(spread)softAreas++;
    const samples=spread?areaSamples(spec):[new THREE.Vector3()];
    for(const offset of samples){
    const direction=lightDirection(spec);let light:THREE.PointLight|THREE.SpotLight|THREE.DirectionalLight;
    // Relative preview scale only: renderer watts are not photometric lumens.
    if(spec.kind==='SUN'){light=new THREE.DirectionalLight(color,spec.power);}
    else if(spec.kind==='POINT'){light=new THREE.PointLight(color,spec.power/(4*Math.PI),0,2);}
    else{const angle=spec.kind==='AREA'?Math.PI*.42:THREE.MathUtils.degToRad(spec.angle/2);light=new THREE.SpotLight(color,spec.power/(2*Math.PI),0,angle,spec.kind==='AREA'?.8:.3,2);}
    light.intensity/=samples.length;light.position.copy(pos).add(offset);light.userData.sourceId=spec.id;root.add(light);
    if(light instanceof THREE.SpotLight||light instanceof THREE.DirectionalLight){light.target.position.copy(light.position).add(direction);root.add(light.target);}
    if(!(light instanceof THREE.PointLight)&&shadowCount<(options.soften?8:4)){light.castShadow=true;shadowCount++;light.shadow.mapSize.set(1024,1024);light.shadow.bias=-.0001;light.shadow.normalBias=.02;light.shadow.camera.near=.05;light.shadow.camera.far=80;
      if(light instanceof THREE.DirectionalLight)Object.assign(light.shadow.camera,{left:-20,right:20,top:20,bottom:-20});}
    }
  }
  // Preview-only diffuse fill, not ray-traced GI. Scale with active light power and floor area.
  // Disabled/black lights cannot create fill; clamping avoids washing out the direct light.
  if(options.soften&&specs.length){
    const floorArea=Math.max(4,options.floorArea||80),color=new THREE.Color(0,0,0);let power=0;
    for(const spec of specs){const weight=spec.kind==='SUN'?spec.power*floorArea:spec.power;power+=weight;color.add(new THREE.Color().setRGB(...spec.color).multiplyScalar(weight));}
    color.multiplyScalar(1/Math.max(power,.001));
    const fill=new THREE.HemisphereLight(color,color.clone().multiplyScalar(.75),Math.min(.8,power/floorArea*.065));
    fill.userData.indirectApproximation=true;root.add(fill);
  }
  // Show editable markers even for disabled lights; markers emit no scene illumination.
  for(const spec of (scene.lighting_setup?.lights||[])){
    if(scene.groups.find(g=>g.id===spec.group_id)?.deleted)continue;
    const pos=eyeVector(lightPosition(spec,scene));
    const marker=new THREE.Mesh(new THREE.SphereGeometry(spec.id===selected ? .11 : .07,10,8),new THREE.MeshBasicMaterial({color:spec.id===selected?'#ffc83e':spec.enabled?'#fff3b1':'#8c938a',wireframe:true}));
    marker.position.copy(pos);marker.userData.lightId=spec.id;root.add(marker);
    if(spec.id===selected)root.add(new THREE.ArrowHelper(lightDirection({...spec,rotation:lightRotation(spec,scene)}),pos,.65,0xffc83e,.15,.08));
  }
  if(scene.lighting_setup?.enabled&&scene.lighting_setup.mode==='day')root.add(new THREE.HemisphereLight(0xccdfff,0x494c40,.25));
}
