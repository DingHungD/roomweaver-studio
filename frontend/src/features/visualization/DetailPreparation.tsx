import {useEffect,useState} from 'react';
import {api} from './api';
import type {Job,Scene} from './api';

export default function DetailPreparation({project,revision,dirty,scene,model,brief,onBrief,onPreview}:{project:string;revision:string|null;dirty:boolean;scene:Scene;model:string;brief:string;onBrief:(s:string)=>void;onPreview:(id:string)=>void}){
 const [all,setAll]=useState(true),[openings,setOpenings]=useState(true);
 const [open,setOpen]=useState(true),[point,setPoint]=useState(scene.viewpoints[0]?.id||''),[job,setJob]=useState<Job|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let active=true;setJob(null);setError('');void api<Job|null>(`/projects/${project}/realism-prepare`).then(j=>{if(active)setJob(j);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[project,revision]);
 useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let active=true;const timer=setInterval(()=>{void api<Job>(`/jobs/${job.id}`).then(j=>{if(active)setJob(j);}).catch(e=>{if(active)setError(e.message);});},1500);return()=>{active=false;clearInterval(timer);};},[job?.id,job?.status]);
 async function prepare(){setBusy(true);setError('');try{setJob(await api<Job>(`/projects/${project}/realism-prepare`,'POST',{base_revision:revision,operation_id:crypto.randomUUID().replaceAll('-',''),point_id:point,brief,realism_all:all,prepare_openings:openings,model:model||null}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const running=busy||!!job&&['queued','running'].includes(job.status);
 return <details open={open} onToggle={e=>setOpen(e.currentTarget.open)} className="lighting-panel"><summary>模型細節準備 · 先核對尺寸再找素材</summary>
 <p>門窗是建築構件，在門頁依原有洞口補框、門片與玻璃，不另切洞或改尺寸。新增木質概念門窗，門片先試安全開啟；未知鉸鏈側不視為已確認。自動核對天花、燈具、櫃體使用側與淋浴靠牆，保留尺寸與必要家具。家電與層架也在此準備；雜誌等內容屬裝飾物。只建立未採用的預覽；淋浴替換通過安裝檢查時，會接續附近既有鏡位的低解析試圖與 Agent 看圖。構圖與最終光照留在觀看點及整合輸出核對。</p>
 <label className="inline-check"><input type="checkbox" checked={all} disabled={running} onChange={e=>setAll(e.target.checked)}/>核對全案模型</label><label className="inline-check"><input type="checkbox" checked={openings} disabled={running} onChange={e=>setOpenings(e.target.checked)}/>補齊門窗概念構件（依可追溯洞口）</label>
 <label>預覽起點<select aria-label="模型準備範圍" value={point} disabled={running} onChange={e=>setPoint(e.target.value)}>{scene.viewpoints.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
 <label>既有確認紀錄<textarea aria-label="模型準備確認紀錄" disabled={running} maxLength={12000} value={brief} onChange={e=>onBrief(e.target.value)} placeholder="物件完整名稱、已確認層架用途與微波爐／咖啡機／雜誌需求；沿用原尺寸。"/></label>
 <div className="object-actions"><button disabled={running||dirty||!revision||!point} onClick={()=>void prepare()}>準備模型細節預覽</button>{job?.status==='completed'&&<button onClick={()=>onPreview(job.id)}>在02查看準備結果</button>}</div>
 {dirty&&<p>請先保存目前編輯。</p>}{!point&&<p>請先新增一個觀看點，供準備模型時定位範圍。</p>}
 {job&&<p role="status">{job.status==='completed'?'模型預覽已完成，尚未採用':job.error||job.progress?.current||job.status}</p>}{error&&<p role="alert">{error}</p>}
 </details>;
}
