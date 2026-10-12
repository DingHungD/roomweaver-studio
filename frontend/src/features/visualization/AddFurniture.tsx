import {useRef,useState} from 'react';
import {api} from './api';
import type {ConceptFurniture,Scene} from './api';
type Item={name:string;size:[number,number,number]};
export default function AddFurniture({scene,busy,getCenter,onAdd}:{scene:Scene;busy:boolean;getCenter:()=>[number,number];onAdd:(f:ConceptFurniture,position:[number,number,number])=>void}){
  const [catalog,setCatalog]=useState<Record<string,Item>>({}),[asset,setAsset]=useState('chair'),[name,setName]=useState('椅子'),[size,setSize]=useState<[number,number,number]>([.5,.5,.8]),[position,setPosition]=useState<[number,number,number]>([0,0,0]),[pending,setPending]=useState(false),[error,setError]=useState('');const lock=useRef(false);
  async function open(){if(Object.keys(catalog).length)return;try{const c=await api<Record<string,Item>>('/concept-furniture');setCatalog(c);setSize(c.chair.size);setPosition([...getCenter(),0]);}catch(e){setError((e as Error).message);}}
  return <details onToggle={e=>{if(e.currentTarget.open)void open();}}><summary>＋ 新增概念家具</summary><p>先確認占位與動線；這是可調整的概念模型，不是商品。加入後會選取家具，可用移動模式定位，再保存。</p><fieldset disabled={busy||pending} style={{border:0,padding:0}}>
    <label>家具類型<select value={asset} onChange={e=>{setAsset(e.target.value);setName(catalog[e.target.value].name);setSize(catalog[e.target.value].size);}}>{Object.entries(catalog).map(([id,v])=><option key={id} value={id}>{v.name}</option>)}</select></label>
    <label>名稱<input maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></label>
    <div className="coordinates">{['寬','深','高'].map((label,i)=><label key={label}>{label}（m）<input type="number" min={.2} max={5} step={.05} value={size[i]} onChange={e=>setSize(size.map((v,j)=>i===j?Number(e.target.value):v) as typeof size)}/></label>)}</div>
    <div className="coordinates">{['X','Y','Z'].map((label,i)=><label key={label}>位置 {label}（m）<input type="number" step={.1} value={position[i]} onChange={e=>setPosition(position.map((v,j)=>i===j?Number(e.target.value):v) as typeof position)}/></label>)}</div>
    <button type="button" onClick={()=>{const p=scene.viewpoints[0]?.eye;if(p)setPosition([p[0],p[1],0]);}}>放在第一觀看點附近</button>
    <button type="button" disabled={!name.trim()||!Object.keys(catalog).length||size.some(v=>v<.2||v>5)||position.some(v=>!Number.isFinite(v)||Math.abs(v)>10000)} onClick={async()=>{if(lock.current)return;lock.current=true;setPending(true);setError('');try{const f=await api<ConceptFurniture>('/concept-furniture','POST',{id:'concept-'+crypto.randomUUID().replaceAll('-',''),name,asset,size});onAdd(f,position);}catch(e){setError((e as Error).message);}finally{lock.current=false;setPending(false);}}}>加入家具</button>
    </fieldset>{error&&<p role="alert">{error}</p>}</details>;
}
