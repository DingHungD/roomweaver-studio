import {useState} from 'react';
import {api} from './api';
import type {Output} from './api';

export default function OutputCleanup({project,revision,outputs,disabled,onChange}:{project:string;revision:string;outputs:Output[];disabled:boolean;onChange:()=>Promise<void>}){
  const [pending,setPending]=useState<{revision:string;items:Output[]}|null>(null);
  const [working,setWorking]=useState(false);const [message,setMessage]=useState('');
  const old=outputs.filter(o=>o.stale&&!o.deleted);
  const trash=outputs.filter(o=>o.deleted);
  const outdated=pending?.revision!==revision;
  async function submit(items:Output[],restore=false){
    setWorking(true);setMessage('');
    try{
      await api(`/projects/${project}/outputs/${restore?'restore':'trash'}`,'POST',{base_revision:revision,job_ids:[...new Set(items.map(o=>o.job_id))]});
      setPending(null);await onChange();setMessage(restore?'已復原成果；勾選「包含舊修訂成果」即可查看。':'舊修訂成果已移至回收區，目前修訂的成果保持不變。');
    }catch(e){setMessage((e as Error).message);}finally{setWorking(false);}
  }
  return <section className="output-cleanup" aria-label="成果清理">
    <div className="render-options"><button disabled={disabled||working||!old.length} onClick={()=>{setPending({revision,items:old});setMessage('');}}>清除舊修訂成果（{old.length} 張）</button>
      {trash.length>0&&<button disabled={disabled||working} onClick={()=>void submit(trash,true)}>復原回收區（{trash.length} 張）</button>}
    </div>
    {pending&&<div className="confirm-card" role="region" aria-label="確認清除舊成果"><h3>只保留目前修訂的成果</h3>
      <p>將移除 {pending.items.length} 張圖片，來自 {new Set(pending.items.map(o=>o.job_id)).size} 個出圖批次。</p>
      <p>保留修訂 {pending.revision.slice(0,8)} 的全部成果，包括同版重跑。模型、設計設定與執行紀錄保留。</p>
      {!outputs.some(o=>!o.stale&&!o.deleted)&&<p>目前修訂尚無成圖；清除後成果列表將為空白。</p>}
      <p>移至可復原的回收區，不釋放磁碟空間。</p>
      {outdated&&<p role="alert">修訂已改變，請取消後重新選擇。</p>}
      <button disabled={disabled||working||outdated} onClick={()=>void submit(pending.items)}>確認移至回收區</button>
      <button disabled={working} onClick={()=>setPending(null)}>取消</button>
    </div>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
