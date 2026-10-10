import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import type {Viewpoint,Scene} from './api';
import {assemble,applyDesign} from './assemblyScene';
import type {AssemblyRuntime} from './assemblyScene';

export default function ModelViewer({url,selected,onSelect,points,focus,design}:{url:string;selected:string;onSelect:(id:string)=>void;points:Viewpoint[];focus?:Viewpoint;design?:Scene}) {
  const host=useRef<HTMLDivElement>(null);
  const assembled=useRef<AssemblyRuntime|null>(null);const latest=useRef(design);latest.current=design;
  const callback=useRef(onSelect);callback.current=onSelect;
  const runtime=useRef<{scene:THREE.Scene;camera:THREE.PerspectiveCamera;controls:OrbitControls;model:THREE.Object3D|null;box:THREE.BoxHelper|null;markers:THREE.Group}|null>(null);
  const [message,setMessage]=useState('正在載入真實模型…');
  useEffect(()=>{
    const element=host.current!;
    const scene=new THREE.Scene();scene.background=new THREE.Color('#e8e8e0');
    const camera=new THREE.PerspectiveCamera(50,1,.03,300);camera.position.set(14,14,15);
    let renderer:THREE.WebGLRenderer;
    try {renderer=new THREE.WebGLRenderer({antialias:true});}catch {setMessage('此裝置無法啟用 3D 顯示，仍可使用物件清單。');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.4;
    element.appendChild(renderer.domElement);
    const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
    scene.add(new THREE.HemisphereLight(0xffffff,0x777766,2.2));const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(10,20,10);scene.add(sun);
    const markers=new THREE.Group();scene.add(markers);
    runtime.current={scene,camera,controls,model:null,box:null,markers};
    let disposed=false;let frame=0;
    new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(url,gltf=>{if(disposed){dispose(gltf.scene);return;}scene.add(gltf.scene);runtime.current!.model=gltf.scene;if(latest.current){assembled.current=assemble(gltf.scene,latest.current);applyDesign(assembled.current,latest.current);}
      const bounds=new THREE.Box3().setFromObject(gltf.scene);const center=bounds.getCenter(new THREE.Vector3());controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(10,13,15));setMessage('');},undefined,()=>setMessage('模型載入失敗，請確認匯入工作結果。'));
    const resize=new ResizeObserver(()=>{const {width,height}=element.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/Math.max(height,1);camera.updateProjectionMatrix();});resize.observe(element);
    const ray=new THREE.Raycaster();let down=[0,0];
    const pointerDown=(e:PointerEvent)=>{down=[e.clientX,e.clientY];};
    const click=(e:PointerEvent)=>{if(Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const rect=element.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
      const model=runtime.current?.model;if(!model)return;for(const hit of ray.intersectObject(model,true)){let object:THREE.Object3D|null=hit.object;while(object&&!object.userData.studio_id)object=object.parent;if(object?.userData.studio_id){callback.current(object.userData.studio_id);break;}}};
    renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointerup',click);
    const draw=()=>{frame=requestAnimationFrame(draw);controls.update();renderer.render(scene,camera);};draw();
    return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();controls.dispose();dispose(scene);renderer.dispose();element.removeChild(renderer.domElement);runtime.current=null;};
  },[url]);
  useEffect(()=>{const r=runtime.current;if(!r?.model)return;if(r.box){r.scene.remove(r.box);r.box.geometry.dispose();(r.box.material as THREE.Material).dispose();r.box=null;}
    r.model.traverse(object=>{if(object.userData.studio_id===selected){r.box=new THREE.BoxHelper(object,0xd48d45);r.scene.add(r.box);}});
  },[selected,message]);
  useEffect(()=>{const r=runtime.current;if(!r)return;dispose(r.markers);r.markers.clear();points.forEach(p=>{const marker=new THREE.Mesh(new THREE.SphereGeometry(.075,12,8),new THREE.MeshBasicMaterial({color:0xe49b42,depthTest:false}));marker.position.set(p.eye[0],p.eye[2],-p.eye[1]);marker.renderOrder=5;r.markers.add(marker);});},[points,message]);
  useEffect(()=>{const r=runtime.current;if(!r)return;if(!focus){if(r.model){const center=new THREE.Box3().setFromObject(r.model).getCenter(new THREE.Vector3());r.controls.target.copy(center);r.camera.position.copy(center).add(new THREE.Vector3(10,13,15));}return;}r.camera.position.set(focus.eye[0],focus.eye[2],-focus.eye[1]);const yaw=(focus.shots[0]?.yaw||0)*Math.PI/180;const pitch=(focus.shots[0]?.pitch||0)*Math.PI/180;r.controls.target.copy(r.camera.position).add(new THREE.Vector3(Math.cos(yaw)*Math.cos(pitch),Math.sin(pitch),-Math.sin(yaw)*Math.cos(pitch)));r.camera.setFocalLength(focus.shots[0]?.lens||24);r.camera.updateProjectionMatrix();},[focus,message]);
  useEffect(()=>{if(assembled.current&&design)applyDesign(assembled.current,design);},[design,message]);
  return <div className="studio-model"><div ref={host} className="studio-canvas"/>{message&&<div className="viewer-message">{message}</div>}<span className="viewer-help">拖曳旋轉 · 滾輪縮放 · 點選物件　／　預覽不代表最終渲染</span></div>;
}
function dispose(object:THREE.Object3D){object.traverse(o=>{if(o instanceof THREE.Mesh||o instanceof THREE.Line){o.geometry.dispose();(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>{Object.values(m).forEach(v=>{if(v instanceof THREE.Texture)v.dispose();});m.dispose();});}});}

export function Panorama({url}:{url:string}) {
  const host=useRef<HTMLDivElement>(null);
  useEffect(()=>{const element=host.current!;const scene=new THREE.Scene();const camera=new THREE.PerspectiveCamera(70,1,.01,20);camera.position.set(.001,0,0);
    const renderer=new THREE.WebGLRenderer({antialias:true});element.appendChild(renderer.domElement);const controls=new OrbitControls(camera,renderer.domElement);controls.enableZoom=false;controls.enablePan=false;controls.rotateSpeed=-.4;
    const geometry=new THREE.SphereGeometry(10,64,32);geometry.scale(-1,1,1);const texture=new THREE.TextureLoader().load(url);texture.colorSpace=THREE.SRGBColorSpace;const material=new THREE.MeshBasicMaterial({map:texture});scene.add(new THREE.Mesh(geometry,material));
    const observer=new ResizeObserver(()=>{renderer.setSize(element.clientWidth,element.clientHeight);camera.aspect=element.clientWidth/element.clientHeight;camera.updateProjectionMatrix();});observer.observe(element);
    let frame=0;const draw=()=>{frame=requestAnimationFrame(draw);controls.update();renderer.render(scene,camera);};draw();
    return()=>{cancelAnimationFrame(frame);observer.disconnect();controls.dispose();geometry.dispose();material.dispose();texture.dispose();renderer.dispose();element.removeChild(renderer.domElement);};
  },[url]);return <div ref={host} className="panorama-view"/>;
}
