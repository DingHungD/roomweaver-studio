import {lightDisplayName} from './configurationScope';
import {objectSize} from './objectSize';
import type {IncompleteItem} from './configurationIncomplete';
import {updateDoorPreview} from './doorPreview';
import {doorLines} from './doorGeometry';
import type {DoorPlan} from './doorGeometry';
import {frameViewport,frameShotViewport,usableViewport} from './cameraViewport';
import {createContext,useContext,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {createPortal} from 'react-dom';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import {assemble,applyDesign,visible} from './assemblyScene';
import type {AssemblyRuntime} from './assemblyScene';
import type {Scene,Viewpoint,Shot} from './api';
import {eyeVector,shotDirection,planPosition} from './viewpointGeometry';
import {lightPosition} from './lightGeometry';
import {buildPreview,clearPreview} from './previewLighting';
import {moveWalkCamera,lookWalkCamera} from './walkCamera';
import {PlanDisplay,hideImportedLights} from './planDisplay';
import {planRegion} from './planRegion';
import {createPlanLighting} from './planLighting';
import {PlanCaps} from './planCaps';
import {PlanFrameCache,supportsPlanLayer} from './planFrameCache';
import {makeArea} from './placementArea';
import {viewportProbe} from './viewportProbe';
import {prepareTextures,pickMeshes,disposeScene as dispose} from './viewportWork';
import {StaticPreview} from './staticPreview';
import type {PlacementArea} from './placementArea';
export type ViewMode='plan'|'walk'|'object';
type Props={incompleteSelected?:string;incomplete?:IncompleteItem[];focusGroup?:{id:string;serial:number};onIncompleteSelect?:(item:IncompleteItem)=>void;doorAssetPreviewUrl?:string;onDoorPart?:(id:string,part:'frame'|'leaf-0'|'leaf-1')=>void;doorPlans?:DoorPlan[];doorDrawing?:boolean;doorStart?:[number,number]|null;onDoorPoint?:(xy:[number,number])=>void;areaEditing?:boolean;placementArea?:PlacementArea|null;onArea?:(area:PlacementArea)=>void;onAreaCancel?:()=>void;url:string;design:Scene;mode:ViewMode;selected:string;child:string;moving:boolean;transformMode?:'translate'|'rotate';onRotate?:(id:string,angle:number,pivot:[number,number,number])=>void;onSelect:(group:string,child?:string)=>void;onMove:(id:string,delta:[number,number,number])=>void;
  onInspect?:(id:string)=>void;onSelectionCenter?:(xyz:[number,number,number])=>void;onSelectionSize?:(id:string,size:[number,number,number])=>void;
  softLighting?:boolean;lightEditing?:boolean;lightId?:string;onLightSelect?:(id:string)=>void;onLightMove?:(id:string,xy:[number,number])=>void;
  fixedPointMarkers?:boolean;pointEditing?:boolean;pointId?:string;focusPoint?:Viewpoint;focusShot?:Shot;matchShotFrame?:boolean;previewReset?:number;
  onPointSelect?:(id:string)=>void;onPointMove?:(id:string,xy:[number,number])=>void;onPlanCenter?:(xy:[number,number])=>void};
// A stable portal target moves between editor slots; WebGL, textures and parsed GLB stay alive.
const SharedViewport=createContext<{mount:HTMLDivElement;show:(props:Props)=>void}|null>(null);
export function ViewportProvider({children}:{children:ReactNode}){
 const [mount]=useState(()=>document.createElement('div'));
 const [props,show]=useState<Props|null>(null);
 const value=useMemo(()=>({mount,show}),[mount]);
 return <SharedViewport.Provider value={value}>{children}{props&&createPortal(<ViewportCanvas {...props}/>,mount)}</SharedViewport.Provider>;
}
export default function SpaceViewport(props:Props){
 const shared=useContext(SharedViewport),slot=useRef<HTMLDivElement>(null);
 useLayoutEffect(()=>{if(!shared||!slot.current)return;slot.current.appendChild(shared.mount);shared.show(props);},[shared,props]);
 useLayoutEffect(()=>{const owner=slot.current;return()=>{if(shared?.mount.parentNode===owner)shared?.mount.remove();};},[shared]);
 return shared?<div ref={slot} className="shared-viewport-slot"/>:<ViewportCanvas {...props}/>;
}
function ViewportCanvas(props:Props){
  const host=useRef<HTMLDivElement>(null),live=useRef(props);live.current=props;
  const runtime=useRef<{assembly:AssemblyRuntime;invalidate:()=>void;refresh:()=>void;selection:()=>void;setup:()=>void;updateIncomplete:()=>void;focusGroup:()=>void;planAt:(x:number,y:number)=>[number,number]|null;heightAt:(x:number,y:number)=>number}|null>(null);
  const areaDrag=useRef<{a:[number,number];b:[number,number]}|null>(null);
  const [areaRect,setAreaRect]=useState<{x:number;y:number;width:number;height:number}|null>(null);
  const areaOverlay=useRef<SVGSVGElement>(null),doorOverlay=useRef<SVGSVGElement>(null);
  const [doorStartPixel,setDoorStartPixel]=useState<[number,number]|null>(null);
  useEffect(()=>{const el=doorOverlay.current;if(!el||!props.doorDrawing)return;const stop=(e:WheelEvent)=>e.preventDefault();el.addEventListener('wheel',stop,{passive:false});return()=>el.removeEventListener('wheel',stop);},[props.doorDrawing]);
  useEffect(()=>{const el=areaOverlay.current;if(!el)return;const stop=(e:WheelEvent)=>{e.preventDefault();e.stopPropagation();};el.addEventListener('wheel',stop,{passive:false});return()=>{el.removeEventListener('wheel',stop);areaDrag.current=null;};},[props.areaEditing]);
  const pointDrag=useRef<{id:string;offset:[number,number];xy:[number,number];start:[number,number];moved:boolean}|null>(null);
  const [incompleteFrames,setIncompleteFrames]=useState<{id:string;lines:{x1:number;y1:number;x2:number;y2:number}[];x:number;y:number;width:number;height:number}[]>([]);
  const [markers,setMarkers]=useState<{id:string;x:number;y:number;dx:number;dy:number}[]>([]);
  const [selectionLines,setSelectionLines]=useState<{x1:number;y1:number;x2:number;y2:number}[]>([]);
  const [doorPaths,setDoorPaths]=useState<{id:string;lines:string[]}[]>([]);
  const [message,setMessage]=useState('正在載入模型…');
  const [position,setPosition]=useState('');
  const conceptIds=new Set((props.design.concept_furniture||[]).map(f=>f.id));
  const structureKey=JSON.stringify(props.design.groups.filter(g=>!conceptIds.has(g.id)).map(g=>[g.id,g.children]));
  useEffect(()=>{
    setMessage('正在載入模型…');setSelectionLines([]);setMarkers([]);setAreaRect(null);areaDrag.current=null;pointDrag.current=null;
    const element=host.current!;const probe=viewportProbe(element);let disposed=false,frame=0,last=performance.now();
    const world=new THREE.Scene();world.background=new THREE.Color('#e8e9e1');
    const perspective=new THREE.PerspectiveCamera(55,1,.02,2000),plan=new THREE.OrthographicCamera(-8,8,8,-8,.01,2000);
    let camera:THREE.PerspectiveCamera|THREE.OrthographicCamera=plan;
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setMessage('此裝置無法顯示 3D，仍可使用物件清單。');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.4;renderer.localClippingEnabled=true;renderer.shadowMap.autoUpdate=false;element.appendChild(renderer.domElement);
    const displayLights=new THREE.Group();world.add(displayLights);displayLights.add(new THREE.HemisphereLight(0xffffff,0x777766,2.2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(8,20,10);displayLights.add(light);
    const doorPreview=new THREE.Group();world.add(doorPreview);let doorKey='';let doorAssetUrl='';let doorAssetModel:THREE.Group|undefined;
    const lightingPreview=new THREE.Group();world.add(lightingPreview);let previewKey='';
    const planLighting=createPlanLighting();world.add(planLighting.root);planLighting.root.visible=false;
    const planCaps=new PlanCaps();world.add(planCaps.root);const planFrames=new PlanFrameCache();const supportsFrameCache=renderer.extensions.has('EXT_color_buffer_float');const shadowPrograms=new WeakMap<THREE.Material,boolean>();let visualRevision=0;
    const orbit=new OrbitControls<THREE.PerspectiveCamera|THREE.OrthographicCamera>(camera,renderer.domElement);orbit.enableDamping=true;
    const transform=new TransformControls(camera,renderer.domElement);transform.setMode('translate');transform.setSpace('world');const helper=transform.getHelper();world.add(helper);
    const incompleteBounds=new Map<string,THREE.Box3>();
    const box={box:new THREE.Box3(),visible:false};
    const planDisplay=new PlanDisplay();
    const clip=new THREE.Plane(new THREE.Vector3(0,-1,0),1.3);
    let assembly:AssemblyRuntime|undefined,staticPreview:StaticPreview|undefined;const keys=new Set<string>();let down=[0,0],dragging=false,wasTransform=false,span=8;let lastPick={id:'',time:0};let needsSetup=true;let needsRender=true;let preparing=false;
    function invalidate(){needsRender=true;if(!frame&&!disposed)frame=requestAnimationFrame(draw);}
    function insets(){
      const content=element.closest<HTMLElement>('.studio-content'),workspace=element.closest('.editor-workspace.is-editing');
      if(!content||!workspace)return {top:0,right:0,bottom:0,left:0};
      const inspector=element.closest('.space-editor')?.querySelector<HTMLElement>('.assembly-inspector');
      const right=inspector?.getClientRects().length?inspector.offsetWidth+24:24;
      const top=parseFloat(getComputedStyle(content).getPropertyValue('--editor-controls-bottom'))||0;
      return {top:Math.min(top+12,element.clientHeight*.6),right:Math.min(right,element.clientWidth*.6),bottom:90,left:24};
    }
    function resize(){
      if(!element.clientWidth||!element.clientHeight)return;
      invalidate();const w=element.clientWidth,h=element.clientHeight;
      const previous=renderer.getSize(new THREE.Vector2());if(previous.x!==w||previous.y!==h)renderer.setSize(w,h);
      plan.left=-span*w/h;plan.right=span*w/h;plan.top=span;plan.bottom=-span;
      const p=live.current,shot=p.focusShot||p.focusPoint?.shots[0];
      if(p.matchShotFrame&&p.mode==='walk'&&shot)frameShotViewport(perspective,w,h,insets(),shot);else {perspective.filmGauge=35;frameViewport(perspective,w,h,insets());}
      frameViewport(plan,w,h,insets());
      if(needsSetup&&assembly){needsSetup=false;setup();}
    }
    function refresh(){if(!assembly)return;const endMeasure=probe.start('refresh');visualRevision++;invalidate();const p=live.current;planDisplay.restore();applyDesign(assembly,p.design);
      for(const [id,g] of assembly.groups){const spec=p.design.groups.find(x=>x.id===id)!;g.visible=!spec.deleted&&(p.mode!=='object'||id===p.selected);}
      const actual=p.lightEditing&&p.mode==='walk';displayLights.visible=!actual&&p.mode!=='plan';lightingPreview.visible=!!actual;
      const softPlan=p.mode==='plan';planLighting.root.visible=softPlan;
      renderer.shadowMap.enabled=!p.moving&&(!!actual||softPlan);renderer.shadowMap.needsUpdate=renderer.shadowMap.enabled;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMappingExposure=actual?1.4*Math.pow(2,p.design.lighting_setup?.exposure||0):softPlan?1:1.4;
      world.background=new THREE.Color(actual?'#252925':p.mode==='plan'?'#f3f2ed':'#e8e9e1');
      hideImportedLights(assembly.root);
      const nextKey=actual?JSON.stringify([p.design.lighting_setup,p.design.groups.map(g=>[g.id,g.translation,g.rotation,g.rotation_pivot,g.deleted]),p.lightId,p.softLighting]):'';
      if(nextKey!==previewKey){previewKey=nextKey;if(actual){const size=new THREE.Box3().setFromObject(assembly.root).getSize(new THREE.Vector3());buildPreview(lightingPreview,p.design,p.lightId||'',{soften:p.softLighting,floorArea:size.x*size.z});}else clearPreview(lightingPreview);}
      // A horizontal cut makes the plan selectable even when a full ceiling exists.
      const region=p.mode==='plan'?planRegion(assembly,p.design):null;
      if(region)for(const id of region.hidden){const group=assembly.groups.get(id);if(group)group.visible=false;}
      renderer.clippingPlanes=region?[clip,...region.planes]:[];
      planCaps.root.visible=softPlan;
      if(p.mode==='plan'){
        const floors=new Set<THREE.Mesh>();
        planDisplay.apply(assembly.root,floors,softPlan,renderer.clippingPlanes);
        if(region)planLighting.fit(region.bounds);
        if(softPlan)planCaps.update(assembly,p.design,renderer.clippingPlanes);
      }
      // Invalidate programs when shadow availability changes, retaining borrowed textures.
      for(const root of [assembly.root,planCaps.root])root.traverse(o=>{if(o instanceof THREE.Mesh)for(const m of Array.isArray(o.material)?o.material:[o.material]){const previous=shadowPrograms.get(m);if(previous!==undefined&&previous!==renderer.shadowMap.enabled)m.needsUpdate=true;shadowPrograms.set(m,renderer.shadowMap.enabled);}});
      staticPreview?.sync();updateIncomplete();selection();endMeasure();
    }
    function updateIncomplete(){
      incompleteBounds.clear();if(assembly)for(const item of live.current.incomplete||[]){if(!item.available)continue;const group=assembly.groups.get(item.id);let bounds:THREE.Box3|undefined;if(item.target){const [lo,hi]=item.target.bounds;bounds=new THREE.Box3().setFromPoints([eyeVector(lo),eyeVector(hi)]);}else if(group)bounds=new THREE.Box3().setFromObject(group);if(bounds&&!bounds.isEmpty())incompleteBounds.set(item.id,bounds);}
      invalidate();
    }
    function focusGroup(){
      const p=live.current;if(!assembly||!p.focusGroup||!element.clientWidth)return;
      const group=assembly.groups.get(p.focusGroup.id);
      const bounds=incompleteBounds.get(p.focusGroup.id)?.clone()||(group?new THREE.Box3().setFromObject(group):null);if(!bounds||bounds.isEmpty())return;
      keys.clear();const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
      if(p.mode==='plan'){
        const safe=usableViewport(element.clientWidth,element.clientHeight,insets());
        span=Math.max(1.5,size.z/2*element.clientHeight/safe.height,size.x/2*element.clientHeight/safe.width)*1.6;plan.zoom=1;
        plan.position.set(center.x,bounds.max.y+30,center.z);orbit.target.set(center.x,0,center.z);plan.lookAt(orbit.target);p.onPlanCenter?.([center.x,-center.z]);
      }else if(p.mode==='walk'){
        const distance=Math.max(size.length()*1.1,1.2);perspective.fov=55;perspective.position.copy(center).add(new THREE.Vector3(distance*.7,distance*.4,distance*.8));perspective.lookAt(center);
      }
      resize();if(orbit.enabled)orbit.update();invalidate();
    }
    function selection(){if(!assembly)return;const p=live.current;invalidate();
      const group=assembly.groups.get(p.selected);const part=p.mode==='object'&&p.child?assembly.parts.get(p.child):group;
      box.visible=!!part&&visible(part);if(part&&box.visible)box.box.setFromObject(part);
      if(group&&visible(group)){const c=new THREE.Box3().setFromObject(group).getCenter(new THREE.Vector3());p.onSelectionCenter?.([c.x,-c.z,c.y]);if(p.onSelectionSize)p.onSelectionSize(p.selected,objectSize(group));}
      if(group&&p.moving&&p.mode!=='object'&&visible(group)){transform.setMode(p.transformMode||'translate');transform.attach(group);transform.showX=p.transformMode!=='rotate';transform.showZ=p.transformMode!=='rotate';transform.showY=p.transformMode==='rotate'||p.mode!=='plan';}
      else transform.detach();
    }
    function setup(){if(!assembly)return;if(!element.clientWidth){needsSetup=true;return;}needsSetup=false;keys.clear();const p=live.current;refresh();
      const bounds=p.mode==='plan'?planRegion(assembly,p.design).bounds:new THREE.Box3();if(p.mode!=='plan')for(const g of assembly.groups.values())if(g.visible)bounds.expandByObject(g);
      if(p.mode==='object'&&p.doorPlans){updateDoorPreview(doorPreview,p.doorPlans.filter(d=>d.id===p.pointId),doorAssetModel);bounds.setFromObject(doorPreview);}
      if(bounds.isEmpty())bounds.setFromCenterAndSize(new THREE.Vector3(),new THREE.Vector3(4,2,4));
      const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
      camera=p.mode==='plan'?plan:perspective;orbit.object=camera;transform.camera=camera;
      orbit.enabled=p.mode!=='walk';orbit.enableRotate=p.mode==='object';orbit.enablePan=p.mode==='plan';orbit.enableZoom=true;
      orbit.mouseButtons.LEFT=p.mode==='plan'?THREE.MOUSE.PAN:THREE.MOUSE.ROTATE;
      if(p.mode==='plan'){const safe=usableViewport(element.clientWidth,element.clientHeight,insets());span=Math.max(size.z/2*element.clientHeight/safe.height,size.x/2*element.clientHeight/safe.width)*1.18;plan.zoom=1;plan.up.set(0,0,-1);plan.position.set(center.x,bounds.max.y+30,center.z);orbit.target.set(center.x,0,center.z);plan.lookAt(orbit.target);}
      else if(p.mode==='object'){perspective.fov=45;const distance=Math.max(size.length()*1.25,.7);perspective.position.copy(center).add(new THREE.Vector3(distance*.7,distance*.5,distance*.8));orbit.target.copy(center);perspective.lookAt(center);}
      else {perspective.fov=55;const point=p.focusPoint||(!p.selected?p.design.viewpoints[0]:undefined);if(point){const shot=p.focusShot||point.shots[0];perspective.position.copy(eyeVector(shot?.eye||point.eye));perspective.lookAt(perspective.position.clone().add(shotDirection(shot?.yaw||0,shot?.pitch||0)));resize();perspective.setFocalLength(shot?.lens||24);}else{const selected=assembly.groups.get(p.selected);const target=selected?new THREE.Box3().setFromObject(selected).getCenter(new THREE.Vector3()):center;perspective.position.set(selected?target.x+1.5:center.x,1.6,selected?target.z+1.8:bounds.max.z-.8);perspective.lookAt(target);}}
      resize();if(orbit.enabled)orbit.update();
      if(p.mode==='plan')p.onPlanCenter?.([center.x,-center.z]);
    }
    const planAt=(x:number,y:number)=>{const r=element.getBoundingClientRect();return planPosition(camera,x-r.left,y-r.top,r.width,r.height);};
    const loadDone=probe.start('loadParse');
    new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(props.url,async gltf=>{loadDone();const prepDone=probe.start('prepare');if(disposed){dispose(gltf.scene);return;}world.add(gltf.scene);assembly=assemble(gltf.scene,live.current.design);
      const meshes:THREE.Mesh[]=[];gltf.scene.traverse(o=>{if(o instanceof THREE.Mesh)meshes.push(o);});
      for(const mesh of meshes){mesh.castShadow=true;mesh.receiveShadow=true;}
      staticPreview=new StaticPreview(assembly.root,new URLSearchParams(location.search).get('preview-batching')==='off'?Infinity:2000);
      if(staticPreview.enabled){world.remove(assembly.root);world.add(staticPreview.root);}
      element.dataset.previewBatches=JSON.stringify(staticPreview.statistics());
      runtime.current={assembly,invalidate,refresh,selection,setup,updateIncomplete,focusGroup,planAt,heightAt};setup();focusGroup();prepDone();preparing=true;
      try{
        const texturesDone=probe.start('textures');
        if(!await prepareTextures(gltf.scene,t=>renderer.initTexture(t),{cancelled:()=>disposed,progress:(done,total)=>{if(!disposed)setMessage(`正在準備模型貼圖… ${done}／${total}`);}}))return;
        texturesDone();setMessage('正在準備顯示效果…');const compileDone=probe.start('shaders');await renderer.compileAsync(world,camera);
        if(disposed)return;
        // Warm the no-shadow edit programs before the first user interaction.
        const hadShadows=renderer.shadowMap.enabled,attached=transform.object;
        renderer.shadowMap.enabled=false;if(!attached){const first=assembly.groups.values().next().value;if(first)transform.attach(first);}
        try{await renderer.compileAsync(world,camera);if(!disposed&&supportsFrameCache&&!staticPreview?.enabled)await planFrames.prepare(renderer,world,camera);}finally{renderer.shadowMap.enabled=hadShadows;if(!attached)transform.detach();}
        // Prepare the unclipped 3D shaders during loading, not on the first view switch.
        const oldClips=renderer.clippingPlanes,oldDisplay=displayLights.visible,oldPlan=planLighting.root.visible;
        planDisplay.restore();renderer.clippingPlanes=[];displayLights.visible=true;planLighting.root.visible=false;renderer.shadowMap.enabled=false;
        staticPreview?.sync();
        for(const root of [assembly.root,planCaps.root])root.traverse(o=>{if(o instanceof THREE.Mesh)for(const m of Array.isArray(o.material)?o.material:[o.material])m.needsUpdate=true;});
        await renderer.compileAsync(world,perspective);
        // Upload off-screen geometry during preparation, before interactive 3D entry.
        if(live.current.doorPlans){
          const target=renderer.getRenderTarget(),warmTarget=new THREE.WebGLRenderTarget(16,16);
          const culling=new Map<THREE.Object3D,boolean>();assembly.root.traverse(o=>{culling.set(o,o.frustumCulled);o.frustumCulled=false;});
          const doorVisible=doorPreview.visible;updateDoorPreview(doorPreview,live.current.doorPlans,doorAssetModel);doorPreview.visible=true;
          try{renderer.setRenderTarget(warmTarget);renderer.render(world,perspective);}finally{renderer.setRenderTarget(target);warmTarget.dispose();culling.forEach((v,o)=>{o.frustumCulled=v;});doorPreview.visible=doorVisible;}
        }
        renderer.clippingPlanes=oldClips;displayLights.visible=oldDisplay;planLighting.root.visible=oldPlan;renderer.shadowMap.enabled=hadShadows;
        compileDone();
        if(!disposed){refresh();preparing=false;invalidate();setMessage('');}
      }catch{if(!disposed){preparing=false;invalidate();setMessage('');}}
    },undefined,()=>{if(!disposed)setMessage('模型載入失敗，請重新開啟已保存設計。');});
    orbit.addEventListener('change',invalidate);
    const observer=new ResizeObserver(resize);observer.observe(element);document.addEventListener('studio-layout',resize);document.addEventListener('studio-frame',setup);
    function highlight(){invalidate();if(!assembly)return;const p=live.current;const o=p.mode==='object'&&p.child?assembly.parts.get(p.child):assembly.groups.get(p.selected);if(o&&visible(o)){box.visible=true;box.box.setFromObject(o);}else box.visible=false;}
    transform.addEventListener('dragging-changed',e=>{dragging=!!e.value;orbit.enabled=!dragging&&live.current.mode!=='walk';if(dragging)wasTransform=true;else if(assembly&&transform.object){const id=transform.object.userData.group_id;const spec=live.current.design.groups.find(g=>g.id===id)!;if(live.current.transformMode==='rotate'){const b=assembly.bases.get(id)!;live.current.onRotate?.(id,THREE.MathUtils.radToDeg(Math.atan2(2*(transform.object.quaternion.w*transform.object.quaternion.y+transform.object.quaternion.x*transform.object.quaternion.z),1-2*(transform.object.quaternion.y**2+transform.object.quaternion.z**2))),spec.rotation_pivot||[b.x,-b.z,b.y]);}else{const before=assembly.bases.get(id)!.clone(),pivot=new THREE.Vector3(spec.rotation_pivot?.[0]||0,spec.rotation_pivot?.[2]||0,-(spec.rotation_pivot?.[1]||0));before.sub(pivot).applyAxisAngle(new THREE.Vector3(0,1,0),THREE.MathUtils.degToRad(spec.rotation||0)).add(pivot);const delta=transform.object.position.clone().sub(before);live.current.onMove(id,[delta.x,-delta.z,delta.y]);}}});
    transform.addEventListener('change',invalidate);
    transform.addEventListener('objectChange',()=>{highlight();if(assembly&&planCaps.root.visible&&/^wall(?:$|[-_\s])|divider|牆/i.test(live.current.design.groups.find(g=>g.id===live.current.selected)?.name||'')){planCaps.update(assembly,live.current.design,renderer.clippingPlanes);}/* Furniture never rebuilds walls or shadows while dragging. */});
    const ray=new THREE.Raycaster();
    function sourceHits(){
      const hits=staticPreview?.enabled?staticPreview.intersections(ray):ray.intersectObjects(pickMeshes(assembly!.root),false);
      return [...hits,...ray.intersectObjects(pickMeshes(planCaps.root),false)].sort((a,b)=>a.distance-b.distance);
    }
    function heightAt(x:number,y:number){
      if(!assembly)return 0;
      const bounds=staticPreview?.enabled?staticPreview.bounds():new THREE.Box3().setFromObject(assembly.root);if(bounds.isEmpty())return 0;
      const top=bounds.max.y+10;
      ray.set(new THREE.Vector3(x,top,-y),new THREE.Vector3(0,-1,0));
      const hit=sourceHits().find(h=>h.object instanceof THREE.Mesh&&visible(h.object)&&!renderer.clippingPlanes.some(p=>p.distanceToPoint(h.point)<-.0001));
      return hit?Math.round(hit.point.y*1000)/1000:0;
    }
    function pointerDown(e:PointerEvent){element.focus();down=[e.clientX,e.clientY];wasTransform=!!transform.axis;}
    function pointerMove(e:PointerEvent){if(e.buttons)invalidate();if(e.buttons===1&&live.current.mode==='walk'&&!live.current.moving&&!dragging){lookWalkCamera(camera,e.movementX,e.movementY);}}
    function pointerUp(e:PointerEvent){if((live.current.pointEditing&&!live.current.doorPlans)||(live.current.lightEditing&&live.current.mode==='plan')||!assembly||wasTransform||dragging||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const r=element.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);
      if(live.current.doorPlans&&live.current.mode!=='plan'){
        const hit=ray.intersectObject(doorPreview,true)[0];if(hit){const id=hit.object.userData.doorId;live.current.onDoorPart?.(id,hit.object.userData.doorPart);const now=performance.now();if(live.current.mode!=='object'&&lastPick.id===id&&now-lastPick.time<380){live.current.onInspect?.(id);lastPick={id:'',time:0};}else lastPick={id,time:now};return;}
      }
      if(live.current.lightEditing){for(const hit of ray.intersectObject(lightingPreview,true)){if(hit.object.userData.lightId){const id=hit.object.userData.lightId;live.current.onLightSelect?.(id);const now=performance.now();if(lastPick.id===id&&now-lastPick.time<380){live.current.onInspect?.(id);lastPick={id:'',time:0};}else lastPick={id,time:now};break;}}return;}
      for(const hit of sourceHits()){if(!(hit.object instanceof THREE.Mesh)||!visible(hit.object)||(live.current.mode==='plan'&&renderer.clippingPlanes.some(plane=>plane.distanceToPoint(hit.point)<-.0001)))continue;let part:THREE.Object3D|null=hit.object.userData.planSource||hit.object;while(part&&!part.userData.studio_id)part=part.parent;let group=part;while(group&&!group.userData.group_id)group=group.parent;if(part&&group){const id=group.userData.group_id;live.current.onSelect(id,live.current.mode==='object'?part.userData.studio_id:undefined);
        const now=performance.now();if(live.current.mode!=='object'&&lastPick.id===id&&now-lastPick.time<380){live.current.onInspect?.(id);lastPick={id:'',time:0};}else lastPick={id,time:now};break;}}
    }
    function wheel(e:WheelEvent){invalidate();if(live.current.mode==='walk'){e.preventDefault();perspective.fov=THREE.MathUtils.clamp(perspective.fov+e.deltaY*.03,20,95);perspective.updateProjectionMatrix();}}
    const allowed=['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright','e','q'];
    function keydown(e:KeyboardEvent){if(document.activeElement!==element)return;const key=e.key.toLowerCase();if(allowed.includes(key)){e.preventDefault();keys.add(key);invalidate();}}
    function keyup(e:KeyboardEvent){keys.delete(e.key.toLowerCase());}
    const blur=()=>keys.clear();element.addEventListener('keydown',keydown);window.addEventListener('keyup',keyup);element.addEventListener('blur',blur);window.addEventListener('blur',blur);
    renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointermove',pointerMove);renderer.domElement.addEventListener('pointerup',pointerUp);renderer.domElement.addEventListener('wheel',wheel,{passive:false});
    function draw(t:number){frame=0;const dt=Math.min((t-last)/1000,.05);last=t;if(!element.clientWidth||!element.clientHeight)return;const p=live.current;
      const forward=Number(keys.has('w')||keys.has('arrowup'))-Number(keys.has('s')||keys.has('arrowdown'));
      const sideways=Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('arrowleft'));
      if(p.mode==='plan'&&(forward||sideways)){const delta=new THREE.Vector3(sideways*dt*span,0,-forward*dt*span);camera.position.add(delta);orbit.target.add(delta);}
      if(p.mode==='walk'){moveWalkCamera(camera,forward,sideways,Number(keys.has('e'))-Number(keys.has('q')),dt);}
      if(orbit.enabled)orbit.update();if(forward||sideways||keys.size)invalidate();
      if(doorAssetUrl!==(p.doorAssetPreviewUrl||'')){doorAssetUrl=p.doorAssetPreviewUrl||'';if(doorAssetModel)dispose(doorAssetModel);doorAssetModel=undefined;doorKey='';const url=doorAssetUrl;if(url)new GLTFLoader().load(url,g=>{if(disposed||doorAssetUrl!==url){dispose(g.scene);return;}doorAssetModel=g.scene;g.scene.updateMatrixWorld(true);doorKey='';needsSetup=true;invalidate();},undefined,()=>{if(!disposed&&doorAssetUrl===url)setMessage('門素材預覽載入失敗，請重新開啟；原門設定保留。');});}
      const visibleDoors=p.mode==='object'?(p.doorPlans||[]).filter(d=>d.id===p.pointId):(p.doorPlans||[]);const nextDoorKey=JSON.stringify(visibleDoors);if(doorKey!==nextDoorKey){doorKey=nextDoorKey;updateDoorPreview(doorPreview,visibleDoors,doorAssetModel);visualRevision++;needsRender=true;}doorPreview.visible=p.mode==='walk'||p.mode==='object';if(p.doorPlans)doorPreview.traverse(o=>{if(o instanceof THREE.Mesh)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>{if(m instanceof THREE.MeshStandardMaterial)m.emissive.set(p.mode==='object'&&o.userData.doorPart===p.child?'#302010':'#000000');});});
      let doorVisibilityChanged=false;
      if(p.doorPlans&&assembly)for(const g of assembly.groups.values()){const spec=p.design.groups.find(s=>s.id===g.userData.group_id);if(g.visible&&spec&&p.doorPlans.some(d=>spec.name.includes(`[${d.id}]`)&&d.control.kind)){g.visible=false;doorVisibilityChanged=true;}}
      if(!needsRender||preparing)return;needsRender=false;const renderStarted=performance.now(),renderDone=probe.start('render');
      renderer.info.autoReset=false;renderer.info.reset();
      const active=assembly?.groups.get(p.selected),layer=supportsFrameCache&&!staticPreview?.enabled&&p.mode==='plan'&&assembly&&(!p.moving||!!active&&supportsPlanLayer(assembly.root,active)&&!/^wall(?:$|[-_\s])|divider|牆/i.test(p.design.groups.find(g=>g.id===p.selected)?.name||''));
      if(staticPreview?.enabled&&(dragging||doorVisibilityChanged))staticPreview.sync(dragging&&!doorVisibilityChanged?active:undefined);
      if(new URLSearchParams(location.search).has('performance'))element.dataset.viewState=JSON.stringify({position:camera.position.toArray(),quaternion:camera.quaternion.toArray(),zoom:camera.zoom,mode:p.mode,selected:p.selected});
      element.dataset.previewPath=layer?(p.moving?'layers':'snapshot'):'scene';
      if(layer)planFrames.draw(renderer,world,camera,assembly!.root,helper,planCaps.root,p.moving?active:undefined,visualRevision);else renderer.render(world,camera);
      renderDone();if(assembly)probe.frame(renderer.info.render,renderStarted,dragging?`${p.mode}-${p.transformMode||'translate'}`:'idle');
      {if(p.doorStart&&p.mode==='plan'){const v=eyeVector([...p.doorStart,0]).project(camera);setDoorStartPixel([(v.x+1)*element.clientWidth/2,(1-v.y)*element.clientHeight/2]);}else setDoorStartPixel(null);
        if(p.doorPlans&&p.mode==='plan')setDoorPaths(p.doorPlans.map(d=>({id:d.id,lines:doorLines(d).map(line=>line.map(xy=>{const v=eyeVector([...xy,0]).project(camera);return `${(v.x+1)*element.clientWidth/2},${(1-v.y)*element.clientHeight/2}`;}).join(' '))})));
        setPosition(`X ${camera.position.x.toFixed(2)} · Y ${(-camera.position.z).toFixed(2)} · 高 ${camera.position.y.toFixed(2)} m`);
        const draft=areaDrag.current;
        const region=draft?makeArea(draft.a,draft.b):p.placementArea;
        if(region&&p.mode==='plan'){
          const a=eyeVector([region.center[0]-region.size[0]/2,region.center[1]-region.size[1]/2,0]).project(camera);
          const b=eyeVector([region.center[0]+region.size[0]/2,region.center[1]+region.size[1]/2,0]).project(camera);
          setAreaRect({x:(Math.min(a.x,b.x)+1)*element.clientWidth/2,y:(1-Math.max(a.y,b.y))*element.clientHeight/2,width:Math.abs(a.x-b.x)*element.clientWidth/2,height:Math.abs(a.y-b.y)*element.clientHeight/2});
        }else setAreaRect(null);
        setIncompleteFrames((p.mode==='object'||p.moving?[]:[...incompleteBounds]).flatMap(([id,bounds])=>{
          const {min,max}=bounds;
          const corners=Array.from({length:8},(_,i)=>new THREE.Vector3(i&1?max.x:min.x,p.mode==='plan'?0:(i&2?max.y:min.y),i&4?max.z:min.z).project(camera));
          const edges=p.mode==='plan'?[[0,1],[1,5],[5,4],[4,0]]:[[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
          const lines=edges.filter(([a,b])=>[a,b].every(i=>corners[i].z>=-1&&corners[i].z<=1)).map(([a,b])=>({x1:(corners[a].x+1)*element.clientWidth/2,y1:(1-corners[a].y)*element.clientHeight/2,x2:(corners[b].x+1)*element.clientWidth/2,y2:(1-corners[b].y)*element.clientHeight/2}));
          if(!lines.length)return [];
          const xs=lines.flatMap(l=>[l.x1,l.x2]),ys=lines.flatMap(l=>[l.y1,l.y2]);
          const x=Math.min(...xs),y=Math.min(...ys),width=Math.max(...xs)-x,height=Math.max(...ys)-y;
          return [{id,lines,x,y,width,height}];
        }));
        if(box.visible){
          const {min,max}=box.box;
          const corners=Array.from({length:8},(_,i)=>new THREE.Vector3(i&1?max.x:min.x,i&2?max.y:min.y,i&4?max.z:min.z).project(camera));
          const edges=[[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
          setSelectionLines(edges.filter(([a,b])=>corners[a].z>=-1&&corners[a].z<=1&&corners[b].z>=-1&&corners[b].z<=1).map(([a,b])=>({x1:(corners[a].x+1)*element.clientWidth/2,y1:(1-corners[a].y)*element.clientHeight/2,x2:(corners[b].x+1)*element.clientWidth/2,y2:(1-corners[b].y)*element.clientHeight/2})));
        }else setSelectionLines([]);
        const points=p.lightEditing?(p.design.lighting_setup?.lights||[]).filter(l=>!p.design.groups.find(g=>g.id===l.group_id)?.deleted).map(l=>({id:l.id,eye:lightPosition(l,p.design),shots:[]})):p.design.viewpoints;
        if((p.pointEditing||p.lightEditing)&&p.mode==='plan')setMarkers(points.map(point=>{
          const drag=pointDrag.current?.id===point.id?pointDrag.current:null;
          const v=eyeVector([...(drag?.xy||point.eye.slice(0,2)),0]);
          const shot=point.id===p.pointId?p.focusShot||point.shots[0]:point.shots[0];
          const direction=shotDirection(shot?.yaw||0,0).add(v).project(camera);v.project(camera);
          return {id:point.id,x:(v.x+1)*element.clientWidth/2,y:(1-v.y)*element.clientHeight/2,dx:(direction.x-v.x)*element.clientWidth/2,dy:(v.y-direction.y)*element.clientHeight/2};
        }));
      }
    }invalidate();
    return()=>{disposed=true;probe.dispose();runtime.current=null;cancelAnimationFrame(frame);observer.disconnect();document.removeEventListener('studio-layout',resize);document.removeEventListener('studio-frame',setup);transform.dispose();orbit.dispose();element.removeEventListener('keydown',keydown);element.removeEventListener('blur',blur);window.removeEventListener('keyup',keyup);window.removeEventListener('blur',blur);assembly?.materials.forEach(m=>m.dispose());planDisplay.dispose();planLighting.dispose();planCaps.dispose();planFrames.dispose();staticPreview?.dispose();if(staticPreview?.enabled&&assembly)dispose(assembly.root);clearPreview(lightingPreview);if(doorAssetModel)dispose(doorAssetModel);dispose(world);renderer.dispose();element.removeChild(renderer.domElement);};
  },[props.url,structureKey]);
  useEffect(()=>{runtime.current?.refresh();},[props.design,props.lightId,props.softLighting,props.lightEditing,props.pointEditing,props.moving]);
  useEffect(()=>{if(props.mode==='object')runtime.current?.refresh();else runtime.current?.selection();},[props.selected,props.child,props.moving,props.transformMode]);
  useEffect(()=>{runtime.current?.setup();},[props.mode,props.lightEditing,props.pointEditing,props.mode==='object'?props.selected:'',props.mode==='walk'?JSON.stringify([props.focusPoint?.id,props.focusPoint?.eye]):'',props.mode==='walk'?JSON.stringify(props.focusShot||props.focusPoint?.shots[0]):'',props.previewReset]);
  useEffect(()=>{runtime.current?.updateIncomplete();},[props.incomplete]);
  useEffect(()=>{runtime.current?.focusGroup();},[props.focusGroup,props.mode]);
  useEffect(()=>{runtime.current?.invalidate();},[props.pointId,props.focusShot,props.areaEditing,props.placementArea,props.doorPlans,props.doorDrawing,props.doorStart,props.doorAssetPreviewUrl]);
  function dragPoint(e:React.PointerEvent<SVGGElement>){
    const drag=pointDrag.current;if(!drag)return;
    const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;
    drag.xy=[xy[0]+drag.offset[0],xy[1]+drag.offset[1]];runtime.current?.invalidate();
    drag.moved ||= Math.hypot(e.clientX-drag.start[0],e.clientY-drag.start[1])>3;
  }
  return <div className="space-viewport">
    <div ref={host} tabIndex={0} role="application" aria-label="空間操作畫布" className="space-canvas"/>
    {props.mode==='plan'&&props.doorPlans&&<svg ref={doorOverlay} className={`placement-overlay ${props.doorDrawing?'drawing':''}`} aria-label="門平面符號" onPointerDown={e=>{if(!props.doorDrawing)return;e.preventDefault();e.stopPropagation();const xy=runtime.current?.planAt(e.clientX,e.clientY);if(xy)props.onDoorPoint?.(xy);}}>{doorStartPixel&&<g transform={`translate(${doorStartPixel[0]} ${doorStartPixel[1]})`}><circle r="5" fill="#e08124"/><text x="9" y="-7" fill="#774415">A</text></g>}{doorPaths.map(d=><g key={d.id} stroke={d.id===props.pointId?'#e08124':'#245b52'} strokeWidth={d.id===props.pointId?3:2} fill="none">{d.lines.map((line,i)=><polyline key={i} points={line} onDoubleClick={()=>props.onInspect?.(d.id)} style={{pointerEvents:'stroke'}} stroke={props.doorPlans?.find(p=>p.id===d.id)?.control.materials?.[i===0?'frame':i===1?'leaf-0':'leaf-1']?.color} strokeDasharray={i>1?'5 3':undefined}/>)}{d.id===props.pointId&&d.lines[0]?.split(' ').map((xy,i)=><text key={'label'+i} x={Number(xy.split(',')[0])+5} y={Number(xy.split(',')[1])-9} stroke="none" fill="#774415" fontSize="12">{i===0?'A':'B'}</text>)}</g>)}</svg>}
    {props.mode==='plan'&&(props.areaEditing||props.placementArea)&&<svg ref={areaOverlay} className={`placement-overlay ${props.areaEditing?'drawing':''}`} tabIndex={props.areaEditing?0:-1} role="application" aria-label="框選新增範圍"
      onKeyDown={e=>{if(e.key==='Escape'){areaDrag.current=null;props.onAreaCancel?.();}}}
      onPointerDown={e=>{if(!props.areaEditing||e.button!==0||!runtime.current)return;e.preventDefault();e.stopPropagation();e.currentTarget.focus();const p=runtime.current.planAt(e.clientX,e.clientY);if(!p)return;e.currentTarget.setPointerCapture(e.pointerId);areaDrag.current={a:p,b:p};runtime.current.invalidate();}}
      onPointerMove={e=>{const p=runtime.current?.planAt(e.clientX,e.clientY);if(areaDrag.current&&p){areaDrag.current.b=p;runtime.current?.invalidate();}}}
      onPointerCancel={()=>{areaDrag.current=null;props.onAreaCancel?.();}}
      onPointerUp={e=>{const d=areaDrag.current;areaDrag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(!d)return;const end=runtime.current?.planAt(e.clientX,e.clientY)||d.b;const area=makeArea(d.a,end);area.height=runtime.current?.heightAt(...area.center)||0;if(Math.min(...area.size)>.01)props.onArea?.(area);}}>
      {areaRect&&<rect {...areaRect} fill="#427d662d" stroke="#285744" strokeWidth="2" strokeDasharray="7 4"/>}
      {props.areaEditing&&<text x="16" y="54" fill="#285744" fontSize="14">拖曳框選新增範圍 · Esc 取消</text>}
    </svg>}
    {!!incompleteFrames.length&&<svg className="incomplete-overlay" aria-label="未完成物件位置">{incompleteFrames.map(frame=>{const index=props.incomplete?.findIndex(i=>i.id===frame.id)??-1,item=props.incomplete?.[index];if(!item)return null;const active=frame.id===(props.incompleteSelected??props.selected);return <g key={frame.id} className={active?'is-selected':''} role="button" tabIndex={0} aria-label={`定位未完成物件 ${item.name}`} onClick={e=>{e.stopPropagation();props.onIncompleteSelect?.(item);}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();props.onIncompleteSelect?.(item);}}}><title>{item.name} · {item.status}</title>{props.mode==='plan'&&<rect x={frame.x} y={frame.y} width={Math.max(frame.width,8)} height={Math.max(frame.height,8)} className="incomplete-hit"/>}{frame.lines.map((line,i)=><line key={i} {...line}/>)}<rect x={frame.x} y={frame.y-22} width="32" height="22" rx="4" className="incomplete-number"/><text x={frame.x+16} y={frame.y-7} textAnchor="middle">{index+1}</text></g>;})}</svg>}
    {!!selectionLines.length&&<svg className="selection-overlay" aria-label="已選取物件外框">{selectionLines.map((line,i)=><g key={i}><line {...line} className="selection-underlay"/><line {...line} className="selection-dash"/></g>)}</svg>}
    {props.lightEditing&&props.mode==='plan'&&!message&&<svg className="viewpoint-overlay light-overlay" aria-label="光源平面配置">
      {markers.map((p,i)=>{const light=props.design.lighting_setup?.lights.find(l=>l.id===p.id);if(!light)return null;const active=p.id===props.lightId;return <g key={p.id} transform={`translate(${p.x} ${p.y})`}>
        <g role="button" tabIndex={0} aria-label={`光源 ${lightDisplayName(props.design,light)}`} aria-pressed={active} className={`point-marker light-marker ${active?'active':''} ${light.enabled?'':'off'}`}
          onDoubleClick={e=>{e.stopPropagation();props.onInspect?.(p.id);}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();props.onLightSelect?.(p.id);}}}
          onPointerDown={e=>{if(e.button!==0)return;e.stopPropagation();const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;const pos=lightPosition(light,props.design);e.currentTarget.setPointerCapture(e.pointerId);pointDrag.current={id:p.id,offset:[pos[0]-xy[0],pos[1]-xy[1]],xy:[pos[0],pos[1]],start:[e.clientX,e.clientY],moved:false};props.onLightSelect?.(p.id);}}
          onPointerMove={dragPoint} onPointerCancel={()=>{pointDrag.current=null;}}
          onPointerUp={e=>{dragPoint(e);const drag=pointDrag.current;pointDrag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(drag?.moved)props.onLightMove?.(drag.id,drag.xy);}}>
          <circle r="27" className="light-halo"/><circle r="16"/><text textAnchor="middle" dy="4">{String(i+1).padStart(2,'0')}</text><title>{lightDisplayName(props.design,light)}：拖曳移動光源</title>
        </g><text textAnchor="middle" y="42" className="point-name">{lightDisplayName(props.design,light)}{light.enabled?'':' · 關閉'}</text>
      </g>;})}
    </svg>}
    {props.pointEditing&&props.mode==='plan'&&!message&&<svg className="viewpoint-overlay" aria-label={props.fixedPointMarkers?'門的位置':'觀看點平面配置'}>
      {props.design.links.map(([a,b])=>{const from=markers.find(p=>p.id===a),to=markers.find(p=>p.id===b);return from&&to?<g key={a+'-'+b}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="point-link"/><text x={(from.x+to.x)/2} y={(from.y+to.y)/2-5} className="link-symbol">↔</text></g>:null;})}
      {markers.map((p,i)=>{const spec=props.design.viewpoints.find(x=>x.id===p.id);const active=p.id===props.pointId;return <g key={p.id} transform={`translate(${p.x} ${p.y})`}>
        {!props.fixedPointMarkers&&<path d="M 0 0 L 74 -38 A 83 83 0 0 1 74 38 Z" transform={`rotate(${Math.atan2(p.dy,p.dx)*180/Math.PI})`} className={active?'point-cone active':'point-cone'}/>}
        <g role="button" tabIndex={0} aria-label={`${props.fixedPointMarkers?'門':'觀看點'} ${String(i+1).padStart(2,'0')} ${spec?.name}`} aria-pressed={active} className="point-marker"
          onDoubleClick={e=>{if(props.doorPlans){e.stopPropagation();props.onInspect?.(p.id);}}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();props.onPointSelect?.(p.id);}}}
          onPointerDown={e=>{if(e.button!==0||!spec)return;e.stopPropagation();if(props.fixedPointMarkers){props.onPointSelect?.(p.id);return;}const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;e.currentTarget.setPointerCapture(e.pointerId);pointDrag.current={id:p.id,offset:[spec.eye[0]-xy[0],spec.eye[1]-xy[1]],xy:[spec.eye[0],spec.eye[1]],start:[e.clientX,e.clientY],moved:false};props.onPointSelect?.(p.id);}}
          onPointerMove={dragPoint} onPointerCancel={()=>{pointDrag.current=null;}}
          onPointerUp={e=>{dragPoint(e);const drag=pointDrag.current;pointDrag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(drag?.moved)props.onPointMove?.(drag.id,drag.xy);}}>
          <circle r={props.fixedPointMarkers?11:18} fill={active?'#2b5144':'#fffef9'}/><text textAnchor="middle" dy="4" fill={active?'white':'#2b5144'}>{String(i+1).padStart(2,'0')}</text><title>{props.doorPlans?.find(d=>d.id===p.id)?.control.name||spec?.name}{props.fixedPointMarkers?'：點選編輯方位':'：拖曳移動觀看點'}</title>
        </g><text textAnchor="middle" y="35" className="point-name">{props.doorPlans?.find(d=>d.id===p.id)?.control.name||spec?.name}</text>
      </g>;})}
    </svg>}
    {message&&<div className="viewer-message">{message}</div>}
    <span className="camera-position" aria-live="off">{position}</span>
    <span className="viewer-help">{props.mode==='plan'?(props.lightEditing?'拖曳光源調整位置 · 家具鎖定 · 滾輪縮放':props.pointEditing?(props.fixedPointMarkers?'點選門的位置 · 門洞鎖定 · 滾輪縮放':'拖曳圓點調整位置 · 拖曳空白處平移 · 滾輪縮放'):'WASD／方向鍵平移 · 滾輪縮放 · 點選物件 · 雙擊單物件展示'):props.mode==='walk'?'W/S 前後 · A/D／左右鍵水平平移 · E 上升／Q 下降 · 拖曳看四周 · 滾輪縮放':props.doorPlans?'拖曳繞門旋轉 · 滾輪縮放 · 點選門框／門片':'拖曳繞物件旋轉 · 滾輪縮放 · 點選子物件'}<br/>{props.pointEditing&&props.mode==='walk'?'即時 3D 預覽，尚未渲染；預覽移動不修改觀看點。':'點一下畫布後使用鍵盤'}{props.moving?' · 流暢調整：保留材質、暫停陰影；結束調整後恢復':''}</span>
  </div>;
}
