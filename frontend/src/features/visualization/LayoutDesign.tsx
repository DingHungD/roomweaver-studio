import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {Plan} from './PlanImport';
import {layoutBlockers} from './layoutReadiness.mjs';
import LayoutSourceReview from './LayoutSourceReview';
import type {QuestionNote} from './QuestionReview';
import {bindCanvasWheel} from './canvasWheel.mjs';

type Item={id:string;name:string;role:string;points:number[][];closed:boolean;thickness:number};
type Proposal={summary:string;placements:{id:string;target_id:string|null;name:string;asset:string;reason:string;rotation:number}[];routes:{name:string;points:number[][];width:number;reason:string}[];use_zones:{name:string;points:number[][];purpose:string;kind?:string}[];coverage:{requirement_id:string;status:string;reason:string}[];assumptions:string[];questions:string[]};
type Report={hard_errors?:string[];floor_patches?:{points:number[][];holes:number[][][]}[];status:string;errors:string[];warnings:string[];baseline_issues?:string[];furniture:{id:string;points:number[][];changed:boolean}[];routes:{name:string;length:number;width:number;blocked:boolean;inferred_floor?:boolean}[]};
type Brief={id:string;base_revision:string;brief:string;requirements:string[];context:string;sources:{label:string;reference:string;sha256:string}[]};
type Run={id:string;source_revision:string;repair?:{source_questions?:QuestionNote[];rationale:string;previous_error_count:number;sources:{label:string;reference:string}[]};request:{brief_id?:string|null;brief:string;requirements:string[];movable_ids:string[];passage_width:number;model:string};site:{excluded_floor_ids?:string[];items:Item[];requirements:{id:string;text:string}[]};task:{source_questions?:QuestionNote[];status:string;phase?:string;error?:string;recovery_note?:string;candidate?:Proposal;layout_report?:Report};adoption?:{revision:string}|null};

