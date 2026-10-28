import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {Revision,Scene} from './api';
import {fixtureLightingCanApply,fixtureLightingPending} from './fixtureLightingState';
import type {FixtureLightingResult} from './fixtureLightingState';

export default function FixtureLightingPanel(props:{project:string;revision:string|null;model:string;scene:Scene;dirty:boolean;busy:boolean;onSave:()=>Promise<string|null|undefined>;onAccept:(r:Revision)=>void}){
  const {project}=props;
  const [task,setTask]=useState<FixtureLightingResult|null>(null),[working,setWorking]=useState(false),[error,setError]=useState('');
  const [available,setAvailable]=useState(false);
  const latest=useRef(props);latest.current=props;
  const applying=useRef(''),generation=useRef(0);
  useEffect(()=>{
    const serial=++generation.current;setTask(null);setError('');setAvailable(false);applying.current='';
    void api<FixtureLightingResult|null>(`/projects/${project}/fixture-lighting/current`).then(t=>{if(generation.current===serial){setTask(t);setAvailable(true);}}).catch(()=>{if(generation.current===serial)setError('現有燈具配置功能尚未載入；如剛更新程式，請重新啟動 Roomweaver 服務並重新整理頁面。');});
    return ()=>{generation.current++;};
  },[project]);
  useEffect(()=>{
    if(!task||!fixtureLightingPending(task.status))return;
    let live=true,running=false;
    const poll=async()=>{
      if(running)return;running=true;
      try{const next=await api<FixtureLightingResult>(`/projects/${project}/fixture-lighting/${task.id}`);if(live)setTask(next);}
      catch(e){if(live)setError(String(e));}finally{running=false;}
    };
    const timer=setInterval(()=>void poll(),1500);
    return ()=>{live=false;clearInterval(timer);};
  },[project,task?.id,task?.status]);
  useEffect(()=>{
    if(!task||!fixtureLightingCanApply(task,props.revision,props.dirty)||applying.current===task.id)return;
    applying.current=task.id;setWorking(true);
    const original=latest.current.scene,serial=generation.current;
    void api<Revision>(`/projects/${project}/fixture-lighting/${task.id}/apply`,'POST',{base_revision:task.base_revision}).then(r=>{
      if(generation.current!==serial)return;
      setTask(t=>t?{...t,adoption:{revision:r.revision!}}:t);
      if(latest.current.scene!==original||latest.current.dirty||latest.current.revision!==task.base_revision){
        setError('光源結果已保存；畫面另有編輯，請先保留目前編輯再重新開啟已保存設計。');return;
      }
      latest.current.onAccept(r);
    }).catch(e=>{if(generation.current===serial)setError(String(e.message||e));}).finally(()=>{if(generation.current===serial)setWorking(false);});
  },[project,task,props.revision,props.dirty]);
  async function start(){
    setWorking(true);setError('');generation.current++;const serial=generation.current;
    try{
      const original=latest.current.scene;
      const revision=latest.current.dirty?await latest.current.onSave():latest.current.revision;
      if(!revision)throw new Error('請先保存場景');
      if(latest.current.project!==project||latest.current.scene!==original)throw new Error('保存期間有其他編輯，請保存後重新配置');
      const next=await api<FixtureLightingResult>(`/projects/${project}/fixture-lighting`,'POST',{
        base_revision:revision,operation_id:crypto.randomUUID().replaceAll('-',''),model:latest.current.model||null});
      if(generation.current===serial){applying.current='';setTask(next);}
    }catch(e){if(generation.current===serial)setError(String(e instanceof Error?e.message:e));}
    finally{if(generation.current===serial)setWorking(false);}
  }
  const pending=fixtureLightingPending(task?.status);
  const stale=task?.status==='passed'&&!task.adoption&&(props.dirty||task.base_revision!==props.revision);
  return <section className="fixture-lighting-controls" aria-label="依現有燈具建立光源">
    <button disabled={!available||props.busy||working||pending||!props.revision} title="使用所選 Agent 辨認現有燈具，保留既有光源並建立可調整的綁定光源" onClick={()=>void start()}>依現有燈具建立光源</button>
    {(pending||working)&&<span role="status"> {working?'保存光源配置中…':task?.phase||'等待 Agent'} </span>}
    {pending&&task?.status!=='stopping'&&<button onClick={()=>{void api(`/agent/tasks/${task!.id}/stop`,'POST').then(()=>setTask(t=>t?{...t,status:'stopping'}:t)).catch(e=>setError(String(e)));}}>停止配置</button>}
    {!task&&<small> 由 Agent 辨認現有燈具；亮度與色溫為可編輯推定。</small>}
    {stale&&<p role="status">配置結果已保留；目前設計有變更，請保存後重新配置。</p>}
    {(error||task?.error)&&<p role="alert">{error||task?.error}</p>}
    {task&&['stopped','interrupted'].includes(task.status)&&<p>配置已停止，既有光源保留；可重新開始。</p>}
    {task?.report&&<details><summary>{task.adoption?'已加入場景 · ':''}新增 {task.report.added_count||0} 盞／恢復 {task.report.restored_count||0} 盞 · {task.report.uncertain_count||0} 項待確認</summary>
      {task.report.notes.map((n,i)=><p key={i}>{n}</p>)}
      <div style={{maxHeight:260,overflow:'auto'}}>{task.report.items.filter(i=>i.status!=='other').map(i=><div key={i.group_id}><p>{i.name}：{i.reason}{i.light_ids?.length?`（${i.light_ids.length} 盞）`:''}</p>{i.evidence&&<div style={{display:'flex',gap:6}}>{['object','reverse','bottom'].map(view=><a key={view} target="_blank" rel="noreferrer" href={`/api/studio/projects/${encodeURIComponent(project)}/fixture-lighting/${task.id}/images/${i.evidence!.replace('fixture-','')}/${view}`}><img loading="lazy" width={120} alt={view==='bottom'?'燈具下方局部圖':'燈具局部模型圖'} src={`/api/studio/projects/${encodeURIComponent(project)}/fixture-lighting/${task.id}/images/${i.evidence!.replace('fixture-','')}/${view}`}/></a>)}</div>}</div>)}</div>
      {task.status==='passed'&&!task.adoption&&!stale&&error&&<button disabled={working} onClick={()=>{applying.current='';setError('');setTask({...task});}}>重試保存配置</button>}
    </details>}
  </section>;
}
