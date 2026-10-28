import {useRef} from 'react';
import type {Scene} from './api';

/** Project-wide labels and unresolved notes, outside an individual object's tabs. */
export default function MaterialProjectManagement({scene,busy,onChange}:{scene:Scene;busy:boolean;onChange:(scene:Scene)=>void}){
  const dialog=useRef<HTMLDialogElement>(null);
  const edit=(change:(next:Scene)=>void)=>{const next=structuredClone(scene);change(next);onChange(next);};
  return <><button disabled={busy} onClick={()=>dialog.current?.showModal()}>專案管理</button>
    <dialog ref={dialog} className="asset-batch-dialog material-project-dialog" aria-label="材質頁專案管理">
      <header><h2>專案管理</h2><button aria-label="關閉專案管理" onClick={()=>dialog.current?.close()}>關閉</button></header>
      <fieldset disabled={busy} style={{border:0,padding:0,minWidth:0}}>
        <h3>空間名稱管理</h3><p>管理空間名稱；新增名稱不會自動建立房間幾何。</p>
        {scene.rooms.map(room=><label key={room.id}>空間名稱<input value={room.name} onChange={e=>edit(next=>{next.rooms.find(r=>r.id===room.id)!.name=e.target.value;})}/></label>)}
        <button onClick={()=>edit(next=>{next.rooms.push({id:'room-'+crypto.randomUUID().slice(0,8),name:'新空間'});})}>＋ 新增空間</button>
        <h3>概念配置尚待核對（{scene.design_notes?.length||0}）</h3>
        {scene.design_notes?.length?<ul>{scene.design_notes.map((note,index)=><li key={index}>{note}</li>)}</ul>:<p>目前沒有概念配置待核對紀錄。</p>}
      </fieldset>
      <footer><small>修改留在目前草稿；關閉後請按「保存修改」。</small><button onClick={()=>dialog.current?.close()}>完成</button></footer>
    </dialog>
  </>;
}
