import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {useProjectDraft} from './ProjectDraft';
import type {Job} from './api';
import './planImport.css';
import PlanSemantics from './PlanSemantics';
import ImportScaleDialog from './ImportScaleDialog';
import type {CadPreparationReport} from './CadPreparation';
import type {QuestionNote,SourceMark} from './QuestionReview';
import {buildBlockers} from './planReview.mjs';
import LayoutDesign from './LayoutDesign';
import {FloorReportView} from './FloorContinuity';
import type {FloorReport} from './FloorContinuity';
import type {EvidenceAudit} from './EvidenceReview';

type Role='ignore'|'wall'|'floor'|'door'|'window'|'furniture';
type Assignment={id:string;name:string;role:Role;height:number;base:number;thickness:number;offset:[number,number];host_id:string|null;points?:[number,number][]|null;design_asset?:string|null};
type Feature={id:string;layer:string;points:[number,number][];closed:boolean;kind:string};
type Calibration={start:[number,number];end:[number,number];metres:number;confirmed:boolean};
type Binding={dimension_id:string;start:{feature_id:string;vertex:number};end:{feature_id:string;vertex:number};axis:'x'|'y';mode?:string};
type DimensionRow={dimension_id:string;text:string;metres:number;status:'applied'|'conflict'|'pending';measured_m:number|null;difference_m:number|null;bindings:Binding[];cautions:{reason:string;source:string}[]};
type IntakeReport={status:string;errors:string[];rooms:{id:string;name:string}[];counts:Record<string,number>;furniture_state:string;layout_mode:string};
export type Settings={intake_review?:{purposes:boolean;structure:boolean;furniture:boolean}|null;cad_unit_confirmed?:boolean;cad_unit_evidence?:string;source_marks?:SourceMark[];question_notes?:QuestionNote[];reconstruction?:{orthogonal:boolean;changed_features:number;bindings:Binding[];note:string}|null;additions?:Feature[];calibration?:Calibration|null;reviewed?:string[];units:'mm'|'cm'|'m'|'inch'|'foot';assignments:Assignment[]};
type Check={intake?:IntakeReport;floor_continuity?:FloorReport;dimension_report?:DimensionRow[];status:string;errors:string[];warnings:string[];counts:Record<string,number>;ignored:number};
export type Plan={id:string;revision:string;source:{name:string;original?:{name:string};conversion?:{tool:string}};parsed:{intake_semantics?:{rooms:{id:string;name:string}[];furniture_state:string;door_state:string;window_state:string};cad_preparation?:CadPreparationReport;image?:{width:number;height:number};scale_evidence?:string;questions?:{id:string;text:string;feature_ids?:string[]}[];notes?:string[];dimensions?:{id:string;text:string;raw_text?:string|null;source_refs?:string[];metres:number|null;endpoint_evidence:string;confidence:string}[];recognition_audit?:{evidence_review?:EvidenceAudit|null;review_complete:boolean;agent_changes?:{name:string;reason:string}[];corrections:{name:string;reason:string}[];dimension_residuals:{id:string;text:string;measured_m:number;scaled_m:number;difference_m:number}[]};features:Feature[];detected_units:string|null;issues:unknown[];annotations:Record<string,number>};settings:Settings;check:Check};
const labels:Record<Role,string>={ignore:'略過',wall:'牆體',floor:'地板／室內範圍',door:'門洞',window:'窗洞',furniture:'家具占位'};
export default function PlanImport({model,setModel,project,baseRevision,onBuilt,onBack,initialPlan,onNewImage}:{model:string;setModel:(model:string)=>void;onNewImage?:()=>void;initialPlan?:Plan;project:string;baseRevision:string|null;onBuilt:(job:Job,base:string|null)=>Promise<void>;onBack:()=>void}){
  const [plan,setPlan]=useState<Plan|null>(initialPlan||null),[settings,setSettings]=useState<Settings|null>(initialPlan?.settings||null);
  const [busy,setBusy]=useState(''),[error,setError]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [discard,setDiscard]=useState<'back'|'image'|null>(null);
  const [stage,setStage]=useState<'plan'|'design'|'build'>('plan'),[designBusy,setDesignBusy]=useState(false),[semanticBusy,setSemanticBusy]=useState(false);
  const layoutBusy=designBusy||semanticBusy;
  function leave(target:'back'|'image'){if(dirty)setDiscard(target);else if(target==='image')onNewImage?.();else onBack();}
  const [calibrating,setCalibrating]=useState(false),[calibrationStart,setCalibrationStart]=useState<[number,number]|null>(null);
  const input=useRef<HTMLInputElement>(null),running=useRef(false),loadVersion=useRef(0);
  useEffect(()=>{if(initialPlan)return;let alive=true;const version=++loadVersion.current;void api<Plan|null>(`/projects/${project}/plans/current`).then(async p=>{if(alive&&version===loadVersion.current&&p&&!p.parsed.image){if(!p.parsed.cad_preparation){setBusy('自動整理 CAD 平面…');try{p=await api<Plan>(`/projects/${project}/plans/${p.id}/prepare`,'POST',{base_revision:p.revision});}finally{if(alive)setBusy('');}}if(alive&&version===loadVersion.current){setPlan(p);setSettings(p.settings);}}}).catch(e=>{if(alive&&version===loadVersion.current)setError(e.message);});return()=>{alive=false;};},[project,initialPlan]);
  const dirty=!!plan&&JSON.stringify(settings)!==JSON.stringify(plan.settings);
  useProjectDraft({label:'平面確認',dirty:dirty||calibrating,blocked:!!busy||layoutBusy||calibrating,save:async()=>{if(!plan||!settings)return;accept(await api<Plan>(`/projects/${project}/plans/${plan.id}`,'PUT',{base_revision:plan.revision,settings}));}});
  const intake=plan?.check.intake||{status:'blocked',errors:['請先完成用途區域與牆門窗判讀。'],rooms:[],counts:{},furniture_state:'uncertain',layout_mode:'review_first'};
  const blockers=plan&&settings?buildBlockers({image:!!plan.parsed.image,settings,questions:plan.parsed.questions||[],dirty,calibrating,busy,confirmed,check:plan.check,intake}):[];
  function jump(id:string){setStage(id==='plan-layout'?'design':['plan-validation','plan-consent','build-reasons'].includes(id)?'build':'plan');requestAnimationFrame(()=>{const target=document.getElementById(id)||document.getElementById('plan-semantics');for(let p=target?.parentElement;p;p=p.parentElement)if(p instanceof HTMLDetailsElement)p.open=true;target?.scrollIntoView({behavior:'smooth',block:'center'});});}
  function changeStage(next:'plan'|'design'|'build'){setStage(next);requestAnimationFrame(()=>document.getElementById('plan-stage-nav')?.scrollIntoView({block:'start',behavior:'smooth'}));}
  async function perform(label:string,work:()=>Promise<void>){if(running.current||layoutBusy)return;running.current=true;setBusy(label);setError('');try{await work();}catch(e){setError((e as Error).message);}finally{setBusy('');running.current=false;}}
  function accept(p:Plan){setPlan(p);setSettings(p.settings);setConfirmed(false);}
  const image=plan?.parsed.image;
  const picker={active:calibrating,points:calibrationStart?[calibrationStart]:!plan?.settings.calibration?.confirmed&&settings?.calibration?[settings.calibration.start,settings.calibration.end]:[],onPoint:(point:[number,number])=>{if(!settings)return;if(!calibrationStart)setCalibrationStart(point);else{setSettings({...settings,calibration:{start:calibrationStart,end:point,metres:settings.calibration?.metres||1,confirmed:false}});setCalibrating(false);setCalibrationStart(null);setConfirmed(false);setScaleOpen(true);}}};
  const needsScale=!!plan&&(image?!plan.settings.calibration?.confirmed:!!plan.parsed.cad_preparation&&!plan.settings.cad_unit_confirmed);
  const [scaleOpen,setScaleOpen]=useState(false);
  useEffect(()=>setScaleOpen(needsScale),[plan?.id,needsScale]);
  return <section className="plan-intake" aria-label="平面確認">
    <div className="plan-heading"><div><small>{image?'圖片辨識 → 平面確認 → 3D':'電子平面 → 3D'}</small><h2>{plan?'確認平面與建模條件':'匯入電子平面'}</h2></div><button onClick={()=>leave('back')} disabled={!!busy||layoutBusy}>返回匯入方式</button></div>
    {discard&&<div className="studio-banner" role="alertdialog" aria-label="未保存修改提醒"><p>尚有未保存的平面修改。離開會捨棄這些修改，已保存版本仍保留。</p><button onClick={()=>setDiscard(null)}>繼續編輯</button><button onClick={()=>{const target=discard;setDiscard(null);if(target==='image')onNewImage?.();else onBack();}}>捨棄未保存修改並離開</button></div>}

    {plan&&<><nav className="plan-stage-nav" id="plan-stage-nav" aria-label="匯入處理階段">{([['plan','1','核對平面'],['design','2','家具配置'],['build','3','建立 3D']] as const).map(([id,n,title])=><button key={id} type="button" aria-current={stage===id?'step':undefined} disabled={!!busy||layoutBusy} onClick={()=>changeStage(id)}><b>{n}</b>{title}<small>{id==='plan'?(dirty?'有未保存修改':plan.check.status==='ready'?'已通過概念檢查':'待核對'):id==='design'?(intake.layout_mode==='preserve'?'沿用原圖家具':intake.layout_mode==='generate'?'原圖未配置 · AI 設計':'先完成用途判讀'):'確認後才建模'}</small></button>)}</nav>
      <div className="plan-savebar"><span>{dirty?'有未保存修改':intake.status==='ready'?'匯入交接已核對':plan.check.status==='ready'?'幾何已通過，仍需核對用途與牆門窗':'平面已保存，仍有檢查問題'}</span><button id="plan-save" disabled={!dirty||!!busy||layoutBusy} onClick={()=>perform('保存並檢查平面…',async()=>accept(await api<Plan>(`/projects/${project}/plans/${plan.id}`,'PUT',{base_revision:plan.revision,settings})))}>保存並檢查平面</button></div></>}

    {plan&&settings&&needsScale&&scaleOpen&&<ImportScaleDialog plan={plan} settings={settings} onChange={s=>{setSettings(s);setConfirmed(false);}} onClose={()=>setScaleOpen(false)} onPick={()=>{setScaleOpen(false);setCalibrating(true);setCalibrationStart(null);}} onSave={()=>void perform('保存匯入尺度…',async()=>accept(await api<Plan>(`/projects/${project}/plans/${plan.id}`,'PUT',{base_revision:plan.revision,settings})))} disabled={!!busy||layoutBusy}/>}
    {calibrating&&<p className="studio-banner" role="status">請在圖面選兩個端點。<button type="button" onClick={()=>{setCalibrating(false);setCalibrationStart(null);setScaleOpen(true);}}>取消選點</button></p>}
    <div className="plan-actions">{image&&onNewImage&&<button disabled={!!busy||layoutBusy} onClick={()=>leave('image')}>換一張圖片</button>}{!image&&<button disabled={!!busy||layoutBusy} onClick={()=>input.current?.click()}>{plan?'換一份 DWG／DXF':'選擇 DWG／DXF 檔案'}</button>}{plan&&<span>{plan.source.original?`${plan.source.original.name} → ${plan.source.name}`:plan.source.name}</span>}</div>
    <input ref={input} hidden type="file" accept=".dwg,.dxf" onChange={e=>{const file=e.target.files?.[0];if(file)void perform('讀取平面；DWG 會核對原生元件與轉檔…',async()=>{loadVersion.current+=1;const body=new FormData();body.append('file',file);const p=await api<Plan>(`/projects/${project}/plans/upload`,'POST',body);accept(p);});e.target.value='';}}/>
    {!plan&&<div className="plan-empty"><b>準備自己的圖面</b><p>ASCII DXF、模型空間、XY 平面。牆可以是中心線或封閉凸輪廓；地板與家具需封閉凸輪廓；門窗以沿牆直線表示洞口寬度。</p><p>圖層名稱 wall、floor、door、window、furniture 會提供用途建議；其他圖層由你指定。DWG 會先由本機 ODA 轉成 DXF，保留原始檔；SKP 尚未開放。圖片請返回選擇圖片入口。</p><p>測試範例：examples/from-dxf/project04-plan.dxf</p></div>}
    {(busy||error)&&<div className={'studio-banner '+(error?'error':'')} role="status">{error||busy}</div>}
    {plan&&settings&&<div className="plan-fields">
      <div id="plan-layout" hidden={stage!=='design'}>{intake.layout_mode==='preserve'?<section className="layout-readiness"><h3>沿用原圖家具配置</h3><p>原圖已辨識 {intake.counts.furniture||0} 件家具／設備。保留位置與圖面尺寸，不另行設計或自動刪除。</p><p>01 先建立概念外形；02 可新增、刪除或替換家具。</p></section>:intake.layout_mode==='review_first'?<p>請先於核對平面完成用途區域、牆門窗與原有家具判讀。</p>:<LayoutDesign model={model} setModel={setModel} project={project} plan={plan} dirty={dirty||calibrating||!!busy||semanticBusy} onAdopted={accept} onWorking={setDesignBusy} onReviewPlan={target=>jump(target||'plan-save')}/>}<button type="button" onClick={()=>changeStage('build')}>前往建模確認 →</button></div>
      <div hidden={stage!=='plan'} role="region" aria-label="核對平面階段">
      <div id="plan-semantics"><PlanSemantics model={model} setModel={setModel} plan={plan} project={project} dirty={dirty||!!busy||calibrating||designBusy} onReady={accept} onWorking={setSemanticBusy} onScale={()=>setScaleOpen(true)} scalePicker={image?picker:undefined}>
      {plan.parsed.intake_semantics&&<fieldset className="semantic-confirmation" disabled={!!busy||layoutBusy}><h3>逐項核對</h3><p>{intake.rooms.map(r=>r.name).join('、')}</p><p>牆 {intake.counts.wall||0} · 門 {intake.counts.door||0} · 窗 {intake.counts.window||0} · 家具／設備 {intake.counts.furniture||0}</p>{([['purposes','用途區域名稱與位置'],['structure','牆面、門與窗的位置；原圖未提供的已明確註記'],['furniture','原圖已有家具已保留；未配置家具會交由 AI 設計']] as const).map(([key,label])=><label key={key}><input type="checkbox" checked={!!settings.intake_review?.[key]} onChange={e=>{setSettings({...settings,intake_review:{purposes:false,structure:false,furniture:false,...settings.intake_review,[key]:e.target.checked}});setConfirmed(false);}}/>我已核對{label}</label>)}<small>勾選後請保存。概念高度不代表施工確認；未測量的高度可於 02 調整。</small></fieldset>}
      </PlanSemantics></div>

      <div className="plan-actions"><button type="button" className="primary" onClick={()=>changeStage('design')}>下一步：家具配置 →</button><button type="button" onClick={()=>changeStage('build')}>保留原配置，前往建模</button></div></div>
      <fieldset className="plan-fields" disabled={!!busy||layoutBusy} hidden={stage!=='build'} aria-label="建立 3D 階段"><div className="plan-validation" id="plan-validation"><h3>{dirty?'設定已變更，請重新保存檢查':plan.check.status==='ready'?'平面檢查通過':'尚有項目需要處理'}</h3>
        {plan.check.floor_continuity&&<details><summary>轉換自動檢查：補齊 {plan.check.floor_continuity.patches.length} 處地板短縫{plan.check.floor_continuity.remaining.length?` · ${plan.check.floor_continuity.remaining.length} 處邊界待核對`:''}</summary><FloorReportView value={plan.check.floor_continuity}/><small>建立 3D 時自動執行補齊與驗證，不需另外啟動。來源不明的區域保留；不更動已確認尺寸。</small></details>}
        <p>{Object.entries(plan.check.counts).map(([k,v])=>`${labels[k as Role]} ${v}`).join(' · ')} · 略過 {plan.check.ignored} 個元件</p>
        {!!Object.keys(plan.parsed.annotations).length&&<p>文字與尺寸標註僅保留在原 DXF，不生成 3D：{Object.entries(plan.parsed.annotations).map(([k,v])=>`${k} ${v}`).join('、')}。</p>}
        {dirty&&plan.check.errors.length>0&&<p>上次保存的問題如下；請保存以取得最新結果。</p>}{plan.check.errors.length>0&&<ul>{plan.check.errors.slice(0,20).map((e,i)=>{const a=settings.assignments.find(a=>e.startsWith(a.name+'：'));return <li key={i}>{e}{a&&<button type="button" onClick={()=>{jump('plan-semantics');}}>前往修正</button>}</li>;})}{plan.check.errors.length>20&&<li>另有 {plan.check.errors.length-20} 項，請先整理來源 DXF。</li>}</ul>}
        <p>本版建立概念模型：家具為占位、門為開口、窗為開口與簡易框；不建立天花。僅供下一階段編輯，不下載正式素材或執行渲染。</p>
        <p>這裡分別檢查幾何與匯入交接；原圖沒有家具時，必須先預覽並採用 AI 配置。舊模型與修訂保留。</p>
        <label className="plan-confirm" id="plan-consent"><input type="checkbox" checked={confirmed} disabled={calibrating||dirty||plan.check.status!=='ready'||intake.status!=='ready'||!!busy} onChange={e=>setConfirmed(e.target.checked)}/>我已確認單位、用途、略過項目與建模高度，接受上述概念模型範圍。</label>
        <div id="build-reasons" className="build-readiness" aria-live="polite"><b>{blockers.length?'目前不能建立 3D 的原因':'所有條件已完成，可以建立 3D'}</b><ul>{blockers.map((r:{target:string;text:string},i:number)=><li key={i}>{r.text} <button type="button" onClick={()=>jump(r.target)}>前往處理</button></li>)}</ul></div><button className="primary" aria-describedby="build-reasons" disabled={blockers.length>0} onClick={()=>perform('建立 3D 工作…',async()=>{const job=await api<Job>(`/projects/${project}/plans/${plan.id}/build`,'POST',{plan_revision:plan.revision,base_revision:baseRevision,confirmed:true});await onBuilt(job,baseRevision);})}>確認平面，建立 3D →</button>
      </div></fieldset>
    </div>}
  </section>;
}
