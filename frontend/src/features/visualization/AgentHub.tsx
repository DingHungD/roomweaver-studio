import {forwardRef,useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {api} from './api';
import type {Connection,Task} from './api';
import AgentWorklist from './AgentWorklist';
import {workCounts,workSummary} from './agentWorklistState';
import type {AgentWorkSnapshot} from './agentWorklistState';
import {AgentActionsContext,AgentLayoutContext,AgentModelContext,AgentWorkContext,useAgentActions,useAgentLayout,useAgentModel,useAgentWork,useOptionalAgentLayout} from './agentHubContext';
import type {AgentTab,CandidateWork} from './agentHubContext';
import {createAgentPoller,persistAgentPanel,readAgentPanel} from './agentHubState';
import './agentHub.css';

export {useAgentActions,useAgentModel,useOptionalAgentLayout} from './agentHubContext';
function storage(){try{return window.localStorage;}catch{return undefined;}}
const isNarrow=()=>typeof window!=='undefined'&&window.matchMedia('(max-width: 1199px)').matches;
const pending=(task:Task)=>['queued','running','stopping'].includes(task.status);

function AgentWorkProvider({children}:{children:ReactNode}){
 const [snapshot,setSnapshot]=useState<AgentWorkSnapshot|null>(null),[error,setError]=useState(''),[updated,setUpdated]=useState<string|null>(null),[now,setNow]=useState(Date.now());
 const [page,setPageValue]=useState(0),[loadedPage,setLoadedPage]=useState<number|null>(null),pageRef=useRef(0),poller=useRef<ReturnType<typeof createAgentPoller>|null>(null);
 useEffect(()=>{
  const controller=createAgentPoller({page:()=>pageRef.current,onTick:()=>setNow(Date.now()),onError:setError,
   async fetchSnapshot(offset,signal){
    const response=await fetch(`/api/studio/agent/tasks?history_limit=20&history_offset=${offset*20}`,{signal});const data=await response.json();
    if(!response.ok)throw new Error(data.error?.message||'無法讀取 Agent 工作清單');
    if(!Array.isArray(data.active)||!Array.isArray(data.history)||!Number.isFinite(data.history_total))throw new Error('工作狀態格式不完整');
    return data as AgentWorkSnapshot;
   },onSnapshot(value,index){setSnapshot(value);setLoadedPage(index);setError('');setUpdated(new Date().toISOString());setNow(Date.now());}});
  poller.current=controller;return()=>{controller.dispose();poller.current=null;};
 },[]);
 const setPage=useCallback((value:number)=>{const next=Math.max(0,Math.floor(value));pageRef.current=next;setPageValue(next);poller.current?.refresh();},[]);
 const refresh=useCallback(()=>poller.current?.refresh(),[]);
 const state=useMemo(()=>({snapshot,error,updated,now,page,loadedPage,setPage,refresh}),[snapshot,error,updated,now,page,loadedPage,setPage,refresh]);
 return <AgentWorkContext.Provider value={state}>{children}</AgentWorkContext.Provider>;
}

export function AgentHubProvider({children}:{children:ReactNode}){
 const [panel,setPanel]=useState(()=>readAgentPanel(storage())),[narrow,setNarrow]=useState(isNarrow),origin=useRef<HTMLButtonElement|null>(null);
 const takeoverScroll=useRef<[number,number]|null>(null);
 const rememberScroll=useCallback(()=>{takeoverScroll.current??=[window.scrollX,window.scrollY];},[]);
 const restoreScroll=useCallback(()=>{const position=takeoverScroll.current;if(position){takeoverScroll.current=null;requestAnimationFrame(()=>window.scrollTo(...position));}},[]);
 const [model,setModel]=useState(()=>{try{return storage()?.getItem('roomweaver.agent-model')||'';}catch{return '';}});
 const [connection,setConnection]=useState<Connection|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [tests,setTests]=useState<Task[]>([]),[candidates,setCandidates]=useState<CandidateWork[]>([]);
 const locked=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>persistAgentPanel(storage(),panel),[panel]);
 useEffect(()=>{try{storage()?.setItem('roomweaver.agent-model',model);}catch{/* Optional local preference. */}},[model]);
 useEffect(()=>{const query=window.matchMedia('(max-width: 1199px)');const changed=()=>{if(query.matches&&panel.open)rememberScroll();if(!query.matches)restoreScroll();setNarrow(query.matches);};query.addEventListener('change',changed);return()=>query.removeEventListener('change',changed);},[panel.open,rememberScroll,restoreScroll]);
 const selectTab=useCallback((tab:AgentTab)=>setPanel(previous=>({...previous,tab})),[]);
 const toggle=useCallback((button:HTMLButtonElement)=>{origin.current=button;if(!panel.open&&narrow)rememberScroll();if(panel.open)restoreScroll();setPanel(previous=>({...previous,open:!previous.open}));},[panel.open,narrow,rememberScroll,restoreScroll]);
 const close=useCallback(()=>{setPanel(previous=>({...previous,open:false}));restoreScroll();requestAnimationFrame(()=>{
  const visible=(button:HTMLButtonElement|null)=>!!button?.isConnected&&!!button.getClientRects().length&&!button.closest('[inert]');
  const button=visible(origin.current)?origin.current:[...document.querySelectorAll<HTMLButtonElement>('[data-agent-trigger]')].find(visible);
  button?.focus({preventScroll:true});
 });},[restoreScroll]);
 const run=useCallback(async(action:()=>Promise<void>)=>{if(locked.current)return;locked.current=true;setBusy(true);setError('');try{await action();}catch(e){if(alive.current)setError((e as Error).message);}finally{locked.current=false;if(alive.current)setBusy(false);}},[]);
 const check=useCallback(()=>run(async()=>{const value=await api<Connection>('/agent/status');if(alive.current)setConnection(value);}),[run]);
 const test=useCallback((kind:string)=>run(async()=>{const value=await api<Task>('/agent/tests','POST',{kind,model:model||null});if(alive.current)setTests(previous=>[value,...previous]);}),[run,model]);
 const stop=useCallback((id:string)=>run(async()=>{await api(`/agent/tasks/${id}/stop`,'POST');const next=await api<Task>(`/agent/tasks/${id}`);if(alive.current){setTests(previous=>previous.map(t=>t.id===id?next:t));setCandidates(previous=>previous.map(c=>c.task.id===id?{...c,task:next}:c));}}),[run]);
 const addCandidate=useCallback((project:string,revision:string|null,task:Task)=>setCandidates(previous=>[{project,revision,task},...previous.filter(c=>c.task.id!==task.id)]),[]);
 const detailIds=[...tests,...candidates.map(c=>c.task)].filter(pending).map(t=>t.id).sort().join(',');
 useEffect(()=>{
  if(!detailIds)return;let live=true,inFlight=false;
  const poll=async()=>{if(inFlight)return;inFlight=true;try{
   const updated=await Promise.allSettled(detailIds.split(',').map(id=>api<Task>(`/agent/tasks/${id}`)));
   if(live){const rows=updated.filter(r=>r.status==='fulfilled').map(r=>r.value);setTests(previous=>previous.map(t=>rows.find(u=>u.id===t.id)||t));setCandidates(previous=>previous.map(c=>({...c,task:rows.find(u=>u.id===c.task.id)||c.task})));if(updated.some(r=>r.status==='rejected'))setError('部分能力測試或候選暫時無法更新，保留上次結果');}
  }finally{inFlight=false;}};
  const timer=setInterval(()=>void poll(),2000);return()=>{live=false;clearInterval(timer);};
 },[detailIds]);
 const layout=useMemo(()=>({...panel,narrow,selectTab,toggle,close,origin}),[panel,narrow,selectTab,toggle,close]);
 const models=useMemo(()=>({model,setModel}),[model]);
 const actions=useMemo(()=>({connection,busy,error,tests,candidates,check,test,stop,addCandidate}),[connection,busy,error,tests,candidates,check,test,stop,addCandidate]);
 return <AgentLayoutContext.Provider value={layout}><AgentModelContext.Provider value={models}><AgentActionsContext.Provider value={actions}><AgentWorkProvider>{children}</AgentWorkProvider></AgentActionsContext.Provider></AgentModelContext.Provider></AgentLayoutContext.Provider>;
}

