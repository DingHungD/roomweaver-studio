import {useEffect,useState,useRef} from 'react';
import {api} from './api';
import type {Job,Revision} from './api';
type PreviewJob=Job&{adopted:boolean};
export default function MaterialPreviewRepair({project,group,revision,dirty,busy,onAccept,compact=false}:{compact?:boolean;project:string;group:string;revision:string|null;dirty:boolean;busy:boolean;onAccept:(r:Revision)=>void}){
 const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const [job,setJob]=useState<PreviewJob|null>(null),[working,setWorking]=useState(false),[error,setError]=useState('');
 const path=`/projects/${project}/asset-preview-repair`;
 useEffect(()=>{let live=true;const load=()=>api<PreviewJob|null>(path+`?group_id=${encodeURIComponent(group)}`).then(r=>{if(live)setJob(r);}).catch(e=>{if(live)setError(e.message);});void load();if(!job||!['queued','running'].includes(job.status))return()=>{live=false;};const timer=setInterval(()=>{void load();},2500);return()=>{live=false;clearInterval(timer);};},[project,group,revision,job?.id,job?.status]);
 const active=!!job&&['queued','running'].includes(job.status);
 async function run(fn:()=>Promise<void>){if(working)return;setWorking(true);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setWorking(false);}}
 return <details open={compact&&job&&(active||job.error||(!job.adopted&&job.status==='completed'))?true:undefined}><summary>{compact?'預覽異常處理':'材質預覽修正（本機）'}</summary><p>補齊此物件 UV，重建色彩、粗糙度、金屬度與法線貼圖；不重新搜尋或下載。保留原生渲染材質及舊模型，完成後再採用。</p>
 <button disabled={busy||dirty||working||active||!revision} onClick={()=>run(async()=>{setJob(await api<PreviewJob>(path,'POST',{base_revision:revision,group_id:group,operation_id:crypto.randomUUID().replaceAll('-','')}));})}>修正目前材質預覽</button>
 {dirty&&<small>請先保存編輯。</small>}{job&&<p role="status">{job.adopted?'已採用預覽修正':job.status==='completed'?'修正完成，等待採用':job.status==='running'?'正在本機烘焙預覽':job.status==='queued'?'等待本機工作':job.status}</p>}
 {job?.error&&<p role="alert">{job.error.split('\n').filter(l=>l.includes('ValueError:')).at(-1)||job.error}</p>}
 {job?.status==='completed'&&!job.adopted&&<button disabled={busy||dirty||working} onClick={()=>run(async()=>{const r=await api<Revision>(`/projects/${project}/asset-replacements/${job.id}/adopt`,'POST',{base_revision:revision,confirmation_id:job.id});if(alive.current){onAccept(r);setJob({...job,adopted:true});}})}>採用預覽修正</button>}
 {error&&<p role="alert">{error}</p>}</details>;
}
