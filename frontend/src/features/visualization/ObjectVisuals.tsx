import {createContext,useContext,useEffect,useMemo,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {assemble,applyDesign} from './assemblyScene';
import {fileUrl} from './api';
import type {Scene} from './api';

type Visual={image:string;boxes:{id:string;x:number;y:number;w:number;h:number}[];view:string};
// One lazy renderer per open dialog, not one WebGL context per card. No animation loop.
class Pictures {
  private cache=new Map<string,Visual>();
  private data?:ReturnType<Pictures['load']>;
  private renderer?:THREE.WebGLRenderer;
  private closed=false;
  constructor(private project:string,private design:Scene){}
  private async load(){
    const gltf=await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(fileUrl(this.project,this.design.model_id,'model.glb'));
    const scene=new THREE.Scene();scene.background=new THREE.Color('#eef0e8');scene.add(gltf.scene);
    const assembly=assemble(gltf.scene,this.design);applyDesign(assembly,this.design);
    gltf.scene.traverse(o=>{if(o instanceof THREE.Light)o.visible=false;});
    scene.add(new THREE.HemisphereLight(0xffffff,0x8d9287,2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(3,8,4);scene.add(light);
    const boxes=[...assembly.groups].filter(([,g])=>g.visible).map(([id,g])=>({id,box:new THREE.Box3().setFromObject(g)})).filter(b=>!b.box.isEmpty());
    return {scene,assembly,boxes};
  }
  async get(id:string):Promise<Visual>{
    if(this.closed)throw new Error('預覽已關閉');
    if(this.cache.has(id))return this.cache.get(id)!;
    this.data??=this.load();const {scene,assembly,boxes}=await this.data;
    if(this.closed)throw new Error('預覽已關閉');
    const target=assembly.groups.get(id),entry=boxes.find(b=>b.id===id);if(!target||!entry)throw new Error('此物件沒有可顯示的幾何');
    this.renderer??=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    const renderer=this.renderer;renderer.setSize(224,160,false);renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1;
    for(const [key,g] of assembly.groups)g.visible=key===id;
    const size=entry.box.getSize(new THREE.Vector3()),center=entry.box.getCenter(new THREE.Vector3());
    const span=Math.max(size.x,size.y,size.z,.1)*1.7;
    const camera=new THREE.OrthographicCamera(-span*.7,span*.7,span*.5,-span*.5,.01,span*20);
    camera.position.copy(center).add(new THREE.Vector3(1,.85,1.2).normalize().multiplyScalar(span*3));camera.lookAt(center);
    renderer.render(scene,camera);
    const interior=boxes.filter(b=>!/(exterior|outdoor|sky|tree|landscape|窗外|室外|天空)/i.test(this.design.groups.find(g=>g.id===b.id)?.name||''));
    const selected=[...interior.filter(b=>b.id!==id),entry];const extent=new THREE.Box3();selected.forEach(b=>extent.union(b.box));
    const result={image:renderer.domElement.toDataURL('image/png'),boxes:selected.map(({id,box})=>({id,x:box.min.x,y:box.min.z,w:Math.max(.04,box.max.x-box.min.x),h:Math.max(.04,box.max.z-box.min.z)})),view:`${extent.min.x-.3} ${extent.min.z-.3} ${extent.max.x-extent.min.x+.6} ${extent.max.z-extent.min.z+.6}`};
    this.cache.set(id,result);return result;
  }
  dispose(){this.closed=true;this.renderer?.dispose();this.renderer?.forceContextLoss();this.cache.clear();void this.data?.then(({scene})=>{const materials=new Set<THREE.Material>(),textures=new Set<THREE.Texture>();scene.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.dispose();for(const m of Array.isArray(o.material)?o.material:[o.material])materials.add(m);}});for(const m of materials){for(const value of Object.values(m))if(value instanceof THREE.Texture)textures.add(value);m.dispose();}textures.forEach(t=>t.dispose());}).catch(()=>{});}
}
const Context=createContext<Pictures|null>(null);
export function ObjectVisualsProvider({project,scene,children}:{project:string;scene:Scene;children:ReactNode}){
  const pictures=useMemo(()=>new Pictures(project,scene),[project,scene]);useEffect(()=>()=>pictures.dispose(),[pictures]);
  return <Context.Provider value={pictures}>{children}</Context.Provider>;
}
export function ObjectVisual({id,name,onInspect}:{id:string;name:string;onInspect?:()=>void}){
  const pictures=useContext(Context),element=useRef<HTMLDivElement>(null);
  const [visual,setVisual]=useState<Visual|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;setVisual(null);setError('');const observer=new IntersectionObserver(entries=>{if(!entries.some(e=>e.isIntersecting)||!pictures)return;observer.disconnect();void pictures.get(id).then(v=>{if(active)setVisual(v);}).catch(e=>{if(active)setError(e.message);});});if(element.current)observer.observe(element.current);return()=>{active=false;observer.disconnect();};},[pictures,id]);
  return <div className="object-visual" ref={element}>{visual?<><figure><img src={visual.image} alt={`${name}目前模型外觀`}/><figcaption>目前外觀</figcaption></figure><figure><svg viewBox={visual.view} role="img" aria-label={`${name}平面位置`}><title>{name}平面位置（橘色）</title>{visual.boxes.map(b=><rect key={b.id} x={b.x} y={b.y} width={b.w} height={b.h} fill={b.id===id?'#de8132':'#d6ddce'} fillOpacity={b.id===id?.85:.35} stroke={b.id===id?'#a84812':'#879383'} strokeWidth="1" vectorEffect="non-scaling-stroke"/>)}</svg><figcaption>橘色為平面位置</figcaption></figure></>:<small>{error||'捲動至此時載入外觀與位置…'}</small>}{onInspect&&<button type="button" onClick={onInspect}>在主畫面查看</button>}</div>;
}
