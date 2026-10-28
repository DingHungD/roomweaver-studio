import {elapsed,workStatus} from './agentWorklistState';
import type {AgentWork} from './agentWorklistState';
import {useAgentWork} from './agentHubContext';
import './agentWorklist.css';

const clock=(value?:string)=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-TW',{hour12:false}):'時間未記錄';
function WorkRow({task,now}:{task:AgentWork;now:number}){
 const pending=['queued','running','stopping'].includes(task.status);
 const end=pending?now:Date.parse(task.finished_at||task.updated_at||'');
 return <li className="agent-work-row" data-status={task.status}>
  <div className="agent-work-row-heading"><strong>{task.activity?.title||'Agent 工作'}</strong><span className="agent-work-status">{workStatus(task.status)}</span></div>
  <p className="agent-work-phase">{task.phase||(task.status==='queued'?'等待 Agent 工作槽':pending?'等待階段回報':'此工作沒有保存階段說明')}</p>
  {task.error&&<p className="agent-work-error">{task.error}</p>}
  <div className="agent-work-meta"><span>{task.activity?.project_id?`專案 ${task.activity.project_id}`:'工作區任務'}</span>{task.model&&<span>{task.model}</span>}</div>
  <div className="agent-work-meta">
   <span>{task.status==='queued'?`已等待 ${elapsed(task.created_at,now)}`:task.started_at?`執行 ${elapsed(task.started_at,end)}`:`總耗時 ${elapsed(task.created_at,end)}`}</span>
   {pending&&task.status!=='queued'&&task.phase_started_at&&<span>此階段 {elapsed(task.phase_started_at,now)}</span>}
   {pending&&task.last_activity_at&&<span>最近回報 {elapsed(task.last_activity_at,now)}前</span>}
   {!pending&&task.finished_at&&<span>結束於 {clock(task.finished_at)}</span>}
  </div>
  <details className="agent-work-details"><summary>工作範圍與階段紀錄</summary>
   <p>工作 {task.id.slice(0,8)}{task.activity?.plan_id?` · 平面 ${task.activity.plan_id}`:''}</p>
   {!!task.activity?.items.length&&<ul aria-label="本次工作範圍">{task.activity.items.map((item,i)=><li key={i}>{item}</li>)}</ul>}
   {!!task.phase_history?.length&&<ol aria-label="階段紀錄">{task.phase_history.map((phase,i)=><li key={i}><time dateTime={phase.at}>{clock(phase.at)}</time><span>{phase.phase}</span></li>)}</ol>}
  </details>
 </li>;
}

export default function AgentWorklist(){
 const {snapshot,error,updated,now,page,loadedPage,setPage,refresh}=useAgentWork();
 return <section className="agent-work-panel" aria-label="Agent 工作清單">
   <div className="agent-work-body">
    {error&&<p className="agent-work-error" role="status">工作狀態暫時無法更新：{error}。保留上次讀取結果。</p>}
    {!!snapshot?.unavailable&&<p className="agent-work-error">{snapshot.unavailable} 筆工作紀錄目前無法讀取。</p>}
    <section aria-label="進行中與等待執行"><h3>進行中／等待執行 <span>{snapshot?.active.length||0}</span></h3>
     <ul className="agent-work-items">{snapshot?.active.map(task=><WorkRow key={task.id} task={task} now={now}/>)}</ul>
     {snapshot&&!snapshot.active.length&&<p className="agent-work-empty">目前沒有進行中或等待執行的工作。</p>}
    </section>
    <section aria-label="已結束工作"><h3>已結束 <span>{snapshot?.history_total||0}</span></h3>
     <ul className="agent-work-items">{snapshot?.history.map(task=><WorkRow key={task.id} task={task} now={now}/>)}</ul>
     {snapshot&&!snapshot.history_total&&<p className="agent-work-empty">尚無已結束的工作。</p>}
     {!!snapshot?.history_total&&<nav className="agent-work-pages" aria-label="工作歷史分頁"><button type="button" disabled={!page} onClick={()=>setPage(page-1)}>較新</button><span>第 {(loadedPage??page)+1} 頁{loadedPage!==null&&loadedPage!==page?` · 第 ${page+1} 頁尚未更新`:''}</span><button type="button" disabled={(page+1)*20>=snapshot.history_total} onClick={()=>setPage(page+1)}>較早</button></nav>}
    </section>
   </div>
   <footer><span>{updated?`上次讀取 ${clock(updated)}`:'尚未取得工作狀態'} · 每 2 秒更新</span><button type="button" onClick={refresh}>重新整理</button></footer>
 </section>;
}
