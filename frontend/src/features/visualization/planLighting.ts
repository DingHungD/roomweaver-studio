import * as THREE from 'three';

/** Neutral, bounded editor light rig; independent of model units and exported watts. */
export function createPlanLighting(){
  const root=new THREE.Group();
  root.add(new THREE.HemisphereLight(0xffffff,0xd1cec7,1.65));
  // Four directions approximate a broad overhead source while conserving total intensity.
  const samples=[[-.55,-.55],[-.55,.55],[.55,-.55],[.55,.55]];
  const lights=samples.map(()=>{
    const light=new THREE.DirectionalLight(0xfff5e5,.65);
    light.castShadow=true;light.shadow.mapSize.set(1024,1024);
    light.shadow.bias=-.00015;light.shadow.normalBias=.012;light.shadow.radius=3;
    root.add(light,light.target);return light;
  });
  return {root,fit(bounds:THREE.Box3){
    const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
    const span=Math.max(size.x,size.z,2),height=Math.max(8,span*1.3);
    lights.forEach((light,i)=>{
      light.position.copy(center).add(new THREE.Vector3(-span*.25+samples[i][0],height,span*.3+samples[i][1]));
      light.target.position.set(center.x,bounds.min.y,center.z);
      Object.assign(light.shadow.camera,{left:-span*.8,right:span*.8,top:span*.8,bottom:-span*.8,near:.1,far:height+span*3});
      light.shadow.camera.updateProjectionMatrix();
    });
  },dispose(){lights.forEach(l=>l.shadow.dispose());root.clear();}};
}
