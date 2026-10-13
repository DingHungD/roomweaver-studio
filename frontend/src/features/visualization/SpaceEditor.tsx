import AssetConstraints from './AssetConstraints';
import {EditorTools,EditorInspector} from './EditorWorkspace';
import type {ReactNode} from 'react';
import EditorToolbar from './EditorToolbar';
import {useEffect,useRef,useState} from 'react';
import AddFurniture from './AddFurniture';
import type {Addition} from './AddFurniture';
import {addPlacedItem,isDecoration} from './placementArea';
import type {PlacementArea} from './placementArea';
import AssetMatcher from './AssetMatcher';
import AssetBatch from './AssetBatch';
import StagingPanel from './StagingPanel';
import {mergeGroups} from './mergeGroups';
import type {Scene,Revision} from './api';
import {api,fileUrl} from './api';
import SpaceViewport from './SpaceViewport';
import type {ViewMode} from './SpaceViewport';

export default function SpaceEditor({kind='furniture',scene,project,onChange,onCandidate,onContinue,busy,active,canUndo,onUndo,revision,dirty,model,onSave,onAccept}:{kind?:'furniture'|'decor';revision:string|null;dirty:boolean;model:string;onSave:()=>Promise<string|null|undefined>;onAccept:(r:Revision)=>void;active:boolean;canUndo:boolean;onUndo:()=>void;scene:Scene;project:string;onChange:(scene:Scene)=>void;onCandidate:(id:string)=>void;onContinue:()=>void;busy:boolean}){
  const [mode,setMode]=useState<ViewMode>('plan'),[selected,setSelected]=useState(scene.groups.find(g=>!g.deleted)?.id||''),[child,setChild]=useState(''),[moving,setMoving]=useState(false),[search,setSearch]=useState('');
  const [placementDraw,setPlacementDraw]=useState<{groupId:string;kind:'area'|'keep_out'}|null>(null);
  const [adding,setAdding]=useState(false),[drawing,setDrawing]=useState(false),[area,setArea]=useState<PlacementArea|null>(null),[addingBusy,setAddingBusy]=useState(false),[additionError,setAdditionError]=useState('');
  const remembered=useRef<Record<string,string>>({});
  const [transformMode,setTransformMode]=useState<'translate'|'rotate'>('translate');
  const [mergeIds,setMergeIds]=useState<string[]>([]),[mergeError,setMergeError]=useState('');
  const selectionCenter=useRef<[number,number,number]>([0,0,0]);
  function rotate(angle:number){if(!group)return;edit(s=>{const g=s.groups.find(x=>x.id===group.id)!;g.rotation_pivot=g.rotation_pivot&&g.rotation?g.rotation_pivot:selectionCenter.current.map((n,i)=>n-g.translation[i]) as [number,number,number];g.rotation=angle;});}
  const [contrast,setContrast]=useState(false);
  const [matchTask,setMatchTask]=useState('');
  const [showDeleted,setShowDeleted]=useState(false);
  const latest=useRef(scene);latest.current=scene;
  const currentKind=useRef(kind);currentKind.current=kind;
  const planCenter=useRef<[number,number]>([0,0]);
  useEffect(()=>{if(active){setMode('plan');setChild('');setMoving(false);}},[active]);
  useEffect(()=>{setAdding(false);setDrawing(false);setArea(null);setMode('plan');setMoving(false);setChild('');setMatchTask('');setSearch('');setAdditionError('');setSelected(remembered.current[kind]||scene.groups.find(g=>!g.deleted&&(kind!=='decor'||isDecoration(scene,g)))?.id||'');},[kind]);
  useEffect(()=>{if(!scene.groups.some(g=>g.id===selected)){setSelected(scene.groups.find(g=>!g.deleted&&(kind!=='decor'||isDecoration(scene,g)))?.id||'');setChild('');setMoving(false);}},[scene.groups,selected]);
  const group=scene.groups.find(g=>g.id===selected&&(kind!=='decor'||isDecoration(scene,g))),part=scene.objects.find(o=>o.id===child);
  useEffect(()=>{if(child&&!group?.children.includes(child))setChild('');},[group,child]);
  const groups=scene.groups.filter(g=>(kind!=='decor'||isDecoration(scene,g))&&(showDeleted||!g.deleted||g.id===selected)&&g.name.toLowerCase().includes(search.toLowerCase()));
  function edit(change:(draft:Scene)=>void){const draft=structuredClone(scene);change(draft);onChange(draft);}
  function select(id:string,partId?:string){if(kind==='decor'&&!scene.groups.some(g=>g.id===id&&isDecoration(scene,g)))return;remembered.current[kind]=id;if(id!==selected)setMatchTask('');setSelected(id);setChild(partId||'');}
  function inspect(){if(!group||group.deleted)return;setMoving(false);setMode('object');}
  function material(change:(m:Scene['objects'][number]['material'])=>void){if(part)edit(s=>change(s.objects.find(o=>o.id===part.id)!.material));}
  async function addItem(value:Addition){
    if(!revision)throw new Error('請先開啟並保存設計');
    const original=latest.current;
    const next=addPlacedItem(original,value.furniture,value.position,kind,value.prompt,value.url,value.room);
    setAddingBusy(true);setAdditionError('');
    try{
      const saved=await api<Revision>(`/projects/${project}/scene`,'PUT',{base_revision:revision,scene:next});
      if(latest.current!==original){setAdditionError('元件已保存，但畫面有其他修改。請核對後重新開啟已保存設計。');return;}
      onAccept(saved);setSelected(value.furniture.id);remembered.current[kind]=value.furniture.id;setChild('');setMoving(false);setAdding(false);setDrawing(false);setArea(null);setMode(value.action==='concept'?'plan':'object');setMatchTask('');
      if(value.action!=='concept'){
        try{const task=await api<{id:string}>(`/projects/${project}/${value.action==='link'?'asset-links':'asset-matches'}`,'POST',{base_revision:saved.revision,group_id:value.furniture.id,object_id:null,kind:'model',description:value.prompt,model:model||null,operation_id:crypto.randomUUID().replaceAll('-',''),...(value.action==='link'?{url:value.url}:{})});if(currentKind.current===kind)setMatchTask(task.id);}
        catch(e){setAdditionError('元件已保存，模型尚未載入：'+(e as Error).message+'。可在此單物件重新搜尋或查核連結。');}
      }
    }finally{setAddingBusy(false);}
  }
  const manualAddButton=(locked=false)=><button className="primary" disabled={locked||busy||addingBusy} onClick={()=>{setAdding(true);setDrawing(true);setArea(null);setMode('plan');setMoving(false);setAdditionError('');}}>＋ 新增{kind==='decor'?'裝飾物':'家具'}</button>;
  const toolbar=(configure:ReactNode,locked=false,status?:ReactNode)=><EditorToolbar views={<>
      <button role="tab" aria-selected={mode==='plan'} onClick={()=>{setMode('plan');setChild('');}}>2D 平面圖</button>
      <button role="tab" aria-selected={mode==='walk'} onClick={()=>{setMode('walk');setChild('');}}>3D 畫面</button>
      {group&&!group.deleted&&<button role="tab" aria-selected={mode==='object'} onClick={inspect}>3D 單物件展示</button>}
    </>} actions={<>{manualAddButton(locked)}{configure}<button disabled={(kind==='decor'&&locked)||!canUndo||busy||(kind==='decor'&&addingBusy)} onClick={onUndo}>復原上一步</button></>}>
      {mode==='plan'&&<label className="plan-contrast"><input type="checkbox" checked={contrast} onChange={e=>setContrast(e.target.checked)}/>加強輪廓辨識</label>}
      <span>{scene.groups.filter(g=>!g.deleted).length} 個單物件 · {scene.objects.length} 個組成</span>
      {status&&<span>{status}</span>}
    </EditorToolbar>;
  return <section className="space-editor"><EditorTools>
    {kind==='decor'?<StagingPanel kind="decor" project={project} scene={scene} revision={revision} dirty={dirty} busy={busy||addingBusy} model={model} onSave={onSave} onAccept={onAccept} toolbar={(configure,locked)=>toolbar(configure,locked)}/>:<AssetBatch toolbar={(configure,status)=>toolbar(configure,false,status)} onAccept={onAccept} project={project} scene={scene} revision={revision} dirty={dirty} model={model} busy={busy} onSave={onSave} onInspect={(gid,pid,task)=>{select(gid,pid||undefined);setMatchTask(task);setMoving(false);setMode('object');}}/>}
    {kind==='furniture'&&<p className="addition-toolbar-help">框選範圍後填寫需求，或指定 BlenderKit 模型網址。</p>}
    {placementDraw&&<p role="status">在平面拖曳框選{placementDraw.kind==='area'?'允許移動區域':'通道／門保留區'}。Esc 取消；完成後請核對右側最多移動距離並保存。</p>}
    {additionError&&<p role="alert">{additionError}</p>}
    </EditorTools><div className="space-editor-grid">
      <div>{active&&<SpaceViewport areaEditing={drawing||!!placementDraw} placementArea={adding?area:group?.placement_constraints?.area?{center:[(group.placement_constraints.area[0]+group.placement_constraints.area[2])/2,(group.placement_constraints.area[1]+group.placement_constraints.area[3])/2],size:[group.placement_constraints.area[2]-group.placement_constraints.area[0],group.placement_constraints.area[3]-group.placement_constraints.area[1]],height:0}:null} onArea={a=>{if(placementDraw){const rect:[number,number,number,number]=[a.center[0]-a.size[0]/2,a.center[1]-a.size[1]/2,a.center[0]+a.size[0]/2,a.center[1]+a.size[1]/2];edit(s=>{const g=s.groups.find(g=>g.id===placementDraw.groupId);if(!g||g.deleted)return;const c=g.placement_constraints||{area:null,max_distance:0,keep_out:[]};g.placement_constraints=placementDraw.kind==='area'?{...c,area:rect}:{...c,keep_out:[...c.keep_out,rect]};});setPlacementDraw(null);}else{setArea(a);setDrawing(false);}}} onAreaCancel={()=>{setDrawing(false);setPlacementDraw(null);}} key={scene.groups.map(g=>g.id+':'+g.children.join(',')).join('|')} transformMode={transformMode} onSelectionCenter={p=>{selectionCenter.current=p;}} onRotate={(_id,angle)=>rotate(angle)} onPlanCenter={xy=>{planCenter.current=xy;}} planContrast={contrast} url={fileUrl(project,scene.model_id,'model.glb')} design={scene} mode={mode} selected={selected} child={child} moving={moving&&!adding&&!addingBusy} onSelect={select} onInspect={id=>{if(kind==='decor'&&!scene.groups.some(g=>g.id===id&&isDecoration(scene,g)))return;select(id);setMoving(false);setMode('object');}} onMove={(id,delta)=>edit(s=>{s.groups.find(g=>g.id===id)!.translation=delta;})}/>}
        <div className="space-bottom"><span>{mode==='object'?`${group?.name||''} · 只顯示此單物件`:mode==='plan'?contrast?'輪廓辨識：簡化地板與光影，實際材質不變。':'柔光平面：保留材質、柔和陰影與室內置中；預覽光不影響出圖。':'平面與 3D 共用同一模型，修改後請保存。'}</span><button className="primary" disabled={busy} onClick={onContinue}>設定光源 →</button></div>
      </div>
      <EditorInspector>
        {adding&&<AddFurniture key={kind} kind={kind} area={area} drawing={drawing} onDraw={()=>{setMode('plan');setMoving(false);setDrawing(true);}} onCancel={()=>{setAdding(false);setDrawing(false);setArea(null);}} getCenter={()=>planCenter.current} scene={scene} busy={busy||addingBusy} onAdd={addItem}/>}
        <fieldset disabled={busy||addingBusy} hidden={adding} style={{border:0,padding:0,margin:0,minWidth:0}}>

        {!!scene.design_notes?.length&&<details><summary>概念配置尚待核對（{scene.design_notes.length}）</summary><ul>{scene.design_notes.map((n,i)=><li key={i}>{n}</li>)}</ul></details>}
        {kind==='furniture'&&group&&<details><summary>合併成單物件</summary><p>例如將同一馬桶的盆體與水箱合為一件，保留原幾何。保留目前選取名稱，可於下方修改。</p><select multiple size={4} aria-label="要合併的組件" value={mergeIds} onChange={e=>setMergeIds(Array.from(e.target.selectedOptions,o=>o.value))}>{scene.groups.filter(g=>g.id!==selected&&!g.deleted).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select><button disabled={busy||!mergeIds.length} onClick={()=>{try{onChange(mergeGroups(scene,selected,mergeIds));setMergeIds([]);setMergeError('');}catch(e){setMergeError((e as Error).message);}}}>合併選取組件</button>{mergeError&&<p role="alert">{mergeError}</p>}</details>}
        <h3>{mode==='object'?'單物件與子物件':'選取單物件'}</h3>
        {mode!=='object'&&<><input aria-label="搜尋單物件" placeholder="搜尋椅子、桌子、牆面…" value={search} onChange={e=>setSearch(e.target.value)}/><select size={6} aria-label="單物件清單" value={selected} onChange={e=>select(e.target.value)}><option value="" disabled>點選畫面或選擇單物件</option>{groups.map(g=><option value={g.id} key={g.id}>{g.deleted?'已刪除 · ':''}{g.name} · {g.children.length} 個組成</option>)}</select><label className="inline-check"><input type="checkbox" checked={showDeleted} onChange={e=>setShowDeleted(e.target.checked)}/>顯示已刪除物件</label></>}
        {!group&&<p>{kind==='decor'?'點「框選新增裝飾物」加入元件，或選擇現有裝飾物；背景家具供定位。':'點選平面圖或 3D 中的家具，整張椅子會一起選取。不同椅子各自獨立。'}</p>}
        {group&&<><AssetConstraints group={group} onDraw={kind=>{setPlacementDraw({groupId:group.id,kind});setMode('plan');setMoving(false);setAdding(false);setDrawing(false);}} onPlacement={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.placement_constraints=value;})} onChange={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.asset_requirements=value;})}/><label>單物件名稱<input value={group.name} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.name=e.target.value;})}/></label><p className="muted">{group.children.length} 個子物件 · {group.method==='structural_wall'?'整屋牆壁群組，雙擊可細調':group.method==='structural_floor'?'整屋地板群組，雙擊可細調':group.method==='blenderkit'?'BlenderKit 家具組成':group.method==='concept'?'通用概念家具組成':group.method==='source_id'?'依模型來源分組':group.method==='hierarchy'?'依模型階層分組':group.method==='name_prefix'?'依物件命名分組':'獨立物件，未推測合併'}</p>
          <div className="object-actions"><button disabled={group.deleted||mode==='object'} className={moving?'primary':''} aria-pressed={moving} onClick={()=>setMoving(!moving)}>{moving?'結束調整':'移動／旋轉'}</button><button disabled={group.deleted} onClick={inspect}>單物件／BlenderKit 配對</button><button className="danger" onClick={()=>{edit(s=>{s.groups.find(g=>g.id===group.id)!.deleted=!group.deleted;});setMoving(false);if(mode==='object')setMode('plan');}}>{group.deleted?'還原物件':'刪除物件'}</button></div>
          {moving&&<><label>調整方式<select value={transformMode} onChange={e=>{setTransformMode(e.target.value as 'translate'|'rotate');}}><option value="translate">平移</option><option value="rotate">水平旋轉</option></select></label>{transformMode==='rotate'?<><p>拖曳旋轉環或輸入角度；家具保持直立，綁定光源一起旋轉。</p><label>旋轉角度（°）<input type="number" min="-360" max="360" step="5" value={group.rotation||0} onChange={e=>rotate(Number(e.target.value))}/></label><div className="object-actions">{[-90,90].map(n=><button key={n} onClick={()=>rotate(((group.rotation||0)+n+540)%360-180)}>{n>0?'+90°':'−90°'}</button>)}</div></>:<><p>拖曳畫面彩色軸／平面，或輸入相對匯入位置的位移。</p><div className="coordinates">{['X','Y','Z'].map((label,i)=><label key={label}>{label} 位移（m）<input aria-label={`${label} 位移`} type="number" step="0.1" value={group.translation[i]} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.translation[i]=Number(e.target.value);})}/></label>)}</div></>}</>}
          <label>歸屬空間<select value={scene.objects.find(o=>o.id===group.children[0])?.room_id||''} onChange={e=>edit(s=>{s.objects.filter(o=>group.children.includes(o.id)).forEach(o=>o.room_id=e.target.value||null);})}><option value="">待確認</option>{scene.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          {mode==='object'&&<><AssetMatcher taskId={matchTask} onSelectPart={id=>select(group.id,id)} key={project+group.id} project={project} group={group} part={part} revision={revision} dirty={dirty} model={model} busy={busy} onSave={onSave} onAccept={onAccept}/><h4>組成與材質</h4><p>點選模型中的子物件，或從清單選擇。材質只套用到所選的組成。</p><select size={7} aria-label="子物件清單" value={child} onChange={e=>select(group.id,e.target.value)}><option value="" disabled>選擇子物件</option>{group.children.map(id=><option key={id} value={id}>{scene.objects.find(o=>o.id===id)?.name||id}</option>)}</select>
            {part&&<><label>子物件名稱<input value={part.name} onChange={e=>edit(s=>{s.objects.find(o=>o.id===part.id)!.name=e.target.value;})}/></label><label>材質描述<textarea value={part.material.description} placeholder="例如：椅腳改成霧黑金屬" onChange={e=>material(m=>m.description=e.target.value)}/></label><label>材質參考連結<input value={part.material.url} placeholder="https://…" onChange={e=>material(m=>m.url=e.target.value)}/></label><label>材質選擇<select aria-label="子物件材質選擇" value="" onChange={e=>{const presets:Record<string,[string,number,string]>={wood:['#b68d60',.65,'溫潤淺木色'],metal:['#353638',.35,'霧黑金屬'],fabric:['#a1aa9d',.9,'淺灰綠布料']};if(e.target.value==='original')material(m=>{m.color=null;});else{const [color,roughness,description]=presets[e.target.value];material(m=>{Object.assign(m,{color,roughness,description});});}}}><option value="" disabled>選擇基本材質…</option><option value="original">原材質</option><option value="wood">淺木色</option><option value="metal">霧黑金屬</option><option value="fabric">淺灰綠布料</option></select></label><div className="material-controls"><label>基本色<input type="color" value={part.material.color||'#d2c7b8'} onChange={e=>material(m=>m.color=e.target.value)}/></label><label>粗糙度<input type="number" min="0" max="1" step="0.05" value={part.material.roughness} onChange={e=>material(m=>m.roughness=Number(e.target.value))}/></label></div><button className="primary" disabled={busy} onClick={()=>onCandidate(part.id)}>請 Agent 整理候選</button><p className="muted">基本色／粗糙度即時預覽；連結記為需求，不會自動下載貼圖。</p></>}
          </>}
        </>}
        <details className="space-names"><summary>空間名稱管理</summary>{scene.rooms.map(r=><label key={r.id}>空間名稱<input value={r.name} onChange={e=>edit(s=>{s.rooms.find(x=>x.id===r.id)!.name=e.target.value;})}/></label>)}<button onClick={()=>edit(s=>{s.rooms.push({id:'room-'+crypto.randomUUID().slice(0,8),name:'新空間'});})}>＋ 新增空間</button></details>
        </fieldset>
      </EditorInspector>
    </div>
  </section>;
}