export function AgentTrigger(){
 const layout=useAgentLayout(),{snapshot,error}=useAgentWork();const counts=workCounts(snapshot?.active||[]),total=counts.running+counts.queued;
 return <button type="button" data-agent-trigger className="agent-hub-trigger" aria-expanded={layout.open} aria-controls="agent-hub-panel" onClick={event=>layout.toggle(event.currentTarget)} title={error?`工作狀態更新失敗：${error}`:!snapshot?'正在讀取 Agent 工作狀態…':`${counts.running} 進行中 · ${counts.queued} 等待 · ${workSummary(snapshot)}`}>
  <span>Agent</span>{total>0&&<span className="agent-hub-count" aria-label={`${counts.running} 進行中，${counts.queued} 等待`}>{total}</span>}{error&&<span className="agent-hub-warning" aria-label="工作狀態更新失敗">!</span>}
 </button>;
}

function AgentSettings({children}:{children?:ReactNode}){
 const {model,setModel}=useAgentModel(),actions=useAgentActions(),{connection}=actions;
 return <div className="agent-hub-settings"><h3>Agent 設定與能力測試</h3><p>沿用本機 ChatGPT 訂閱登入。模型在雲端執行，檔案與渲染留在本機。</p>
  {actions.error&&<p role="status" className="agent-work-error">{actions.error}</p>}
  <button disabled={actions.busy} onClick={()=>void actions.check()}>檢查登入與模型</button>{connection&&<p>{connection.authenticated?'已登入':'尚未登入'} · {connection.auth_type} · {connection.version}</p>}
  <label>模型<select value={model} onChange={event=>setModel(event.target.value)}><option value="">使用模型清單預設{connection?.default_model?`（${connection.default_model}）`:''}</option>{model&&!connection?.models.some(m=>m.id===model)&&<option value={model}>{model}（已選定，待確認可用性）</option>}{connection?.models.map(m=><option key={m.id} value={m.id}>{m.displayName}</option>)}</select></label>
  <p className="muted">預設取自 Codex 模型清單。清單不保證帳號權限，請先測試連線；不會自動切換供應者。</p>
  <div className="test-buttons">{(['connection','vision','tool','browser'] as const).map((kind,i)=><button key={kind} disabled={actions.busy} onClick={()=>void actions.test(kind)}>{['連線','看圖','工具','瀏覽器操作'][i]}</button>)}</div>
  {actions.tests.map(task=><article className="agent-task" key={task.id}><b>{task.kind} · {task.status}</b>{pending(task)&&<button disabled={actions.busy} onClick={()=>void actions.stop(task.id)}>停止</button>}{task.error&&<p className="agent-work-error">{task.error}</p>}{task.response&&<p>{task.response.text}</p>}{task.evidence&&<img src={`/api/studio/agent/tasks/${task.id}/images/${task.evidence.screenshot.split(/[\\/]/).at(-1)}`} alt="瀏覽器實際狀態"/>}</article>)}
  {children}
 </div>;
}

