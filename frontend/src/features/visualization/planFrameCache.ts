import * as THREE from 'three';

/** View-local color/depth layers; never changes scene geometry or source materials. */
export class PlanFrameCache {
 private base=new THREE.WebGLRenderTarget(1,1,{type:THREE.HalfFloatType,depthTexture:new THREE.DepthTexture(1,1)});
 private active=new THREE.WebGLRenderTarget(1,1,{type:THREE.HalfFloatType,depthTexture:new THREE.DepthTexture(1,1)});
 private key='';
 private screen=new THREE.Scene();
 private camera=new THREE.OrthographicCamera(-1,1,1,-1,0,1);
 private material=new THREE.ShaderMaterial({depthTest:false,depthWrite:false,
  uniforms:{base:{value:this.base.texture},baseDepth:{value:this.base.depthTexture},movingMap:{value:this.active.texture},activeDepth:{value:this.active.depthTexture},hasActive:{value:false}},
  vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}',
  fragmentShader:`uniform sampler2D base,baseDepth,movingMap,activeDepth;uniform bool hasActive;varying vec2 vUv;
   void main(){vec4 b=texture2D(base,vUv);vec4 a=texture2D(movingMap,vUv);
    bool front=hasActive&&texture2D(activeDepth,vUv).r<=texture2D(baseDepth,vUv).r;
    gl_FragColor=front?vec4(a.rgb+b.rgb*(1.-a.a),a.a+b.a*(1.-a.a)):b;
    if(min(texture2D(baseDepth,vUv).r,hasActive?texture2D(activeDepth,vUv).r:1.)<1.){
     #include <tonemapping_fragment>
    }
    #include <colorspace_fragment>
   }`});
 private quad=new THREE.Mesh(new THREE.PlaneGeometry(2,2),this.material);
 constructor(){this.screen.add(this.quad);}
 async prepare(renderer:THREE.WebGLRenderer,world:THREE.Scene,camera:THREE.Camera){
  const size=renderer.getDrawingBufferSize(new THREE.Vector2());this.base.setSize(size.x,size.y);this.active.setSize(size.x,size.y);
  this.invalidate();
  const previous=renderer.getRenderTarget();
  try{renderer.setRenderTarget(this.base);await renderer.compileAsync(world,camera);}
  finally{renderer.setRenderTarget(previous);}
  await renderer.compileAsync(this.screen,this.camera);
 }
 invalidate(){this.key='';}
 draw(renderer:THREE.WebGLRenderer,world:THREE.Scene,camera:THREE.Camera,root:THREE.Object3D,helper:THREE.Object3D,caps:THREE.Object3D,active:THREE.Object3D|undefined,revision:number){
  camera.updateMatrixWorld();const size=renderer.getDrawingBufferSize(new THREE.Vector2());
  if(this.base.width!==size.x||this.base.height!==size.y){this.base.setSize(size.x,size.y);this.active.setSize(size.x,size.y);this.invalidate();}
  const key=[revision,active?.uuid||'',...camera.matrixWorld.elements,...camera.projectionMatrix.elements].join(',');
  const target=renderer.getRenderTarget(),autoClear=renderer.autoClear,bg=world.background,clear=renderer.getClearColor(new THREE.Color()),alpha=renderer.getClearAlpha(),helperVisible=helper.visible;
  const hidden=new Map<THREE.Object3D,boolean>();const hide=(o:THREE.Object3D)=>{hidden.set(o,o.visible);o.visible=false;};
  const restore=()=>{hidden.forEach((v,o)=>{o.visible=v;});hidden.clear();};
  try{
   renderer.autoClear=true;helper.visible=false;
   if(key!==this.key){
    if(active)hide(active);
    renderer.setRenderTarget(this.base);renderer.render(world,camera);restore();this.key=key;
   }
   if(active){
    const selected=new Set<THREE.Object3D>();active.traverse(o=>selected.add(o));
    root.traverse(o=>{if((o instanceof THREE.Mesh||o instanceof THREE.Line)&&!selected.has(o))hide(o);});hide(caps);
    world.background=null;renderer.setClearColor(0,0);renderer.setRenderTarget(this.active);renderer.render(world,camera);restore();
   }
   this.material.uniforms.hasActive.value=!!active;
   renderer.setRenderTarget(target);renderer.render(this.screen,this.camera);
   // Transform handles are an editing overlay and intentionally sit above geometry.
   helper.visible=helperVisible;
   if(helperVisible){renderer.autoClear=false;renderer.clearDepth();renderer.render(helper,camera);}
  }finally{restore();helper.visible=helperVisible;world.background=bg;renderer.setClearColor(clear,alpha);renderer.setRenderTarget(target);renderer.autoClear=autoClear;}
 }
 dispose(){this.base.dispose();this.active.dispose();this.quad.geometry.dispose();this.material.dispose();this.screen.clear();}
}

/** Transparent/transmissive pieces need the full scene for correct compositing. */
export function supportsPlanLayer(root:THREE.Object3D,active?:THREE.Object3D){
 const bounds=active?new THREE.Box3().setFromObject(active):null;
 const members=new Set<THREE.Object3D>();active?.traverse(o=>members.add(o));
 let supported=true;root.traverseVisible(o=>{if(!(o instanceof THREE.Mesh))return;
  if(!(Array.isArray(o.material)?o.material:[o.material]).some(m=>m.visible&&(m.transparent||(m as THREE.MeshPhysicalMaterial).transmission>0)))return;
  if(!bounds||members.has(o)){supported=false;return;}
  // Top-down refraction can be cached only while it does not overlap the moving footprint.
  const other=new THREE.Box3().setFromObject(o);
  if(other.min.x<=bounds.max.x&&other.max.x>=bounds.min.x&&other.min.z<=bounds.max.z&&other.max.z>=bounds.min.z)supported=false;
 });return supported;
}
