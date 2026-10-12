import {useEffect,useState} from 'react';
import {api,fileUrl} from './api';
import type {Scene,LightingSetup,StudioLight,Job} from './api';
import {bindLight,lightPosition,placeLight} from './lightGeometry';
const initial:LightingSetup={enabled:false,mode:'existing',exposure:0,auto_adjust:true,agent_review:false,lights:[]};
export function LightingRun({project,jobId,onAdopt}:{project:string;jobId:string;onAdopt:(setup:LightingSetup,revision:string)=>void}){
  const [data,setData]=useState<{revision:string;attempts:{name:string;images:string[];status:string;review?:{reason:string;warnings?:string[]}}[];lighting_setup?:LightingSetup}|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{let alive=true;async function read(){try{const d=await api<NonNullable<typeof data>>(`/jobs/${jobId}/lighting-status`);if(alive)setData(d);}catch(e){if(alive)setError((e as Error).message);}}void read();const timer=setInterval(read,5000);return()=>{alive=false;clearInterval(timer);};},[jobId]);
  if(!data?.attempts.length)return error?<p>{error}</p>:null;
  return <details className="lighting-panel"><summary>照明試圖與調整紀錄（{data.attempts.length} 輪）</summary>{data.attempts.map(a=><section key={a.name}><h4>{a.name} · {a.status}</h4><p>{a.review?.reason||'本機影像檢查；尚無 Agent 判圖結論。'}</p>{a.review?.warnings?.map((w,i)=><p key={i}>待確認：{w}</p>)}<div className="lighting-probes">{a.images.map(name=><a key={name} href={fileUrl(project,jobId,name)} target="_blank" rel="noreferrer"><img src={fileUrl(project,jobId,name)} alt={name}/></a>)}</div></section>)}{data.lighting_setup&&<button onClick={()=>onAdopt(data.lighting_setup!,data.revision)}>將本次有效照明帶回編輯</button>}<p>試圖僅供光影與構圖確認，正式出圖仍需人工判圖。</p></details>;
}

