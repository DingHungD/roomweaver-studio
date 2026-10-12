import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {ConceptFurniture,Scene} from './api';
import {decorAssets} from './placementArea';
import type {PlacementArea} from './placementArea';
export type Addition={furniture:ConceptFurniture;position:[number,number,number];prompt:string;url:string;room:string|null;action:'concept'|'prompt'|'link'};
type Item={name:string;size:[number,number,number]};
export default function AddFurniture({scene,busy,kind,area,drawing,getCenter,onDraw,onCancel,onAdd}:{scene:Scene;busy:boolean;kind:'furniture'|'decor';area:PlacementArea|null;drawing:boolean;getCenter:()=>[number,number];onDraw:()=>void;onCancel:()=>void;onAdd:(value:Addition)=>Promise<void>}){
 const label=kind==='decor'?'裝飾物':'家具元件';
 const initial=kind==='decor'?'vase':'chair';
 const [catalog,setCatalog]=useState<Record<string,Item>>({}),[asset,setAsset]=useState(initial),[name,setName]=useState(kind==='decor'?'花瓶與花':'椅子');
 const [size,setSize]=useState<[number,number,number]>(kind==='decor'?[.18,.18,.3]:[.5,.5,.85]),[position,setPosition]=useState<[number,number,number]>([...getCenter(),0]);
 const [prompt,setPrompt]=useState(''),[url,setUrl]=useState(''),[room,setRoom]=useState(''),[action,setAction]=useState<'concept'|'prompt'|'link'>('prompt');
 const [pending,setPending]=useState(false),[error,setError]=useState('');const lock=useRef(false);
 useEffect(()=>{let alive=true;api<Record<string,Item>>('/concept-furniture').then(c=>{if(alive)setCatalog(c);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[]);
 useEffect(()=>{if(area){setSize(s=>[...area.size,s[2]]);setPosition([...area.center,area.height]);}},[area]);
 const min=kind==='decor'?.005:.2;
 const invalid=size.some(v=>!Number.isFinite(v)||v<min||v>5)||position.some(v=>!Number.isFinite(v)||Math.abs(v)>10000);
 return <section className="manual-addition" aria-label={`新增${label}設定`}><h3>新增{label}</h3><p>在左側 2D 拖曳框選範圍，再確認尺寸、高度與模型來源。可改畫或取消，尚未加入前不會修改設計。</p>
 <fieldset disabled={busy||pending} style={{border:0,padding:0}}>
 <button onClick={onDraw}>{drawing?'正在框選範圍…':area?'重新框選範圍':'在 2D 框選範圍'}</button><button onClick={()=>setPosition([...getCenter(),0])}>使用畫面中心</button>
 {area&&<p role="status">已框選 {area.size[0].toFixed(2)} × {area.size[1].toFixed(2)} m</p>}
 <label>{label}類型<select value={asset} onChange={e=>{const a=e.target.value;setAsset(a);setName(catalog[a].name);setSize(area?[...area.size,catalog[a].size[2]]:catalog[a].size);}}>{Object.entries(catalog).filter(([id])=>kind==='decor'?decorAssets.has(id):!decorAssets.has(id)&&!['floor_lamp','ceiling_light'].includes(id)).map(([id,v])=><option key={id} value={id}>{v.name}</option>)}</select></label>
 <label>名稱<input value={name} maxLength={100} onChange={e=>setName(e.target.value)}/></label>
 <div className="coordinates">{['寬','深','高'].map((n,i)=><label key={n}>{n}（m）<input aria-label={`新增${n}`} type="number" min={min} max={5} step={.01} value={size[i]} onChange={e=>setSize(size.map((v,j)=>i===j?Number(e.target.value):v) as typeof size)}/></label>)}</div>
 <label>放置高度（底部 m）<input aria-label="新增放置高度" type="number" step={.01} value={position[2]} onChange={e=>setPosition([position[0],position[1],Number(e.target.value)])}/></label>
 <small>框選中心若有可見表面，會帶入其高度；桌面、地板或層架仍請核對。這不是碰撞或動線驗收。</small>
 <details><summary>精確平面位置</summary>{['X','Y'].map((n,i)=><label key={n}>{n}（m）<input type="number" step={.01} value={position[i]} onChange={e=>setPosition(position.map((v,j)=>i===j?Number(e.target.value):v) as typeof position)}/></label>)}</details>
 <label>所屬空間<select value={room} onChange={e=>setRoom(e.target.value)}><option value="">待確認</option>{scene.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
 <label>建立方式<select aria-label="建立方式" value={action} onChange={e=>setAction(e.target.value as typeof action)}><option value="prompt">描述需求，請 Agent 找模型</option><option value="link">指定 BlenderKit 模型連結</option><option value="concept">先加入概念占位</option></select></label>
 <label>需求描述<textarea aria-label="新增元件需求" maxLength={1800} value={prompt} placeholder={kind==='decor'?'例如：透明玻璃花瓶、少量白花':'例如：雙人布沙發、米色、可拆洗'} onChange={e=>setPrompt(e.target.value)}/></label>
 {action==='link'&&<label>BlenderKit 模型網址<input aria-label="新增模型網址" type="url" value={url} maxLength={2000} placeholder="https://www.blenderkit.com/asset-gallery-detail/…/" onChange={e=>setUrl(e.target.value)}/></label>}
 <p>{action==='concept'?'先保存可移動、旋轉、刪除的占位，之後可配對模型。':action==='prompt'?'保存元件後使用 Codex 搜尋候選，會使用模型額度；選定候選後才下載。':'保存元件並查核指定模型，不呼叫 Agent；核對來源及授權後下載套用。只支援 BlenderKit 模型頁連結。'}</p>
 {invalid&&<p role="alert">寬、深、高需介於 {min}～5 m；請縮小框選範圍或調整數值。</p>}
 <button className="primary" disabled={invalid||!name.trim()||!catalog[asset]||(action==='prompt'&&!prompt.trim())||(action==='link'&&!url.trim())} onClick={async()=>{if(lock.current)return;lock.current=true;setPending(true);setError('');try{if(action==='link'){const u=new URL(url);if(u.protocol!=='https:'||!['blenderkit.com','www.blenderkit.com'].includes(u.hostname)||!/^\/asset-gallery-detail\/[a-f0-9-]{36}\/?$/i.test(u.pathname))throw new Error('請貼上 BlenderKit 單一模型頁網址');}const f=await api<ConceptFurniture>('/concept-furniture','POST',{id:'concept-'+crypto.randomUUID().replaceAll('-',''),name:name.trim(),asset,size});await onAdd({furniture:f,position,prompt,url:action==='link'?url:'',room:room||null,action});}catch(e){setError((e as Error).message);}finally{lock.current=false;setPending(false);}}}>{pending?'處理中…':action==='concept'?`加入${label}`:action==='prompt'?'新增並搜尋模型':'新增並查核連結'}</button>
 <button onClick={onCancel}>取消新增</button></fieldset>{error&&<p role="alert">{error}</p>}</section>;
}
