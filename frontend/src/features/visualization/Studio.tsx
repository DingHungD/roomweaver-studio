import {canAdoptAgentCandidate} from './agentHubState';
import {IncompleteRepairProvider} from './IncompleteRepair';
import {EditorWorkspace,WorkspaceControls,RailToggle} from './EditorWorkspace';
import {useCallback,useEffect,useRef,useState} from 'react';
import ProjectHome from './ProjectHome';
import {AgentHubProvider,AgentHubFrame,AgentTrigger,useAgentModel,useAgentActions} from './AgentHub';
import type {LibraryProject} from './ProjectHome';
import {ProjectDraftContext} from './ProjectDraft';
import type {ProjectDraft} from './ProjectDraft';
import {api,fileUrl} from './api';
import type {Job,Output,Revision,Scene,Task,Workflow} from './api';
import {Panorama} from './ModelViewer';
import ViewpointEditor from './ViewpointEditor';
import {confirmDesignRevision,renderReady} from './studioFlow';
import './studio.css';
import SpaceEditor from './SpaceEditor';
import {ViewportProvider} from './SpaceViewport';
import OutputCleanup from './OutputCleanup';
import PlanImport from './PlanImport';
import ImageImport from './ImageImport';
import ImportStart from './ImportStart';
import SourceModelPage from './SourceModelPage';
import type {ImportRoute} from './ImportStart';
import {LightingRun} from './LightingPanel';
import SceneReviewRun from './SceneReviewRun';
import RealismRun from './RealismRun';
import RealismPreview from './RealismPreview';
import LightEditor from './LightEditor';
import DoorEditor from './DoorEditor';
import RenderPreflightDialog from './RenderPreflightDialog';
import {renderPreflight} from './renderPreflight';
import type {RenderIssue,RenderReadiness} from './renderPreflight';
const captions=['匯入你的設計','編輯空間與材質','配置光源','設定觀看點與方向','整合輸出','裝飾物','門的開啟方位'];
type Readiness=RenderReadiness;
type Project=LibraryProject;
type IntakeStatus={current:Project|null;job:Job|null;examples:Partial<Record<ImportRoute,boolean>>};
type IntakeResult={project:Project;route:ImportRoute;job:Job|null;base_revision?:string|null};
type ProjectResume={project:Project;step:number;route:'choose'|ImportRoute;job:Job|null;base_revision:string|null};
const uid=()=>crypto.randomUUID().replaceAll('-','');
export default function Studio(){
 const [opened,setOpened]=useState<Project|null>(null);
 return <AgentHubProvider>{opened?<StudioProject key={opened.id} initialProject={opened} onHome={()=>setOpened(null)}/>:<AgentHubFrame className="agent-home-layout"><ProjectHome onOpen={setOpened} agentControl={<AgentTrigger/>}/></AgentHubFrame>}</AgentHubProvider>;
}
function StudioProject({initialProject,onHome}:{initialProject:Project;onHome:()=>void}){
  const [projects,setProjects]=useState<Project[]>([initialProject]);const [project,setProject]=useState(initialProject.id);const [step,setStep]=useState(0);
  const drafts=useRef(new Map<string,ProjectDraft>());
  const registerDraft=useCallback((id:string,draft:ProjectDraft|null)=>{if(draft)drafts.current.set(id,draft);else drafts.current.delete(id);},[]);
  const [exitOpen,setExitOpen]=useState(false),[exitBusy,setExitBusy]=useState(false),[exitError,setExitError]=useState('');
  const exitDialog=useRef<HTMLDialogElement>(null),homeButton=useRef<HTMLButtonElement>(null);
  useEffect(()=>{if(exitOpen){exitDialog.current?.showModal();requestAnimationFrame(()=>exitDialog.current?.querySelector<HTMLButtonElement>('button')?.focus());}},[exitOpen]);
  const [revision,setRevision]=useState<string|null>(null);const [scene,setScene]=useState<Scene|null>(null);const [dirty,setDirty]=useState(false);
  const renderButton=useRef<HTMLButtonElement>(null);
  const [preflight,setPreflight]=useState<RenderIssue[]|null>(null);
  const [readiness,setReadiness]=useState<Readiness|null>(null);
  useEffect(()=>{let active=true;setReadiness(null);if(scene)void api<{render_readiness?:Readiness}>(`/projects/${project}/models/${scene.model_id}`).then(m=>{if(active)setReadiness(m.render_readiness||null);}).catch(()=>{});return()=>{active=false;};},[project,scene?.model_id]);
  const [history,setHistory]=useState<Scene[]>([]);
  const [confirmedRevision,setConfirmedRevision]=useState<string|null>(null);
  const [busy,setBusy]=useState('');const [error,setError]=useState('');const [notice,setNotice]=useState('');const [job,setJob]=useState<Job|null>(null);
  const [workflow,setWorkflow]=useState<Workflow|null>(null);const [outputs,setOutputs]=useState<Output[]>([]);const [view,setView]=useState<Output|null>(null);
  const {model,setModel}=useAgentModel();const agent=useAgentActions();const tasks=agent.candidates.filter(entry=>entry.project===project);
  const [realismBrief,setRealismBrief]=useState('');
  const [previewJob,setPreviewJob]=useState<string|null>(null);
  useEffect(()=>{setPreviewJob(null);},[project,revision]);
  useEffect(()=>{if(dirty)setPreviewJob(null);},[dirty]);
  useEffect(()=>{let active=true;
    if(workflow?.status==='completed'&&workflow.realism_point_id&&workflow.job_id&&!dirty&&workflow.revision===revision){
      void api<{model_preview?:unknown}>(`/jobs/${workflow.job_id}/realism-review`).then(r=>{if(active&&r.model_preview)setPreviewJob(workflow.job_id!);}).catch(()=>{});
    }
    return()=>{active=false;};
  },[project,revision,workflow?.job_id,workflow?.status]);

  useEffect(()=>{setRealismBrief('');},[project]);
  const [realismAll,setRealismAll]=useState(false),[prepareOpenings,setPrepareOpenings]=useState(true);
  const [realismPoint,setRealismPoint]=useState('');const [realismEnabled,setRealismEnabled]=useState(false);
  const [sceneReview,setSceneReview]=useState(false);const [quality,setQuality]=useState('preview');const [showOld,setShowOld]=useState(false);const actionRunning=useRef(false);const savedScene=useRef<Scene|null>(null);
  const projectInfo=projects.find(p=>p.id===project);
  const [intake,setIntake]=useState<'choose'|'glb'|'dxf'|'image'>('choose');
  const [importPending,setImportPending]=useState(false);
  const [examples,setExamples]=useState<Partial<Record<ImportRoute,boolean>>>({}),[intakeJob,setIntakeJob]=useState<Job|null>(null);
  async function receivePlanJob(next:Job,base:string|null,identifier=project,route=intake){setScene(null);setRevision(base);setConfirmedRevision(null);setWorkflow(null);setImportPending(true);setJob(next);if(next.status==='completed'){if(route==='glb'){setImportPending(false);setStep(7);return;}accept(await api<Revision>(`/projects/${identifier}/import/adopt`,'POST',{job_id:next.id,base_revision:base}),identifier);setImportPending(false);setStep(1);}}
  async function perform(label:string,action:()=>Promise<void>){if(actionRunning.current)return;actionRunning.current=true;setBusy(label);setError('');try{await action();}catch(e){setError(String((e as Error).message));}finally{actionRunning.current=false;setBusy('');}}
  useEffect(()=>{void perform('讀取專案',async()=>{const data=await api<IntakeStatus>('/intake');setExamples(data.examples);await loadProject();});},[]);
  function accept(data:Revision,identifier=project){setHistory([]);savedScene.current=data.scene;setScene(data.scene);setRevision(data.revision);setDirty(false);if(data.scene){setProjects(old=>old.map(p=>p.id===identifier?{...p,revision:data.revision}:p));setOutputs(old=>old.map(o=>({...o,stale:o.revision!==data.revision})));}}
  function changeScene(next:Scene){if(scene&&JSON.stringify(next)!==JSON.stringify(scene))setHistory(h=>[...h.slice(-19),scene]);setScene(next);setDirty(JSON.stringify(next)!==JSON.stringify(savedScene.current));}
  function undo(){const previous=history.at(-1);if(!previous)return;setHistory(h=>h.slice(0,-1));setScene(previous);setDirty(JSON.stringify(previous)!==JSON.stringify(savedScene.current));}
  async function save(){if(!scene)return;const data=await api<Revision>(`/projects/${project}/scene`,'PUT',{base_revision:revision,scene});setRevision(data.revision);setDirty(false);setOutputs(old=>old.map(o=>({...o,stale:o.revision!==data.revision})));savedScene.current=scene;setNotice('已建立新修訂，既有成果仍保留。');return data.revision;}
  async function beginIntake(result:IntakeResult){
    setProject(result.project.id);setProjects([result.project]);setScene(null);savedScene.current=null;setRevision(result.base_revision??result.project.revision);setDirty(false);setHistory([]);setConfirmedRevision(null);setWorkflow(null);setOutputs([]);setJob(null);setPreviewJob(null);setNotice('');setImportPending(false);setIntake(result.route);setIntakeJob(result.job);
    if(result.job)await receivePlanJob(result.job,result.base_revision??result.project.revision,result.project.id,result.route);
  }
  function chooseFile(route:ImportRoute,file:File){void perform(file.name.toLowerCase().endsWith('.dwg')?'正在將 DWG 轉成 DXF，完成後進入平面確認…':'正在開啟檔案…',async()=>{const body=new FormData();body.append('file',file);await beginIntake(await api<IntakeResult>(`/intake/upload?route=${route}&operation_id=${uid()}&project_id=${encodeURIComponent(project)}`,'POST',body));});}
  function openExample(route:ImportRoute){void perform('正在開啟 Project04 範例…',async()=>{await beginIntake(await api<IntakeResult>('/intake/examples','POST',{route,operation_id:uid(),project_id:project}));});}
  async function loadProject(){
    const state=await api<ProjectResume>(`/project-library/${initialProject.id}/resume`);
    setProject(state.project.id);setProjects([state.project]);setIntakeJob(state.job);setIntake(state.route);
    if(state.step===7||(state.route==='glb'&&state.step!==0)){setScene(null);savedScene.current=null;setStep(7);return;}
    if(state.step===0){setScene(null);savedScene.current=null;setRevision(state.base_revision);setStep(0);if(state.job)await receivePlanJob(state.job,state.base_revision,state.project.id,state.route);}
    else await openSaved(state.project.id,state.step);
  }
  async function continueIntake(){if(scene){setStep(1);return;}await loadProject();}
  async function refreshOutputs(){setOutputs(await api<Output[]>(`/projects/${project}/outputs?include_deleted=true`));}
  async function openSaved(identifier=project,targetStep=1){const saved=await api<Revision>(`/projects/${identifier}/scene`);accept(saved,identifier);setStep(targetStep);setOutputs(await api<Output[]>(`/projects/${identifier}/outputs?include_deleted=true`));const runs=await api<Workflow[]>(`/projects/${identifier}/workflows`);const latest=runs.filter(r=>r.quality).at(-1)||null;setWorkflow(latest);setSceneReview(!!latest?.scene_review);setRealismEnabled(!!latest?.realism_point_id);const preparation=await api<(Job&{preparation_context?:{brief:string}})|null>(`/projects/${identifier}/realism-prepare`);setRealismBrief(preparation?.preparation_context?.brief??latest?.realism_brief??'');setRealismAll(!!latest?.realism_all);setRealismPoint(latest?.realism_point_id||saved.scene?.viewpoints.find(p=>p.shots.length)?.id||'');const designs=await api<Workflow[]>(`/projects/${identifier}/design`);setConfirmedRevision(designs.find(r=>r.status==='ready'&&r.revision===saved.revision)?.revision||null);}
  useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let alive=true;const timer=setInterval(()=>{api<Job>(`/jobs/${job.id}`).then(async next=>{if(!alive)return;setJob(next);if(next.status==='completed'&&!scene){if(intake==='glb'){setImportPending(false);setStep(7);return;}const data=await api<Revision>(`/projects/${project}/import/adopt`,'POST',{job_id:next.id,base_revision:revision});accept(data);setImportPending(false);setStep(1);}else if(['failed','interrupted'].includes(next.status))setError(next.error||'工作中斷');}).catch(e=>{if(alive)setError(e.message);});},2000);return()=>{alive=false;clearInterval(timer);};},[job?.id,job?.status,project,scene,revision,intake]);
  useEffect(()=>{if(!workflow?.job_id||['completed','failed','stopped','interrupted'].includes(workflow.status))return;let alive=true;const timer=setInterval(async()=>{try{const next=await api<Workflow>(`/workflows/${workflow.run_id}`);const progress=await api<Job>(`/jobs/${workflow.job_id}`);if(!alive)return;setWorkflow(next);setJob(progress);if(next.status==='completed')await refreshOutputs();}catch(e){if(alive)setError((e as Error).message);}},2500);return()=>{alive=false;clearInterval(timer);};},[workflow?.run_id,workflow?.status]);
  async function rememberView(){if(scene&&revision&&!dirty&&step>0)await api(`/project-library/${project}/view`,'PUT',{revision,step});}
  useEffect(()=>{if(!scene||!revision||dirty||busy||step===0)return;const timer=setTimeout(()=>{void rememberView().catch(()=>{/* Resume falls back to authoritative saved progress. */});},300);return()=>{clearTimeout(timer);};},[project,scene?.model_id,revision,dirty,busy,step]);
  useEffect(()=>{const prevent=(e:BeforeUnloadEvent)=>{if(dirty||[...drafts.current.values()].some(d=>d.dirty)){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',prevent);return()=>window.removeEventListener('beforeunload',prevent);},[dirty]);
  function canSaveDrafts(){return [...drafts.current.values()].filter(d=>d.dirty).every(d=>!!d.save&&!d.blocked);}
  async function requestHome(){if(dirty||[...drafts.current.values()].some(d=>d.dirty)){setExitError('');setExitOpen(true);return;}try{await rememberView();}catch{/* Saved design remains available even without a view hint. */}onHome();}
  function cancelExit(){exitDialog.current?.close();setExitOpen(false);requestAnimationFrame(()=>homeButton.current?.focus());}
  async function saveAndHome(){if(exitBusy)return;setExitBusy(true);setExitError('');try{const rev=dirty?await save():revision;for(const draft of [...drafts.current.values()].filter(d=>d.dirty)){if(!draft.save||draft.blocked)throw new Error('請先完成目前頁面的處理');await draft.save();}if(scene&&rev&&step>0)await api(`/project-library/${project}/view`,'PUT',{revision:rev,step});onHome();}catch(e){setExitError((e as Error).message);}finally{setExitBusy(false);}}
  const readyForRender=renderReady(revision,confirmedRevision,dirty);
  async function confirmDesign(includePoints:boolean){
    const rev=dirty?await save():revision;if(!rev)return;
    await confirmDesignRevision(rev,includePoints,(phase,base_revision)=>api(`/projects/${project}/design/confirm`,'POST',{phase,base_revision}));
    if(includePoints){setConfirmedRevision(rev);setStep(4);setNotice('觀看點與方向已確認。選擇品質並建立出圖工作後，才會提交渲染。');}else setStep(3);
  }
  async function candidate(objectId:string){const rev=dirty?await save():revision;const task=await api<Task>(`/projects/${project}/candidates`,'POST',{base_revision:rev,object_id:objectId,model:model||null,operation_id:uid()});agent.addCandidate(project,rev??null,task);}
  async function createRender(){
    // Read fresh metadata only; checking never saves, confirms or submits Blender.
    if(!scene)return;
    const [current,modelInfo,designs]=await Promise.all([
      api<Revision>(`/projects/${project}/scene`),
      api<{render_readiness?:Readiness}>(`/projects/${project}/models/${scene.model_id}`),
      api<Workflow[]>(`/projects/${project}/design`),
    ]);
    const report=modelInfo.render_readiness||null;
    const confirmed=designs.find(r=>r.status==='ready'&&r.revision===revision)?.revision||null;
    setReadiness(report);setConfirmedRevision(confirmed);
    const missing=renderPreflight(scene,revision,confirmed,dirty,report,current.revision);
    if(missing.length){setPreflight(missing);return;}
    setJob(null);setWorkflow(await api<Workflow>(`/projects/${project}/workflows`,'POST',{base_revision:revision,operation_id:uid(),quality:realismEnabled?'preview':quality,scene_review:realismEnabled?false:sceneReview,realism_point_id:realismEnabled?realismPoint:null,realism_brief:realismEnabled?realismBrief:'',realism_all:realismEnabled&&realismAll,prepare_openings:realismEnabled&&prepareOpenings,agent_model:model||null}));
  }
  const visibleOutputs=outputs.filter(o=>!o.deleted&&(showOld||!o.stale));
  if(step===7)return <SourceModelPage project={project} name={projectInfo?.name||project} onHome={onHome} onImport={()=>{setIntake('choose');setStep(0);}}/>;
  const agentCandidates=tasks.length?<section aria-label="本案材質候選"><h3>本案材質候選</h3>{tasks.map(entry=>{const task=entry.task,stale=entry.revision!==revision;return <article className="agent-task" key={task.id}><b>{task.kind} · {task.status}</b>{['queued','running','stopping'].includes(task.status)&&<button disabled={agent.busy} onClick={()=>void agent.stop(task.id)}>停止</button>}{task.error&&<p className="agent-work-error">{task.error}</p>}{task.response&&<p>{task.response.text}</p>}{task.evidence&&<img src={`/api/studio/agent/tasks/${task.id}/images/${task.evidence.screenshot.split(/[\\/]/).at(-1)}`} alt="Agent evidence"/>}{task.candidate&&<><span className="candidate-swatch" style={{background:task.candidate.color}}/>{task.candidate.reason}<p>{task.candidate.source_verified?'已讀取指定參考頁，授權尚未核對。':'依使用者描述提出，尚未查核外部來源。'}本候選只調整基本色與粗糙度。</p>{stale&&<p>來源版本已變更，請重新整理候選。</p>}<button disabled={!scene||!canAdoptAgentCandidate(entry,project,revision,dirty,!!busy)} onClick={()=>perform('採用材質候選',async()=>{accept(await api<Revision>(`/projects/${project}/candidates/${task.id}/adopt`,'POST',{base_revision:revision,confirmation_id:task.id}));setNotice('已採用於指定物件，重新出圖即可查看。');})}>採用於指定物件</button></>}</article>;})}</section>:null;
  return <ProjectDraftContext.Provider value={registerDraft}><IncompleteRepairProvider project={project} scene={scene} revision={revision} dirty={dirty} onSave={save} onAccept={accept}><ViewportProvider><EditorWorkspace settingsExtra={agentCandidates} section={step} editing={!!scene&&[1,2,3,5,6].includes(step)}><div className="studio-app">
    <header className="studio-header"><a className="studio-brand" href="?studio=visualization"><span>◈</span> Roomweaver <small>LOCAL STUDIO</small></a><div className="project-back"><button ref={homeButton} disabled={!!busy} onClick={()=>void requestHome()}>← 我的專案</button><span title={projectInfo?.name}>{projectInfo?.name}</span></div><div className="header-actions"><span className="local-pill">● 本機運算</span>{scene&&<button disabled={!!busy} onClick={()=>perform('建立備份',async()=>{const result=await api<{path:string}>('/backup','POST');setNotice('資料庫與設定已備份：'+result.path);})}>備份設定</button>}<AgentTrigger/></div></header>
    <div className="studio-shell"><nav className="studio-rail" aria-label="工作室導覽">
      {scene&&[1,2,3,5,6].includes(step)&&<RailToggle label={captions[step]}/>}<small>設計工作區</small><button className={step===0?'active':''} aria-current={step===0?'page':undefined} onClick={()=>{if(step!==0)setIntake('choose');setStep(0);}}><b>01</b> 匯入</button>
      <button disabled={!scene} className={step>0&&step!==4?'active':''} onClick={()=>setStep(1)}><b>02</b> 編輯</button>
      {scene&&<div className="edit-sections">{([{id:1,name:'材質',icon:'▧'},{id:6,name:'門',icon:'◫'},{id:5,name:'裝飾物',icon:'✿'},{id:2,name:'光源',icon:'☀'},{id:3,name:'觀看點',icon:'◎'}]).map(item=><button key={item.id} aria-current={step===item.id?'page':undefined} className={step===item.id?'selected':''} onClick={()=>setStep(item.id)}><span>{item.icon}</span>{item.name}</button>)}</div>}
      <button disabled={!scene} className={step===4?'active':''} aria-current={step===4?'page':undefined} onClick={()=>setStep(4)}><b>03</b> 整合輸出</button>
      <p>{scene?projectInfo?.name:'先匯入模型，再開始編輯。'}</p>
    </nav><div className="studio-content">
    <div className="studio-title"><div><small>YOUR SPACE, YOUR PERSPECTIVE</small><h1>{captions[step]}</h1></div>{scene&&step!==0&&<div className="save-actions"><span>{dirty?'有尚未保存的修改':`已保存 · ${revision?.slice(0,8)}`}</span><button disabled={!dirty||!!busy} onClick={()=>perform('保存中',async()=>{await save();})}>保存修改</button></div>}{scene&&[1,2,3,5,6].includes(step)&&<WorkspaceControls/>}</div>
    {(error||busy||notice)&&<div className={`studio-banner ${error?'error':''}`} role="status">{error||busy||notice}<button aria-label="關閉通知" onClick={()=>{setError('');setNotice('');}}>×</button></div>}
    {scene&&step===4&&<div className="studio-banner" role="note"><span>{scene.lighting_setup?.enabled?'已採用自訂照明；出圖時會試渲染並依設定進行 Agent 判圖／有限次調整。':readiness?.status==='blocked'?`渲染尚未就緒：${readiness.issues.join('；')}`:readiness?`照明盤點：${readiness.light_count} 盞燈 · ${readiness.world_available?'有環境光':'無環境光'}。出圖前會逐鏡位試渲染檢查。`:'此模型尚無匯入照明檢查紀錄；出圖時會先檢查場景，再試渲染。'}<br/>材質預覽使用展示燈光；光影預覽僅近似直接照明。以低解析 Cycles 試圖確認整體光照，檢查通過後仍需人工確認品質。</span></div>}
    {step===0&&<>
      <main className={(intake==='dxf'||intake==='image')&&!importPending?'studio-intake plan-intake-project':'studio-intake'}>
      {!importPending&&intake==='choose'&&<><ImportStart disabled={!!busy||dirty} examples={examples} onFile={chooseFile} onExample={openExample}/>{dirty&&<p>目前有未保存的編輯，請先返回編輯頁保存。</p>}{projectInfo&&(scene||projectInfo.revision||intakeJob||projectInfo.has_intake||projectInfo.configured)&&<div className="intake-resume"><span>{projectInfo.name}</span><button disabled={!!busy} onClick={()=>void perform('繼續設計',continueIntake)}>{scene?'返回目前編輯':'繼續上次設計 →'}</button></div>}</>}
      {!importPending&&intake==='glb'&&<><h2>開啟 3D 模型</h2><p>可返回匯入頁，重新選擇 GLB／SKP 或開啟 Project04 範例，檔案上限 512 MB。</p><button onClick={()=>setIntake('choose')}>返回匯入方式</button></>}
      {importPending&&job&&<div className="plan-empty" role="status"><h2>{['queued','running'].includes(job.status)?'正在準備模型與交接檢查':'模型工作結果'}</h2><p>{job.status==='running'?'本機處理模型，核對 GLB／BLEND 的物件與尺度…':job.status==='queued'?'等待本機工作佇列':job.status}</p>{job.error&&<p>{job.error}</p>}<p>{intake==='glb'?'完成後直接進入原模型出圖／網站。':'完成後進入配置與編輯。'}原始檔已保存。</p>{!['queued','running'].includes(job.status)&&<button onClick={()=>setImportPending(false)}>返回匯入設定</button>}</div>}
      </main>
      {!importPending&&intake==='image'&&<ImageImport model={model} setModel={setModel} key={project} project={project} baseRevision={revision||projectInfo?.revision||null} onBuilt={(job,base)=>receivePlanJob(job,base)} onBack={()=>setIntake('choose')}/>}
      {!importPending&&intake==='dxf'&&<PlanImport model={model} setModel={setModel} key={project} project={project} baseRevision={revision||projectInfo?.revision||null} onBuilt={(job,base)=>receivePlanJob(job,base)} onBack={()=>setIntake('choose')}/>}
    </>}
    {scene&&previewJob&&step===1&&<RealismPreview project={project} jobId={previewJob} revision={revision} onClose={()=>setPreviewJob(null)}/>}
    {scene&&<div hidden={(step!==1&&step!==5)||!!previewJob&&step===1}><SpaceEditor kind={step===5?'decor':'furniture'} revision={revision} dirty={dirty} model={model} onSave={save} onAccept={accept} active={(step===1&&!previewJob)||step===5} canUndo={!!history.length} onUndo={undo} key={project} scene={scene} project={project} busy={!!busy} onChange={changeScene} onCandidate={id=>perform('交給 Agent 整理候選',()=>candidate(id))} onContinue={()=>setStep(2)}/></div>}
    {scene&&step===6&&<DoorEditor revision={revision} dirty={dirty} model={model} onSave={save} onAccept={accept} previewJob={previewJob} project={project} scene={scene} busy={!!busy} canUndo={!!history.length} onUndo={undo} onChange={changeScene}/>}
    {scene&&<div hidden={step!==3}><ViewpointEditor revision={revision} active={step===3} canUndo={!!history.length} onUndo={undo} key={project+scene.model_id} scene={scene} project={project} busy={!!busy} onChange={changeScene} onContinue={()=>perform('確認編輯設定',()=>confirmDesign(true))}/></div>}
    {scene&&<div hidden={step!==2}><LightEditor model={model} onAccept={accept} onContinue={()=>setStep(3)} active={step===2} canUndo={!!history.length} onUndo={undo} key={project} scene={scene} project={project} revision={revision} dirty={dirty} busy={!!busy} onChange={changeScene} onSave={save}/></div>}
    {scene&&step===4?<main className="studio-results-workspace">{step===4&&<div className="studio-results"><div className="section-heading"><h2>你的渲染成果</h2><button onClick={()=>setStep(2)}>調整照明</button><button onClick={()=>perform('更新成果',refreshOutputs)}>重新整理</button></div>{!readyForRender&&<div className="confirm-card"><p>目前版本尚未完成編輯確認。點「建立出圖工作」可檢查缺少哪些設定。</p><button onClick={()=>setStep(3)}>返回觀看點設定</button></div>}<section className="lighting-panel"><label className="inline-check"><input type="checkbox" checked={realismEnabled} disabled={workflow?.status==='rendering'} onChange={e=>{setRealismEnabled(e.target.checked);if(!realismPoint)setRealismPoint(scene.viewpoints.find(p=>p.shots.length)?.id||'');}}/>寫實化精修 · Agent 試圖與回修</label>{realismEnabled&&<><label>精修範圍<select aria-label="精修範圍" value={realismAll?"all":"point"} disabled={workflow?.status==='rendering'} onChange={e=>setRealismAll(e.target.value==='all')}><option value="point">選定空間</option><option value="all">全案所有觀看點</option></select></label><label className="inline-check"><input type="checkbox" checked={prepareOpenings} disabled={workflow?.status==='rendering'} onChange={e=>setPrepareOpenings(e.target.checked)}/>沿用平面洞口補齊門窗概念模型</label><label>{realismAll?"02 預覽起點":"試作觀看點"} <select aria-label="寫實精修觀看點" value={realismPoint} disabled={workflow?.status==='rendering'} onChange={e=>setRealismPoint(e.target.value)}>{scene.viewpoints.filter(p=>p.shots.length).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><details><summary>既有需求與本次精修重點</summary><label>需求紀錄<textarea aria-label="精修需求紀錄" maxLength={12000} value={realismBrief} disabled={workflow?.status==='rendering'} onChange={e=>setRealismBrief(e.target.value)} placeholder="貼上物件名稱、已確認用途、來源與精修重點；僅提出預覽，不更改已確認尺寸。"/></label><p className="muted">用途不明先查紀錄；有明確分層書架需求且為單一方塊時，才試作等外框概念層架。家電型號與施工細節不自行假定。</p></details><p>Agent 依原生模型與實際試圖修整材質、窗景、櫃體細節與取景，最多兩輪；保留前後比較並標示取景變更，採用後再出正式圖。</p><p className="muted">使用目前選定的 Codex 模型看圖。必要家具與已確認尺寸保持，全景眼位不變；日光調整可能影響其他空間，會列在紀錄中。</p></>}</section><label className="inline-check"><input type="checkbox" checked={!realismEnabled&&sceneReview} disabled={realismEnabled||workflow?.status==='rendering'} onChange={e=>setSceneReview(e.target.checked)}/>整屋試圖 → Agent 看圖 → 自動修正重驗（最多三輪）</label><p className="muted">啟用後將試圖與場景摘要交給目前選定的 Codex 模型；只修正有問題且允許調整的部分。未通過時保留預覽，不直接出正式圖。</p><div className="render-options"><select aria-label="渲染品質" disabled={realismEnabled} value={realismEnabled?'preview':quality} onChange={e=>setQuality(e.target.value)}><option value="preview">低解析預覽 · 先確認構圖</option><option value="final">正式尺寸 · 4K 全景 / 1600 寬效果圖（依畫幅）</option></select><button ref={renderButton} className="primary" disabled={!!busy||workflow?.status==='rendering'||(workflow?.status==='awaiting_confirmation'&&workflow.revision===revision&&!dirty)} onClick={()=>perform('整理出圖設定',createRender)}>建立出圖工作</button></div>{workflow?.status==='awaiting_confirmation'&&<div className="confirm-card"><h3>確認這次出圖</h3>{workflow.scene_review&&<p>先進行整屋試圖與 Agent 複查；尚有問題則保留預覽。自動調整不覆寫目前編輯。</p>}<p>{workflow.realism_point_id?(workflow.realism_all?'全案觀看點的基準與精修試圖（最多兩輪）':'選定觀看點的基準與精修試圖（最多兩輪）'):`${scene.viewpoints.length} 張全景 ＋ ${scene.viewpoints.reduce((n,p)=>n+p.shots.length,0)} 張效果圖`} · {workflow.quality==='preview'?'低解析預覽':'正式尺寸'}</p><p>設定版本 {workflow.revision.slice(0,8)} · {scene.lighting_setup?.enabled?'自訂照明與試圖檢查':'原模型照明'}</p><button className="primary" disabled={!readyForRender||workflow.revision!==revision} onClick={()=>perform('提交渲染',async()=>{setWorkflow(await api<Workflow>(`/workflows/${workflow.run_id}/resume`,'POST',{base_revision:workflow.revision,confirmation_id:workflow.confirmation_id}));})}>確認並開始渲染</button><button onClick={()=>perform('停止流程',async()=>{setWorkflow(await api<Workflow>(`/workflows/${workflow.run_id}/stop`,'POST'));})}>取消</button></div>}{workflow&&workflow.status!=='awaiting_confirmation'&&<div className="render-progress"><b>{workflow.status==='completed'?(workflow.realism_point_id?'寫實精修試作完成 · 請比較預覽':workflow.scene_review?'本次試圖工作完成 · 請查看檢查結果':'本次渲染完成'):workflow.status==='rendering'?'本機渲染中':workflow.status}</b><span>{workflow.error||(job?.progress&&workflow.status!=='completed'?`${job.progress.completed} / ${job.progress.total}　${job.progress.current}`:'')}</span>{workflow.status==='rendering'&&<button onClick={()=>perform('停止工作',async()=>{if(workflow.job_id){await api(`/jobs/${workflow.job_id}/stop-lighting`,'POST');setNotice('已要求停止後續調整，目前出圖完成後才停止。');}else setWorkflow(await api<Workflow>(`/workflows/${workflow.run_id}/stop`,'POST'));})}>停止／取消排隊</button>}</div>}{revision&&<OutputCleanup key={project} project={project} revision={revision} outputs={outputs} disabled={!!busy||dirty||workflow?.status==='rendering'} onChange={refreshOutputs}/>}{workflow?.job_id&&workflow.scene_review&&<SceneReviewRun project={project} jobId={workflow.job_id} revision={revision} dirty={dirty} onNavigate={setStep} onAdopt={r=>{accept(r);setConfirmedRevision(null);setNotice('已採用調整並保存新修訂，請重新確認編輯。');}}/>}{workflow?.job_id&&workflow.realism_point_id&&<RealismRun onPreview={()=>{setPreviewJob(workflow.job_id!);setStep(1);}} project={project} jobId={workflow.job_id} revision={revision} dirty={dirty} onAdopt={r=>{accept(r);setConfirmedRevision(null);setNotice('精修已保存為新修訂，請重新確認編輯後出圖。');}}/>}{workflow?.job_id&&scene&&!workflow.scene_review&&!workflow.realism_point_id&&<LightingRun project={project} jobId={workflow.job_id} onAdopt={(setup,base)=>{if(base!==revision||dirty){setError('設定已變更，不能套用過期照明。');return;}changeScene({...scene,lighting_setup:setup});setStep(2);setNotice('已帶回照明，請保存並重新確認觀看點。');}}/>}<label className="old-toggle"><input type="checkbox" checked={showOld} onChange={e=>setShowOld(e.target.checked)}/>包含舊修訂成果</label>{!visibleOutputs.length&&<div className="results-empty">尚無此修訂的成圖。先用低解析確認視角與材質。</div>}<div className="output-grid">{visibleOutputs.map(o=><button className="output-card" key={o.job_id+o.file} onClick={()=>setView(o)}><img src={fileUrl(project,o.job_id,o.thumbnail)} alt={o.name}/><strong>{o.name}</strong><span>{o.kind==='panorama'?'360° 全景':'效果圖'} · {o.width} × {o.height}</span><small>{o.realism_status?'寫實化試作 · 請比較後確認':o.scene_review_status==='needs_attention'?'試圖 · 仍有待確認問題':o.stale?'舊修訂 · 待更新':o.quality==='preview'?'低解析預覽':'正式尺寸'}</small></button>)}</div></div>}</main>:null}
    </div></div>

    {preflight&&<RenderPreflightDialog returnFocus={renderButton} issues={preflight} onClose={()=>setPreflight(null)} onNavigate={target=>{setPreflight(null);setStep(target);}}/>}
    {exitOpen&&<dialog ref={exitDialog} className="project-exit-dialog" aria-label="返回專案首頁前保存" onCancel={e=>{e.preventDefault();cancelExit();}}><h2>有尚未保存的修改</h2><p>保存後返回可保留這次調整；捨棄只會放棄目前草稿，已保存版本仍保留。</p>{exitError&&<p role="alert">{exitError}</p>}<div className="project-exit-actions"><button disabled={exitBusy} onClick={cancelExit}>取消</button><button disabled={exitBusy} onClick={onHome}>捨棄未保存修改並返回</button><button disabled={exitBusy||!canSaveDrafts()} onClick={()=>void saveAndHome()}>保存後返回</button></div>{!canSaveDrafts()&&<small>部分內容仍在處理，或尚無保存功能；請先在原頁面完成處理，或選擇捨棄草稿。</small>}</dialog>}
    {view&&<div className="studio-modal" role="dialog" aria-modal="true" aria-label={view.name}><div className="modal-content"><div className="section-heading"><h3>{view.name}</h3><button onClick={()=>setView(null)}>關閉 ×</button></div>{view.kind==='panorama'?<Panorama url={fileUrl(project,view.job_id,view.file)}/>:<img src={fileUrl(project,view.job_id,view.file)} alt={view.name}/>}<p>{view.kind==='panorama'?'拖曳環視 360° · ':''}設定版本 {view.revision.slice(0,8)}　<a href={fileUrl(project,view.job_id,view.file)} download={view.file}>下載原圖 ↗</a></p></div></div>}
    <footer className="studio-footer">設計由你確認，流程由工作室接續。<span>本機單使用者 · Blender / Cycles</span></footer>
  </div></EditorWorkspace></ViewportProvider></IncompleteRepairProvider></ProjectDraftContext.Provider>;
}