export default function LightingPanel({project,revision,scene,dirty,busy,onChange,onSave,selected:controlledSelected,onSelect,center}:{selected?:string;onSelect?:(id:string)=>void;center?:[number,number];project:string;revision:string|null;scene:Scene;dirty:boolean;busy:boolean;onChange:(s:Scene)=>void;onSave:()=>Promise<string|null|undefined>}){
  const setup=scene.lighting_setup||initial;
  const [localSelected,setLocalSelected]=useState(''),[job,setJob]=useState<Job|null>(null),[message,setMessage]=useState(''),[starting,setStarting]=useState(false);
  const selected=controlledSelected??localSelected;const setSelected=onSelect||setLocalSelected;
  const light=setup.lights.find(l=>l.id===selected);const running=starting||!!job&&['queued','running'].includes(job.status);
  function edit(fn:(next:LightingSetup)=>void){const next=structuredClone(setup);fn(next);onChange({...scene,lighting_setup:next});}
  function changeLight(patch:Partial<StudioLight>){edit(s=>{Object.assign(s.lights.find(l=>l.id===selected)!,patch);});}
  useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let alive=true;const timer=setInterval(async()=>{try{const next=await api<Job>(`/jobs/${job.id}`);if(!alive)return;setJob(next);if(next.status==='completed'&&next.result?.lighting_setup){if(next.source_revision!==revision||dirty){setMessage('配置期間設計已改變，請保存後重新配置；未套用過期提案。');return;}onChange({...scene,lighting_setup:next.result.lighting_setup});setMessage('已載入可編輯照明提案，請保存。'+(next.result.notes||[]).join(' '));}else if(['failed','interrupted','cancelled'].includes(next.status))setMessage(next.error||'照明配置已停止');}catch(e){if(alive)setMessage((e as Error).message);}},1500);return()=>{alive=false;clearInterval(timer);};},[job?.id,job?.status,revision,dirty,scene]);
  async function configure(){setStarting(true);setMessage('');try{const rev=dirty?await onSave():revision;if(!rev)throw new Error('請先保存設計');setJob(await api<Job>(`/projects/${project}/lighting`,'POST',{base_revision:rev,operation_id:crypto.randomUUID().replaceAll('-',''),quality:'preview'}));}catch(e){setMessage((e as Error).message);}finally{setStarting(false);}}
  return <section className="lighting-panel" aria-label="照明設定"><div className="section-heading"><h2>照明與光影</h2><button className="primary" disabled={busy||running} onClick={()=>void configure()}>{running?'盤點光源中…':'盤點／恢復原有光源'}</button></div>
    <p>上方可新增室外日光及 BlenderKit 燈具。此處可盤點原模型光源；已登記同案照明來源時可恢復。預設以本機檢查試圖，最多調整三輪；啟用 Codex 判讀後才會呼叫雲端模型。</p>
    <p role="status">{message}</p><fieldset disabled={busy||running}>
    <label className="inline-check"><input type="checkbox" checked={setup.enabled} onChange={e=>edit(s=>{s.enabled=e.target.checked;})}/>使用這份照明設定</label>
    <div className="render-options"><label>光線情境<select value={setup.mode} onChange={e=>edit(s=>{s.mode=e.target.value as LightingSetup['mode'];})}><option value="existing">保留原環境</option><option value="day">日間柔和環境</option><option value="indoor">只有室內燈</option></select></label><label>曝光（EV）<input type="number" min="-3" max="3" step="0.25" value={setup.exposure} onChange={e=>edit(s=>{s.exposure=Number(e.target.value);})}/></label></div>
    <label className="inline-check"><input type="checkbox" checked={setup.auto_adjust} onChange={e=>edit(s=>{s.auto_adjust=e.target.checked;})}/>允許自動調整未鎖定光源，最多三輪</label>
    <label className="inline-check"><input type="checkbox" checked={setup.agent_review} onChange={e=>edit(s=>{s.agent_review=e.target.checked;})}/>使用 Codex 判讀試圖（雲端處理試圖與光源設定，使用訂閱額度）</label>
    <select aria-label="照明光源" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">選擇光源微調 · {setup.lights.length} 盞</option>{setup.lights.map(l=><option key={l.id} value={l.id}>{l.locked?'🔒 ':''}{l.name}{l.origin==='proposal'?' · 建議燈位':''}</option>)}</select>
    {light&&<div className="lighting-controls"><label>光源名稱<input value={light.name} onChange={e=>changeLight({name:e.target.value})}/></label><label className="inline-check"><input type="checkbox" checked={light.enabled} onChange={e=>changeLight({enabled:e.target.checked})}/>開燈</label><label className="inline-check"><input type="checkbox" checked={light.locked} onChange={e=>changeLight({locked:e.target.checked})}/>鎖定，不讓 Agent 修改</label>
      <label>亮度（渲染器功率，非燈泡耗電瓦數）<input type="number" min="0" max={light.kind==='SUN'?10:5000} step="1" value={light.power} onChange={e=>changeLight({power:Number(e.target.value)})}/></label>
      <label>光色<select value="" onChange={e=>changeLight({color:JSON.parse(e.target.value)})}><option value="" disabled>目前 RGB {light.color.map(v=>v.toFixed(2)).join(' / ')}</option><option value="[1,0.72,0.45]">暖光</option><option value="[1,0.9,0.78]">自然白</option><option value="[0.85,0.92,1]">冷白</option></select></label>
      <label>光源大小／陰影柔和（m）<input type="number" min="0.01" max="10" step="0.1" value={Number(light.size.toFixed(3))} onChange={e=>changeLight({size:Number(e.target.value)})}/></label>
      <label>綁定燈具<select value={light.group_id||''} onChange={e=>changeLight(bindLight(light,scene,e.target.value||null))}><option value="">獨立光源</option>{scene.groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
      <p>綁定時保持燈位，之後跟隨物件移動；刪除物件會一起停用光源。</p>
      <div className="coordinates">{['X','Y','Z'].map((axis,i)=><label key={axis}>{axis} 位置（m）<input type="number" step="0.1" value={Number(lightPosition(light,scene)[i].toFixed(3))} onChange={e=>{const p=lightPosition(light,scene);p[i]=Number(e.target.value);changeLight(placeLight(light,scene,p));}}/></label>)}</div>
      <div className="coordinates">{['X','Y','Z'].map((axis,i)=><label key={axis}>{axis} 旋轉（°）<input type="number" step="5" value={Math.round(light.rotation[i]*180/Math.PI)} onChange={e=>{const p=[...light.rotation] as [number,number,number];p[i]=Number(e.target.value)*Math.PI/180;changeLight({rotation:p});}}/></label>)}</div>
      <button onClick={()=>{edit(s=>{s.lights=s.lights.filter(l=>l.id!==selected);});setSelected('');}}>移除此光源</button>
    </div>}</fieldset><p className="muted">切換「3D 畫面」可即時查看近似光影；請到「整合輸出」低解析出圖，確認實際照明。日間模式為柔和環境提案，並非實際日照分析。</p></section>;
}