export default function LayoutDesign({project,plan,dirty,onAdopted,onWorking,onReviewPlan}:{project:string;plan:Plan;dirty:boolean;onAdopted:(plan:Plan)=>void;onWorking:(working:boolean)=>void;onReviewPlan:(target?:string)=>void}){
  const [run,setRun]=useState<Run|null>(null),[brief,setBrief]=useState(''),[needs,setNeeds]=useState(''),[movable,setMovable]=useState<string[]>([]),[width,setWidth]=useState(.8);
  const [models,setModels]=useState<{id:string;displayName:string}[]>([]),[model,setModel]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState(''),[accept,setAccept]=useState(false);
  const [caseBrief,setCaseBrief]=useState<Brief|null>(null),[useBrief,setUseBrief]=useState(true);
  const [zoom,setZoom]=useState(1),[pan,setPan]=useState<[number,number]>([0,0]);
  const [showRoutes,setShowRoutes]=useState(true),[showZones,setShowZones]=useState(false);
  const canvas=useRef<SVGSVGElement>(null),lock=useRef(false),operation=useRef<{key:string;id:string}|null>(null),drag=useRef<{x:number;y:number;pan:[number,number]}|null>(null);
  const waiting=!!run&&['queued','running','stopping'].includes(run.task.status),proposal=run?.task.candidate,report=run?.task.layout_report;
  const stale=!!run&&run.source_revision!==plan.revision&&run.adoption?.revision!==plan.revision;
  const endpoint=`/projects/${project}/plans/${plan.id}/layout`;
  async function work(label:string,fn:()=>Promise<void>){if(lock.current)return;lock.current=true;onWorking(true);setBusy(label);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy('');lock.current=false;onWorking(false);}}
  useEffect(()=>{let alive=true;setRun(null);setBrief('');setNeeds('');setMovable([]);setWidth(.8);setModel('');setError('');setCaseBrief(null);setUseBrief(true);operation.current=null;
    void Promise.all([api<Run|null>(endpoint+'/current'),api<Brief|null>(endpoint+'/brief')]).then(([r,b])=>{if(!alive)return;setRun(r);setCaseBrief(b);if(r){setBrief(r.request.brief);setNeeds(r.request.requirements.join('\n'));setMovable(r.request.movable_ids);setWidth(r.request.passage_width);setModel(r.request.model);setUseBrief(!!r.request.brief_id);}else if(b){setBrief(b.brief);setNeeds(b.requirements.join('\n'));}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[endpoint]);
  useEffect(()=>{setAccept(false);},[plan.revision,dirty,run?.id]);
  useEffect(()=>{if(!waiting||!run)return;let active=true;const timer=setInterval(()=>{void api<Run>(endpoint+'/'+run.id).then(r=>{if(active)setRun(r);}).catch(e=>{if(active)setError(e.message);});},2000);return()=>{active=false;clearInterval(timer);};},[endpoint,run?.id,waiting]);
  useEffect(()=>canvas.current?bindCanvasWheel(canvas.current,(f:number)=>setZoom(z=>Math.min(5,Math.max(.5,z*f)))):undefined,[run?.id,!!proposal]);
  const items=run?.site.items||[],floor=items.filter(a=>a.role==='floor'&&!run?.site.excluded_floor_ids?.includes(a.id)).flatMap(a=>a.points);
  const minX=floor.length?Math.min(...floor.map(p=>p[0])):0,minY=floor.length?Math.min(...floor.map(p=>p[1])):0;
  const w=floor.length?Math.max(...floor.map(p=>p[0]))-minX:1,h=floor.length?Math.max(...floor.map(p=>p[1]))-minY:1;
  const fit=500/Math.max(w,h,1),xy=(p:number[])=>[50+(p[0]-minX)*fit,50+(minY+h-p[1])*fit];
  const points=(pts:number[][])=>pts.map(p=>xy(p).join(',')).join(' ');
  const disabled=dirty||plan.check.status!=='ready'||!!busy||waiting||run?.task.status!=='passed';
  const reasons=layoutBlockers({dirty,planStatus:plan.check.status,errors:plan.check.errors,busy:!!busy,waiting,brief,needs,model,width,contextStale:!!caseBrief&&useBrief&&caseBrief.base_revision!==plan.revision});
  function locate(target:string){if(target.startsWith('plan-')){onReviewPlan(target);return;}document.getElementById(target)?.focus();document.getElementById(target)?.scrollIntoView({block:'center',behavior:'smooth'});}
  return <section className="layout-designer" id="ai-space-layout" aria-label="AI 空間配置">
    <h3>AI 空間配置 · 家具與生活動線</h3><p>確認平面 → 說明生活需求 → Agent 提案與自動檢查 → 預覽採用 → 建立 3D。此步可選；已有滿意配置可直接建模。</p>
    <p>沿用需求承接、固定牆門窗保全、家具操作區與動線檢查。新增家具是通用概念模型；尚未接商品搜尋、施工設計或自動法規認證。</p>
    {dirty&&<p className="studio-banner">平面有未保存修改，請先保存並檢查，再提出或採用配置。</p>}
    {plan.check.status!=='ready'&&<p className="studio-banner">先處理平面檢查問題，才能讓 Agent 依正確尺度配置。</p>}
    <details className="layout-request" open={!proposal}><summary>生活需求與 Agent 設定{caseBrief?' · 已載入本案需求':''}</summary>
    {caseBrief&&<section className="layout-context" id="layout-context" tabIndex={-1}><p>已有 {caseBrief.requirements.length} 項需求與 {caseBrief.sources.length} 份來源紀錄，已帶入下方欄位，不必重新輸入。</p><label><input type="checkbox" checked={useBrief} disabled={waiting||!!busy} onChange={e=>setUseBrief(e.target.checked)}/>沿用這份需求包的確認紀錄與背景</label><details><summary>查看來源、既有確認及仍待核對的對應</summary><ul>{caseBrief.sources.map((r,i)=><li key={i}>{r.label}<small>{r.reference}</small></li>)}</ul><p style={{whiteSpace:'pre-wrap'}}>{caseBrief.context}</p></details></section>}
    <div className="layout-brief"><label>生活需求與設計方向<textarea id="layout-brief-input" value={brief} maxLength={4000} onChange={e=>setBrief(e.target.value)} disabled={waiting||!!busy} placeholder="例如：兩人居住，一人需要固定在家工作；保留床與廚具，希望增加收納，入口到座位不要繞路。"/></label>
      <label>必須滿足的項目（每行一項）<textarea id="layout-needs-input" value={needs} onChange={e=>setNeeds(e.target.value)} disabled={waiting||!!busy} placeholder={'保留既有床的尺寸\n增加一張工作桌與可拉出的椅子\n主要通道保持暢通'}/></label>
      <label>主要通道的設計目標（m）<input id="layout-width-input" type="number" min={.5} max={2} step={.05} value={width} disabled={waiting||!!busy} onChange={e=>setWidth(Number(e.target.value))}/><small>這是你的配置目標，並非法規判定；Agent 不得自行降低。</small></label>
      <details><summary>允許 Agent 移動哪些既有家具？（預設全部保留）</summary>{plan.settings.assignments.filter(a=>a.role==='furniture').map(a=><label key={a.id}><input type="checkbox" checked={movable.includes(a.id)} disabled={waiting||!!busy} onChange={e=>setMovable(e.target.checked?[...movable,a.id]:movable.filter(id=>id!==a.id))}/>{a.name}</label>)}</details>
      <div className="plan-actions"><button type="button" disabled={waiting||!!busy} onClick={()=>work('連接 Codex…',async()=>{const result=await api<{authenticated:boolean;auth_type:string;models:{id:string;displayName:string}[]}>('/agent/status');if(!result.authenticated||result.auth_type!=='chatgpt')throw new Error('請先以 ChatGPT 登入本機 Codex');setModels(result.models);if(!result.models.some(m=>m.id===model))setModel(result.models[0]?.id||'');})}>連接配置 Agent</button><label>配置模型<select id="layout-model-input" value={model} disabled={waiting||!!busy} onChange={e=>setModel(e.target.value)}><option value="">選擇模型</option>{!models.length&&model&&<option value={model}>{model}（重新連接確認可用性）</option>}{models.map(m=><option key={m.id} value={m.id}>{m.displayName}</option>)}</select></label></div>
      <p>按下提案才會把本案平面座標、元件與需求送至 Codex，使用訂閱額度。一次最多提出 1 輪並依幾何結果修正 2 輪；不會自動採用。</p>
      <div className="layout-readiness" id="layout-status" role="status">{reasons.length?<><b>開始配置前還需要：</b><ul>{reasons.map((r:{target:string;text:string})=><li key={r.target}>{r.text} <button type="button" disabled={!!busy||waiting} onClick={()=>locate(r.target)}>前往處理</button></li>)}</ul></>:<p>需求與平面已備妥，可以開始提案；此操作不會採用或建立 3D。</p>}</div>
      <button type="button" className="primary" disabled={!!busy||waiting} aria-describedby="layout-status" onClick={()=>{if(reasons.length){locate(reasons[0].target);return;}void work('提交配置需求…',async()=>{const data={base_revision:plan.revision,brief:brief.trim(),requirements:needs.split('\n').map(s=>s.trim()).filter(Boolean),movable_ids:movable,passage_width:width,model,brief_id:useBrief?caseBrief?.id:null,parent_id:run?.task.candidate&&!stale&&run.request.requirements.join("\n")===needs?run.id:null};const key=JSON.stringify(data);if(!operation.current||operation.current.key!==key)operation.current={key,id:crypto.randomUUID()};const r=await api<Run>(endpoint,'POST',{...data,operation_id:operation.current.id});setRun(r);setAccept(false);operation.current=null;});}}>{reasons.length?'檢查開始配置的條件':run?'依目前需求重新提案':'請 Agent 配置空間與動線'}</button>
      {waiting&&<><p role="status">{run?.task.phase||'等待配置 Agent…'}</p><button type="button" disabled={!!busy||run?.task.status==='stopping'} onClick={()=>work('要求停止…',async()=>{setRun(await api<Run>(endpoint+'/'+run!.id+'/stop','POST'));})}>停止配置</button></>}
    </div></details>
    {(busy||error||run?.task.error)&&<p role="status" className="studio-banner">{error||run?.task.error||busy}</p>}
    {run&&['interrupted','stopped','failed'].includes(run.task.status)&&<p>本次配置未完成，不會自動重送；可修改需求後重新提案。</p>}
    {run?.task.recovery_note&&<p className="studio-banner">{run.task.recovery_note}</p>}
    {stale&&<p className="studio-banner">平面版本已改變，此提案僅供參考，不能套用；請重新提案。</p>}
    {proposal&&report&&<div className="layout-proposal"><h4>{run?.adoption?'已採用的配置':'配置候選，尚未修改你的平面'}</h4><p>{proposal.summary}</p><p>{proposal.placements.length} 項家具配置 · {proposal.routes.length} 條生活動線 · {proposal.coverage.length} 項需求逐項對照</p>
      {run?.repair&&<section className="layout-context"><b>對照紀錄後的修正版 · {run.repair.previous_error_count} → {report.errors.length} 項硬性衝突{report.routes.some(r=>r.inferred_floor&&!r.blocked)?`，另有 ${report.routes.filter(r=>r.inferred_floor&&!r.blocked).length} 條路線待核對銜接`:""}</b><p>家具與需求保留，修正版獨立保存；原候選與平面沒有被覆蓋。這是 Agent 輔助修正後的程式重驗，不代表設計已通過。</p><details><summary>已處理事項與引用的確認紀錄</summary><p style={{whiteSpace:'pre-wrap'}}>{run.repair.rationale}</p><ul>{run.repair.sources.map((s,i)=><li key={i}>{s.label}<small>{s.reference}</small></li>)}</ul></details></section>}
      {!!report.floor_patches?.length&&<p className="studio-banner">青色短縫是預覽推導的地板銜接，原圖未改。使用這些區域的路線標為「待核對」，不算已通過，也不能直接採用建模。</p>}
      <div className="plan-actions"><span>灰色：原有固定配置 · 藍色：新增／移動家具 · 橘色：操作區 · 綠／紅：動線及其寬度</span><button type="button" onClick={()=>{setZoom(1);setPan([0,0]);}}>配置圖置中</button></div>
      <div className="plan-actions"><label><input type="checkbox" checked={showRoutes} onChange={e=>setShowRoutes(e.target.checked)}/>顯示生活動線</label><label><input type="checkbox" checked={showZones} onChange={e=>setShowZones(e.target.checked)}/>顯示家具操作區</label><small>家具編號對照圖下清單；指向家具可查看名稱。</small></div>
      <svg ref={canvas} className="layout-preview" role="img" aria-label="AI 家具配置與動線預覽" viewBox="0 0 600 600" onPointerDown={e=>{drag.current={x:e.clientX,y:e.clientY,pan};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!drag.current)return;const scale=600/e.currentTarget.getBoundingClientRect().width;setPan([drag.current.pan[0]+(e.clientX-drag.current.x)*scale,drag.current.pan[1]+(e.clientY-drag.current.y)*scale]);}} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
        <g transform={`translate(${300+pan[0]} ${300+pan[1]}) scale(${zoom}) translate(-300 -300)`}>
          {items.filter(a=>a.role==='floor').map(a=><polygon key={a.id} points={points(a.points)} fill="#eee9de" stroke="#ddd5c6"/>)}
          {report.floor_patches?.map((patch,i)=><path key={`patch-${i}`} d={[patch.points,...patch.holes].map(r=>'M'+r.map(p=>xy(p).join(' ')).join(' L')+' Z').join(' ')} fillRule="evenodd" fill="#56c9d0" stroke="#147c87" strokeWidth={1} strokeDasharray="3 2"><title>推導銜接，待核對</title></path>)}
          {items.filter(a=>a.role==='wall').map(a=>a.closed?<polygon key={a.id} points={points(a.points)} fill="#56625c"/>:<polyline key={a.id} points={points(a.points)} fill="none" stroke="#56625c" strokeWidth={a.thickness*fit}/>)}
          {items.filter(a=>a.role==='door'||a.role==='window').map(a=><polyline key={a.id} points={points(a.points)} fill="none" stroke={a.role==='door'?'#fffdf8':'#55b6cb'} strokeWidth={Math.max(6,a.thickness*fit+2)}/>)}
          {showZones&&proposal.use_zones.map((z,i)=><polygon key={i} points={points(z.points)} fill={z.kind==='seated'?'#7796cc':'#edb353'} fillOpacity={.25} stroke="#ab731c" strokeDasharray="4 3"><title>{z.name}：{z.kind==='seated'?'座位占用區（不是淨空通道）。':''}{z.purpose}</title></polygon>)}
          {showRoutes&&proposal.routes.map((r,i)=><g key={i}><polyline points={points(r.points)} fill="none" stroke={report.routes[i]?.blocked?'#bb3b36':report.routes[i]?.inferred_floor?'#168996':'#3d9f74'} strokeWidth={r.width*fit} opacity={.22}/><polyline points={points(r.points)} fill="none" stroke={report.routes[i]?.blocked?'#bb3b36':report.routes[i]?.inferred_floor?'#168996':'#237752'} strokeWidth={2} strokeDasharray="6 4"/><title>{r.name} · {r.width} m</title></g>)}
          {report.furniture.map(f=>{const index=proposal.placements.findIndex(p=>(p.target_id||p.id)===f.id),label=proposal.placements[index]?.name||items.find(a=>a.id===f.id)?.name;const center=xy([f.points.reduce((v,p)=>v+p[0],0)/f.points.length,f.points.reduce((v,p)=>v+p[1],0)/f.points.length]);return <g key={f.id}><polygon points={points(f.points)} fill={f.changed?'#8abacb':'#b9beb4'} stroke={f.changed?'#226d86':'#667261'} strokeWidth={2}/><text x={center[0]} y={center[1]} textAnchor="middle" dominantBaseline="middle" fontSize={10} fill="#183942">{index>=0?String(index+1).padStart(2,'0'):'固定'}</text><title>{label}</title></g>;})}
        </g>
      </svg>
      <ol className="layout-key">{proposal.placements.map((p,i)=><li key={p.id}><b>{String(i+1).padStart(2,'0')}</b>{p.name}</li>)}</ol>
      {!!proposal.questions.length&&<section className="layout-context" aria-label="需要你確認的項目"><h4>需要你確認的項目（{proposal.questions.length}）</h4><p>其餘檢查問題仍由配置與轉錄流程處理；不是要求你刪除必要家具。</p><ol>{proposal.questions.map((q,i)=><li key={i}>{q}</li>)}</ol></section>}
      {!!(run?.repair?.source_questions||run?.task.source_questions)?.length&&plan.parsed.image&&<LayoutSourceReview key={run.id} endpoint={endpoint+'/'+run.id} revision={plan.revision} notes={(run.repair?.source_questions||run.task.source_questions)!} image={plan.parsed.image} imageUrl={`/api/studio/projects/${project}/image-plans/${plan.id}/image`} stale={stale}/>}
      <p><b>{report.status==='ready'?'提供的幾何檢查通過，仍需審閱設計':`提案有 ${report.errors.length} 項待修正事項；${(report.hard_errors?.length??report.errors.length)>0?"先處理穿牆／重疊等硬性問題":"可確認為概念家具區域，後續仍須調整"}`}</b></p>
      {!!report.errors.length&&<details className="layout-issues"><summary>查看家具與動線問題（{report.errors.length}）</summary><ul>{report.errors.map((e,i)=><li key={i}>{proposal.placements.reduce((text,p)=>text.replaceAll(p.id,p.name),e)}</li>)}</ul></details>}
      {!!report.baseline_issues?.length&&<details><summary>現有平面本身的限制（{report.baseline_issues.length}）</summary><ul>{report.baseline_issues.map((e,i)=><li key={i}>{e}</li>)}</ul></details>}
      <details><summary>需求如何被滿足</summary><ul>{proposal.coverage.map(c=><li key={c.requirement_id}><b>{run?.site.requirements.find(r=>r.id===c.requirement_id)?.text}</b>：{c.status==='addressed'?'已提出方案':'尚未滿足'} · {c.reason}</li>)}</ul></details>
      <details><summary>家具配置理由與動線</summary><ul>{proposal.placements.map(p=><li key={p.id}>{p.name}：{p.reason}</li>)}{report.routes.map((r,i)=><li key={i}>{r.name} · {r.blocked?'受阻':r.inferred_floor?'待核對地板銜接':'幾何通行檢查通過'} · 長 {r.length} m／寬 {r.width} m · {proposal.routes[i]?.reason}</li>)}</ul></details>
      <details><summary>設計假設與檢查限制</summary><ul>{[...proposal.assumptions,...report.warnings].map((s,i)=><li key={i}>{s}</li>)}</ul></details>
      {run?.task.status==='preview'&&<p className="studio-banner">本輪只供預覽，採用入口維持關閉；紅色動線與未解操作空間仍需修正。</p>}
      {!run?.adoption&&<><label><input type="checkbox" checked={accept} onChange={e=>setAccept(e.target.checked)} disabled={disabled||stale||(report.hard_errors?.length??report.errors.length)>0}/>我已檢視家具區域與未解事項，只採用為概念模型；動線問題仍需在02編輯調整，不代表設計驗收。</label><button type="button" className="primary" disabled={disabled||stale||!accept||(report.hard_errors?.length??report.errors.length)>0} onClick={()=>work('採用並另存平面…',async()=>{const next=await api<Plan>(endpoint+'/'+run!.id+'/adopt','POST',{base_revision:plan.revision,accept_assumptions:true,accept_layout_limits:report.status!=='ready'});onAdopted(next);setRun(await api<Run>(endpoint+'/'+run!.id));setAccept(false);})}>採用家具區域，另存概念平面</button></>}
      {run?.adoption&&<p>已另存為平面修訂。下方重新確認建模即可建立 3D；既有模型與原件保留。</p>}
    </div>}
  </section>;
}
