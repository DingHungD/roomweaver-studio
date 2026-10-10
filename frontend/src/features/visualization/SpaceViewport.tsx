import {useEffect,useRef,useState} from 'react';
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
export type ViewMode='plan'|'walk'|'object';
type Props={url:string;design:Scene;mode:ViewMode;selected:string;child:string;moving:boolean;onSelect:(group:string,child?:string)=>void;onMove:(id:string,delta:[number,number,number])=>void;
  planContrast?:boolean;onInspect?:(id:string)=>void;onSelectionCenter?:(xyz:[number,number,number])=>void;
  softLighting?:boolean;lightEditing?:boolean;lightId?:string;onLightSelect?:(id:string)=>void;onLightMove?:(id:string,xy:[number,number])=>void;
  pointEditing?:boolean;pointId?:string;focusPoint?:Viewpoint;focusShot?:Shot;previewReset?:number;
  onPointSelect?:(id:string)=>void;onPointMove?:(id:string,xy:[number,number])=>void;onPlanCenter?:(xy:[number,number])=>void};
export default function SpaceViewport(props:Props){
  const host=useRef<HTMLDivElement>(null),live=useRef(props);live.current=props;
  const runtime=useRef<{assembly:AssemblyRuntime;refresh:()=>void;setup:()=>void;planAt:(x:number,y:number)=>[number,number]|null}|null>(null);
  const pointDrag=useRef<{id:string;offset:[number,number];xy:[number,number];start:[number,number];moved:boolean}|null>(null);
  const [markers,setMarkers]=useState<{id:string;x:number;y:number;dx:number;dy:number}[]>([]);
  const [selectionLines,setSelectionLines]=useState<{x1:number;y1:number;x2:number;y2:number}[]>([]);
  const [message,setMessage]=useState('正在載入模型…');
  const [position,setPosition]=useState('');
  useEffect(()=>{
    const element=host.current!;let disposed=false,frame=0,last=performance.now(),lastLabel=0;
    const world=new THREE.Scene();world.background=new THREE.Color('#e8e9e1');
    const perspective=new THREE.PerspectiveCamera(55,1,.02,2000),plan=new THREE.OrthographicCamera(-8,8,8,-8,.01,2000);
    let camera:THREE.PerspectiveCamera|THREE.OrthographicCamera=plan;
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setMessage('此裝置無法顯示 3D，仍可使用物件清單。');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.4;renderer.localClippingEnabled=true;renderer.shadowMap.autoUpdate=false;element.appendChild(renderer.domElement);
    const displayLights=new THREE.Group();world.add(displayLights);displayLights.add(new THREE.HemisphereLight(0xffffff,0x777766,2.2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(8,20,10);displayLights.add(light);
    const lightingPreview=new THREE.Group();world.add(lightingPreview);let previewKey='';
    const orbit=new OrbitControls<THREE.PerspectiveCamera|THREE.OrthographicCamera>(camera,renderer.domElement);orbit.enableDamping=true;
    const transform=new TransformControls(camera,renderer.domElement);transform.setMode('translate');transform.setSpace('world');const helper=transform.getHelper();world.add(helper);
    const box={box:new THREE.Box3(),visible:false};
    const outlines:THREE.LineSegments[]=[];
    const floorPreview=new THREE.MeshStandardMaterial({color:'#e4e7df',roughness:1});
    const floorMaterials=new Map<THREE.Mesh,THREE.Material|THREE.Material[]>();
    const clip=new THREE.Plane(new THREE.Vector3(0,-1,0),1.3);
    let assembly:AssemblyRuntime|undefined;const keys=new Set<string>();let down=[0,0],dragging=false,wasTransform=false,span=8;let lastPick={id:'',time:0};let needsSetup=true;
    function resize(){const w=Math.max(1,element.clientWidth),h=Math.max(1,element.clientHeight);renderer.setSize(w,h);perspective.aspect=w/h;perspective.updateProjectionMatrix();plan.left=-span*w/h;plan.right=span*w/h;plan.top=span;plan.bottom=-span;plan.updateProjectionMatrix();if(needsSetup&&assembly&&element.clientWidth>0){needsSetup=false;setup();}}
    function refresh(){if(!assembly)return;const p=live.current;floorMaterials.forEach((material,mesh)=>{mesh.material=material;});floorMaterials.clear();applyDesign(assembly,p.design);
      for(const [id,g] of assembly.groups){const spec=p.design.groups.find(x=>x.id===id)!;g.visible=!spec.deleted&&(p.mode!=='object'||id===p.selected);}
      const actual=p.lightEditing&&p.mode==='walk';displayLights.visible=!actual;lightingPreview.visible=!!actual;
      renderer.shadowMap.enabled=!!actual;renderer.shadowMap.needsUpdate=!!actual;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMappingExposure=actual?1.4*Math.pow(2,p.design.lighting_setup?.exposure||0):1.4;
      world.background=new THREE.Color(actual?'#252925':'#e8e9e1');
      assembly.root.traverse(o=>{if(o instanceof THREE.Light){o.userData.previewWasVisible??=o.visible;o.visible=actual?false:o.userData.previewWasVisible;}});
      const nextKey=actual?JSON.stringify([p.design.lighting_setup,p.design.groups.map(g=>[g.id,g.translation,g.deleted]),p.lightId,p.softLighting]):'';
      if(nextKey!==previewKey){previewKey=nextKey;if(actual){const size=new THREE.Box3().setFromObject(assembly.root).getSize(new THREE.Vector3());buildPreview(lightingPreview,p.design,p.lightId||'',{soften:p.softLighting,floorArea:size.x*size.z});}else clearPreview(lightingPreview);}
      // A horizontal cut makes the plan selectable even when a full ceiling exists.
      renderer.clippingPlanes=p.mode==='plan'?[clip]:[];
      outlines.forEach(line=>{line.visible=p.mode==='plan'&&p.planContrast!==false;});
      if(p.mode==='plan'&&p.planContrast!==false){for(const spec of p.design.groups){if(!/^(floor|floor[-_ ]|地板|地坪)/i.test(spec.name))continue;assembly.groups.get(spec.id)?.traverse(o=>{if(o instanceof THREE.Mesh){floorMaterials.set(o,o.material);o.material=floorPreview;}});}}
      const group=assembly.groups.get(p.selected);const part=p.mode==='object'&&p.child?assembly.parts.get(p.child):group;
      box.visible=!!part&&visible(part);if(part&&box.visible)box.box.setFromObject(part);
      if(group&&visible(group)){const c=new THREE.Box3().setFromObject(group).getCenter(new THREE.Vector3());p.onSelectionCenter?.([c.x,-c.z,c.y]);}
      if(group&&p.moving&&p.mode!=='object'&&visible(group)){transform.attach(group);transform.showY=p.mode!=='plan';}
      else transform.detach();
    }
    function setup(){if(!assembly)return;if(!element.clientWidth){needsSetup=true;return;}needsSetup=false;keys.clear();const p=live.current;refresh();
      const bounds=new THREE.Box3();for(const g of assembly.groups.values())if(g.visible)bounds.expandByObject(g);
      if(bounds.isEmpty())bounds.setFromCenterAndSize(new THREE.Vector3(),new THREE.Vector3(4,2,4));
      const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
      camera=p.mode==='plan'?plan:perspective;orbit.object=camera;transform.camera=camera;
      orbit.enabled=p.mode!=='walk';orbit.enableRotate=p.mode==='object';orbit.enablePan=p.mode==='plan';orbit.enableZoom=true;
      orbit.mouseButtons.LEFT=p.mode==='plan'?THREE.MOUSE.PAN:THREE.MOUSE.ROTATE;
      if(p.mode==='plan'){span=Math.max(size.z/2,size.x/(2*(element.clientWidth/Math.max(1,element.clientHeight))))*1.18;plan.zoom=1;plan.up.set(0,0,-1);plan.position.set(center.x,bounds.max.y+30,center.z);orbit.target.set(center.x,0,center.z);plan.lookAt(orbit.target);}
      else if(p.mode==='object'){perspective.fov=45;const distance=Math.max(size.length()*1.25,.7);perspective.position.copy(center).add(new THREE.Vector3(distance*.7,distance*.5,distance*.8));orbit.target.copy(center);perspective.lookAt(center);}
      else {perspective.fov=55;const point=p.focusPoint||(!p.selected?p.design.viewpoints[0]:undefined);if(point){const shot=p.focusShot||point.shots[0];perspective.position.copy(eyeVector(point.eye));perspective.lookAt(perspective.position.clone().add(shotDirection(shot?.yaw||0,shot?.pitch||0)));resize();perspective.setFocalLength(shot?.lens||24);}else{const selected=assembly.groups.get(p.selected);const target=selected?new THREE.Box3().setFromObject(selected).getCenter(new THREE.Vector3()):center;perspective.position.set(selected?target.x+1.5:center.x,1.6,selected?target.z+1.8:bounds.max.z-.8);perspective.lookAt(target);}}
      resize();if(orbit.enabled)orbit.update();
      if(p.mode==='plan')p.onPlanCenter?.([center.x,-center.z]);
    }
    const planAt=(x:number,y:number)=>{const r=element.getBoundingClientRect();return planPosition(camera,x-r.left,y-r.top,r.width,r.height);};
    new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(props.url,gltf=>{if(disposed){dispose(gltf.scene);return;}world.add(gltf.scene);assembly=assemble(gltf.scene,live.current.design);
      const meshes:THREE.Mesh[]=[];gltf.scene.traverse(o=>{if(o instanceof THREE.Mesh)meshes.push(o);});
      for(const mesh of meshes){mesh.castShadow=true;mesh.receiveShadow=true;const edge=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry,35),new THREE.LineBasicMaterial({color:0x47594e,transparent:true,opacity:.85}));edge.userData.planOutline=true;mesh.add(edge);outlines.push(edge);}
      runtime.current={assembly,refresh,setup,planAt};setup();setMessage('');},undefined,()=>setMessage('模型載入失敗，請重新開啟已保存設計。'));
    const observer=new ResizeObserver(resize);observer.observe(element);
    function highlight(){if(!assembly)return;const p=live.current;const o=p.mode==='object'&&p.child?assembly.parts.get(p.child):assembly.groups.get(p.selected);if(o&&visible(o)){box.visible=true;box.box.setFromObject(o);}else box.visible=false;}
    transform.addEventListener('dragging-changed',e=>{dragging=!!e.value;orbit.enabled=!dragging&&live.current.mode!=='walk';if(dragging)wasTransform=true;else if(assembly&&transform.object){const id=transform.object.userData.group_id;const delta=transform.object.position.clone().sub(assembly.bases.get(id)!);live.current.onMove(id,[delta.x,-delta.z,delta.y]);}});
    transform.addEventListener('objectChange',highlight);
    const ray=new THREE.Raycaster();
    function pointerDown(e:PointerEvent){element.focus();down=[e.clientX,e.clientY];wasTransform=!!transform.axis;}
    function pointerMove(e:PointerEvent){if(e.buttons===1&&live.current.mode==='walk'&&!live.current.moving&&!dragging){lookWalkCamera(camera,e.movementX,e.movementY);}}
    function pointerUp(e:PointerEvent){if(live.current.pointEditing||(live.current.lightEditing&&live.current.mode==='plan')||!assembly||wasTransform||dragging||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const r=element.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);
      if(live.current.lightEditing){for(const hit of ray.intersectObject(lightingPreview,true)){if(hit.object.userData.lightId){live.current.onLightSelect?.(hit.object.userData.lightId);break;}}return;}
      for(const hit of ray.intersectObject(assembly.root,true)){if(!(hit.object instanceof THREE.Mesh)||!visible(hit.object)||(live.current.mode==='plan'&&hit.point.y>1.3001))continue;let part:THREE.Object3D|null=hit.object;while(part&&!part.userData.studio_id)part=part.parent;let group=part;while(group&&!group.userData.group_id)group=group.parent;if(part&&group){const id=group.userData.group_id;live.current.onSelect(id,live.current.mode==='object'?part.userData.studio_id:undefined);
        const now=performance.now();if(live.current.mode!=='object'&&lastPick.id===id&&now-lastPick.time<380){live.current.onInspect?.(id);lastPick={id:'',time:0};}else lastPick={id,time:now};break;}}
    }
    function wheel(e:WheelEvent){if(live.current.mode==='walk'){e.preventDefault();perspective.fov=THREE.MathUtils.clamp(perspective.fov+e.deltaY*.03,20,95);perspective.updateProjectionMatrix();}}
    const allowed=['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright','shift',' '];
    function keydown(e:KeyboardEvent){if(document.activeElement!==element)return;const key=e.key.toLowerCase();if(allowed.includes(key)){e.preventDefault();keys.add(key);}}
    function keyup(e:KeyboardEvent){keys.delete(e.key.toLowerCase());}
    const blur=()=>keys.clear();element.addEventListener('keydown',keydown);window.addEventListener('keyup',keyup);element.addEventListener('blur',blur);window.addEventListener('blur',blur);
    renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointermove',pointerMove);renderer.domElement.addEventListener('pointerup',pointerUp);renderer.domElement.addEventListener('wheel',wheel,{passive:false});
    function draw(t:number){frame=requestAnimationFrame(draw);const dt=Math.min((t-last)/1000,.05);last=t;if(!element.clientWidth||!element.clientHeight)return;const p=live.current;
      const forward=Number(keys.has('w')||keys.has('arrowup'))-Number(keys.has('s')||keys.has('arrowdown'));
      const sideways=Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('arrowleft'));
      if(p.mode==='plan'&&(forward||sideways)){const delta=new THREE.Vector3(sideways*dt*span,0,-forward*dt*span);camera.position.add(delta);orbit.target.add(delta);}
      if(p.mode==='walk'){moveWalkCamera(camera,forward,sideways,Number(keys.has(' '))-Number(keys.has('shift')),dt);}
      if(orbit.enabled)orbit.update();renderer.render(world,camera);
      if(t-lastLabel>50){lastLabel=t;setPosition(`X ${camera.position.x.toFixed(2)} · Y ${(-camera.position.z).toFixed(2)} · 高 ${camera.position.y.toFixed(2)} m`);
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
    }frame=requestAnimationFrame(draw);
    return()=>{disposed=true;runtime.current=null;cancelAnimationFrame(frame);observer.disconnect();transform.dispose();orbit.dispose();element.removeEventListener('keydown',keydown);element.removeEventListener('blur',blur);window.removeEventListener('keyup',keyup);window.removeEventListener('blur',blur);assembly?.materials.forEach(m=>m.dispose());floorMaterials.forEach((material,mesh)=>{mesh.material=material;});floorPreview.dispose();clearPreview(lightingPreview);dispose(world);renderer.dispose();element.removeChild(renderer.domElement);};
  },[props.url]);
  useEffect(()=>{runtime.current?.refresh();},[props.design,props.selected,props.child,props.moving,props.planContrast,props.lightId,props.softLighting]);
  useEffect(()=>{runtime.current?.setup();},[props.mode,props.mode==='object'?props.selected:'',props.mode==='walk'?JSON.stringify([props.focusPoint?.id,props.focusPoint?.eye]):'',props.mode==='walk'?JSON.stringify(props.focusShot||props.focusPoint?.shots[0]):'',props.previewReset]);
  function dragPoint(e:React.PointerEvent<SVGGElement>){
    const drag=pointDrag.current;if(!drag)return;
    const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;
    drag.xy=[xy[0]+drag.offset[0],xy[1]+drag.offset[1]];
    drag.moved ||= Math.hypot(e.clientX-drag.start[0],e.clientY-drag.start[1])>3;
  }
  return <div className="space-viewport">
    <div ref={host} tabIndex={0} role="application" aria-label="空間操作畫布" className="space-canvas"/>
    {!!selectionLines.length&&<svg className="selection-overlay" aria-label="已選取物件外框">{selectionLines.map((line,i)=><g key={i}><line {...line} className="selection-underlay"/><line {...line} className="selection-dash"/></g>)}</svg>}
    {props.lightEditing&&props.mode==='plan'&&!message&&<svg className="viewpoint-overlay light-overlay" aria-label="光源平面配置">
      {markers.map((p,i)=>{const light=props.design.lighting_setup?.lights.find(l=>l.id===p.id);if(!light)return null;const active=p.id===props.lightId;return <g key={p.id} transform={`translate(${p.x} ${p.y})`}>
        <g role="button" tabIndex={0} aria-label={`光源 ${light.name}`} aria-pressed={active} className={`point-marker light-marker ${active?'active':''} ${light.enabled?'':'off'}`}
          onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();props.onLightSelect?.(p.id);}}}
          onPointerDown={e=>{if(e.button!==0)return;e.stopPropagation();const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;const pos=lightPosition(light,props.design);e.currentTarget.setPointerCapture(e.pointerId);pointDrag.current={id:p.id,offset:[pos[0]-xy[0],pos[1]-xy[1]],xy:[pos[0],pos[1]],start:[e.clientX,e.clientY],moved:false};props.onLightSelect?.(p.id);}}
          onPointerMove={dragPoint} onPointerCancel={()=>{pointDrag.current=null;}}
          onPointerUp={e=>{dragPoint(e);const drag=pointDrag.current;pointDrag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(drag?.moved)props.onLightMove?.(drag.id,drag.xy);}}>
          <circle r="27" className="light-halo"/><circle r="16"/><text textAnchor="middle" dy="4">{String(i+1).padStart(2,'0')}</text><title>{light.name}：拖曳移動光源</title>
        </g><text textAnchor="middle" y="42" className="point-name">{light.name}{light.enabled?'':' · 關閉'}</text>
      </g>;})}
    </svg>}
    {props.pointEditing&&props.mode==='plan'&&!message&&<svg className="viewpoint-overlay" aria-label="觀看點平面配置">
      {props.design.links.map(([a,b])=>{const from=markers.find(p=>p.id===a),to=markers.find(p=>p.id===b);return from&&to?<g key={a+'-'+b}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="point-link"/><text x={(from.x+to.x)/2} y={(from.y+to.y)/2-5} className="link-symbol">↔</text></g>:null;})}
      {markers.map((p,i)=>{const spec=props.design.viewpoints.find(x=>x.id===p.id);const active=p.id===props.pointId;return <g key={p.id} transform={`translate(${p.x} ${p.y})`}>
        <path d="M 0 0 L 74 -38 A 83 83 0 0 1 74 38 Z" transform={`rotate(${Math.atan2(p.dy,p.dx)*180/Math.PI})`} className={active?'point-cone active':'point-cone'}/>
        <g role="button" tabIndex={0} aria-label={`觀看點 ${String(i+1).padStart(2,'0')} ${spec?.name}`} aria-pressed={active} className="point-marker"
          onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();props.onPointSelect?.(p.id);}}}
          onPointerDown={e=>{if(e.button!==0||!spec)return;e.stopPropagation();const xy=runtime.current?.planAt(e.clientX,e.clientY);if(!xy)return;e.currentTarget.setPointerCapture(e.pointerId);pointDrag.current={id:p.id,offset:[spec.eye[0]-xy[0],spec.eye[1]-xy[1]],xy:[spec.eye[0],spec.eye[1]],start:[e.clientX,e.clientY],moved:false};props.onPointSelect?.(p.id);}}
          onPointerMove={dragPoint} onPointerCancel={()=>{pointDrag.current=null;}}
          onPointerUp={e=>{dragPoint(e);const drag=pointDrag.current;pointDrag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(drag?.moved)props.onPointMove?.(drag.id,drag.xy);}}>
          <circle r="18" fill={active?'#2b5144':'#fffef9'}/><text textAnchor="middle" dy="4" fill={active?'white':'#2b5144'}>{String(i+1).padStart(2,'0')}</text><title>{spec?.name}：拖曳移動觀看點</title>
        </g><text textAnchor="middle" y="35" className="point-name">{spec?.name}</text>
      </g>;})}
    </svg>}
    {message&&<div className="viewer-message">{message}</div>}
    <span className="camera-position" aria-live="off">{position}</span>
    <span className="viewer-help">{props.mode==='plan'?(props.lightEditing?'拖曳光源調整位置 · 家具鎖定 · 滾輪縮放':props.pointEditing?'拖曳圓點調整位置 · 拖曳空白處平移 · 滾輪縮放':'WASD／方向鍵平移 · 滾輪縮放 · 點選物件 · 雙擊單物件展示'):props.mode==='walk'?'W/S 前後 · A/D／左右鍵水平平移 · 空白上升／Shift 下降 · 拖曳看四周 · 滾輪縮放':'拖曳繞物件旋轉 · 滾輪縮放 · 點選子物件'}<br/>{props.pointEditing&&props.mode==='walk'?'即時 3D 預覽，尚未渲染；預覽移動不修改觀看點。':'點一下畫布後使用鍵盤'}{props.moving?' · 拖曳彩色軸或平面移動整件物件':''}</span>
  </div>;
}
function dispose(root:THREE.Object3D){root.traverse(o=>{if(o instanceof THREE.Mesh||o instanceof THREE.Line){o.geometry.dispose();const materials=Array.isArray(o.material)?o.material:[o.material];materials.forEach(m=>{Object.values(m).forEach(v=>{if(v instanceof THREE.Texture)v.dispose();});m.dispose();});}});}