function AgentHubPanel({settingsExtra}:{settingsExtra?:ReactNode}){
 const layout=useAgentLayout(),panel=useRef<HTMLElement>(null),tabButtons=useRef<(HTMLButtonElement|null)[]>([]);
 useEffect(()=>{if(layout.open)requestAnimationFrame(()=>tabButtons.current[layout.tab==='work'?0:1]?.focus());},[layout.open,layout.narrow]);
 return <aside ref={panel} id="agent-hub-panel" className="agent-hub-panel" hidden={!layout.open} role={layout.narrow?'dialog':undefined} aria-modal={layout.narrow&&layout.open?true:undefined} aria-label="Agent 工作與設定" onKeyDown={event=>{
  if(event.defaultPrevented)return;
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();layout.close();}
  if(event.key==='Tab'&&layout.narrow){const elements=[...panel.current!.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]')].filter(e=>e.tabIndex>=0&&e.getClientRects().length&&!e.closest('[hidden]'));const first=elements[0],last=elements.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
 }}>
  <header className="agent-hub-heading"><h2>Agent</h2><button type="button" aria-label="收合 Agent 側欄" onClick={layout.close}>收合 ›</button></header>
  <div role="tablist" aria-label="Agent 分頁" className="agent-hub-tabs" onKeyDown={event=>{const index=layout.tab==='work'?0:1;const next=event.key==='Home'?0:event.key==='End'?1:event.key==='ArrowRight'?1-index:event.key==='ArrowLeft'?1-index:null;if(next!==null){event.preventDefault();layout.selectTab(next===0?'work':'settings');tabButtons.current[next]?.focus();}}}>
   {(['work','settings'] as const).map((tab,index)=><button ref={element=>{tabButtons.current[index]=element;}} key={tab} type="button" id={`agent-tab-${tab}`} role="tab" aria-selected={layout.tab===tab} aria-controls={`agent-content-${tab}`} tabIndex={layout.tab===tab?0:-1} onClick={()=>layout.selectTab(tab)}>{tab==='work'?'工作':'設定'}</button>)}
  </div>
  <div className="agent-hub-tab-body" id="agent-content-work" role="tabpanel" aria-labelledby="agent-tab-work" hidden={layout.tab!=='work'}><AgentWorklist/></div>
  <div className="agent-hub-tab-body" id="agent-content-settings" role="tabpanel" aria-labelledby="agent-tab-settings" hidden={layout.tab!=='settings'}><AgentSettings>{settingsExtra}</AgentSettings></div>
 </aside>;
}

export const AgentHubFrame=forwardRef<HTMLDivElement,{children:ReactNode;className?:string;settingsExtra?:ReactNode}>(function AgentHubFrame({children,className='',settingsExtra},ref){
 const layout=useOptionalAgentLayout();const takeover=!!layout?.open&&layout.narrow;
 return <div ref={ref} className={`agent-hub-layout ${layout?.open?'agent-is-open':''} ${layout?.narrow?'agent-is-narrow':''} ${className}`}>
  <div className="agent-hub-main" hidden={takeover} inert={takeover}>{children}</div>{layout&&<AgentHubPanel settingsExtra={settingsExtra}/>}
 </div>;
});
