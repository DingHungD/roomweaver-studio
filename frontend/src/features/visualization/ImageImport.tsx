import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {Job} from './api';
import PlanImport from './PlanImport';
import type {Plan} from './PlanImport';

type Task={id:string;status:string;error?:string;phase?:string};
type Intake={id:string;source:{name:string};task_id:string|null;task?:Task;plan?:Plan|null};
type Model={id:string;displayName:string;inputModalities?:string[]};
export default function ImageImport({project,baseRevision,onBuilt,onBack}:{project:string;baseRevision:string|null;onBuilt:(job:Job,base:string|null)=>Promise<void>;onBack:()=>void}){
  const [record,setRecord]=useState<Intake|null>(null),[plan,setPlan]=useState<Plan|null>(null);
  const [models,setModels]=useState<Model[]>([]),[model,setModel]=useState(''),[context,setContext]=useState('');
  const [busy,setBusy]=useState(''),[error,setError]=useState('');
  const file=useRef<HTMLInputElement>(null),lock=useRef(false),generation=useRef(0);
  const waiting=!!record?.task&&['queued','running','stopping'].includes(record.task.status);
  async function perform(label:string,work:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(label);setError('');try{await work();}catch(e){setError((e as Error).message);}finally{setBusy('');lock.current=false;}}
  useEffect(()=>{let active=true;const gen=++generation.current;void api<Intake|null>(`/projects/${project}/image-plans/current`).then(r=>{if(active&&gen===generation.current){setRecord(r);if(r?.plan)setPlan(r.plan);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[project]);
  useEffect(()=>{if(!record||!waiting)return;let active=true;const id=record.id;const timer=setInterval(()=>{void api<Intake>(`/projects/${project}/image-plans/${id}`).then(r=>{if(active)setRecord(r);}).catch(e=>{if(active)setError(e.message);});},2000);return()=>{active=false;clearInterval(timer);};},[project,record?.id,waiting]);
  if(plan)return <PlanImport project={project} baseRevision={baseRevision} initialPlan={plan} onNewImage={()=>setPlan(null)} onBuilt={onBuilt} onBack={()=>{setPlan(null);onBack();}}/>;
  return <section className="plan-intake" aria-label="圖片辨識"><div className="plan-heading"><div><small>圖片 → Agent 辨識 → 人工確認 → 3D</small><h2>從手繪圖開始</h2></div><button onClick={onBack} disabled={!!busy}>返回匯入方式</button></div>
    <p>原圖先保存在本機。按下辨識後，這張圖片、局部放大圖與補充說明會送到所選 Codex 模型，分兩輪盤點與複核，使用你的 ChatGPT 訂閱額度。建模仍需你確認。</p>
    <div className="plan-actions"><button disabled={!!busy||waiting} onClick={()=>file.current?.click()}>{record?'換一張圖片':'選擇 PNG／JPG'}</button><span>{record?.source.name||'PNG／JPG，最大 20 MB、2,400 萬像素'}</span></div>
    <input ref={file} type="file" hidden accept=".png,.jpg,.jpeg" onChange={e=>{const f=e.target.files?.[0];if(f)void perform('保存圖片…',async()=>{generation.current++;const body=new FormData();body.append('file',f);setRecord(await api<Intake>(`/projects/${project}/image-plans/upload`,'POST',body));});e.target.value='';}}/>
    <div className="plan-layout"><div className="plan-canvas">{record?<img className="image-source" alt="待辨識的原始平面圖" src={`/api/studio/projects/${project}/image-plans/${record.id}/image`}/>:<div className="plan-empty"><b>建議使用完整、正向、清楚的平面圖</b><p>至少保留一條已知長度。手繪圖可能不按比例，辨識後要逐項核對牆線、門窗及比例尺。</p></div>}</div>
      <aside className="plan-properties"><h3>辨識設定</h3><button disabled={!!busy||waiting} onClick={()=>perform('讀取本機 Codex…',async()=>{const c=await api<{authenticated:boolean;auth_type:string;models:Model[]}>('/agent/status');if(!c.authenticated||c.auth_type!=='chatgpt')throw new Error('請先在本機 Codex 完成 ChatGPT 登入');const list=c.models.filter(m=>m.inputModalities?.includes('image'));setModels(list);setModel(list[0]?.id||'');if(!list.length)throw new Error('目前沒有可用的圖片模型');})}>連接本機 Codex</button>
        <label>辨識模型<select value={model} disabled={!!busy||waiting||!!record?.task_id} onChange={e=>setModel(e.target.value)}><option value="">先連接以取得可用模型</option>{models.map(m=><option key={m.id} value={m.id}>{m.displayName}</option>)}</select></label>
        <label>圖面補充說明<textarea maxLength={4000} value={context} disabled={!!busy||waiting||!!record?.task_id} onChange={e=>setContext(e.target.value)} placeholder="例如：尺寸單位是公分；紅色是梁，綠色是管孔。"/></label>
        <button className="primary" disabled={!record||!model||!!record.task_id||!!busy} onClick={()=>perform('提交辨識…',async()=>{setRecord(await api<Intake>(`/projects/${project}/image-plans/${record!.id}/recognize`,'POST',{model,context}));})}>請 Agent 辨識</button>
        {waiting&&<><p role="status">{record?.task?.status==='queued'?'等待 Agent…':record?.task?.status==='stopping'?'正在停止…':(record?.task?.phase||'正在辨認牆線與門窗，通常需要數分鐘。可離開後續開。')}</p><button disabled={!!busy||record?.task?.status==='stopping'} onClick={()=>perform('要求停止…',async()=>{await api(`/agent/tasks/${record!.task_id}/stop`,'POST');setRecord(await api<Intake>(`/projects/${project}/image-plans/${record!.id}`));})}>停止辨識</button></>}
        {record?.task?.status==='passed'&&<><p>辨識候選已備妥，尚未确认設計或建立模型。</p><button className="primary" disabled={!!busy} onClick={()=>perform('開啟候選平面…',async()=>{setPlan(await api<Plan>(`/projects/${project}/image-plans/${record.id}/draft`,'POST'));})}>核對平面 →</button></>}
        {record?.task&&['failed','interrupted','stopped'].includes(record.task.status)&&<p role="alert">{record.task.error||'辨識已停止'}。可重新選擇圖片後明確重試，不會自動重送。</p>}
      </aside></div>{(busy||error)&&<p className={'studio-banner '+(error?'error':'')} role="status">{error||busy}</p>}
  </section>;
}
