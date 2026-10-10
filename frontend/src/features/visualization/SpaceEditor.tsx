import {useEffect,useState} from 'react';
import type {Scene} from './api';
import {fileUrl} from './api';
import SpaceViewport from './SpaceViewport';
import type {ViewMode} from './SpaceViewport';

export default function SpaceEditor({scene,project,onChange,onCandidate,onContinue,busy,active,canUndo,onUndo}:{active:boolean;canUndo:boolean;onUndo:()=>void;scene:Scene;project:string;onChange:(scene:Scene)=>void;onCandidate:(id:string)=>void;onContinue:()=>void;busy:boolean}){
  const [mode,setMode]=useState<ViewMode>('plan'),[selected,setSelected]=useState(scene.groups.find(g=>!g.deleted)?.id||''),[child,setChild]=useState(''),[moving,setMoving]=useState(false),[search,setSearch]=useState('');
  const [contrast,setContrast]=useState(true);
  const [showDeleted,setShowDeleted]=useState(false);
  useEffect(()=>{if(active){setMode('plan');setChild('');setMoving(false);}},[active]);
  useEffect(()=>{if(!scene.groups.some(g=>g.id===selected)){setSelected(scene.groups.find(g=>!g.deleted)?.id||'');setChild('');}},[scene.groups,selected]);
  const group=scene.groups.find(g=>g.id===selected),part=scene.objects.find(o=>o.id===child);
  const groups=scene.groups.filter(g=>(showDeleted||!g.deleted||g.id===selected)&&g.name.toLowerCase().includes(search.toLowerCase()));
  function edit(change:(draft:Scene)=>void){const draft=structuredClone(scene);change(draft);onChange(draft);}
  function select(id:string,partId?:string){setSelected(id);setChild(partId||'');}
  function inspect(){if(!group||group.deleted)return;setMoving(false);setMode('object');}
  function material(change:(m:Scene['objects'][number]['material'])=>void){if(part)edit(s=>change(s.objects.find(o=>o.id===part.id)!.material));}
  return <section className="space-editor">
    <div className="space-navigation" role="tablist" aria-label="空間檢視方式">
      <button role="tab" aria-selected={mode==='plan'} onClick={()=>{setMode('plan');setChild('');}}>2D 平面圖</button>
      <button role="tab" aria-selected={mode==='walk'} onClick={()=>{setMode('walk');setChild('');}}>3D 畫面</button>
      {group&&!group.deleted&&<button role="tab" aria-selected={mode==='object'} onClick={inspect}>3D 單物件展示</button>}
      {mode==='plan'&&<label className="plan-contrast"><input type="checkbox" checked={contrast} onChange={e=>setContrast(e.target.checked)}/>平面辨識模式</label>}
      <span>{scene.groups.filter(g=>!g.deleted).length} 個單物件 · {scene.objects.length} 個組成</span>
      <button disabled={!canUndo||busy} onClick={onUndo}>復原上一步</button>
    </div>
    <div className="space-editor-grid">
      <div>{active&&<SpaceViewport planContrast={contrast} url={fileUrl(project,scene.model_id,'model.glb')} design={scene} mode={mode} selected={selected} child={child} moving={moving} onSelect={select} onInspect={id=>{select(id);setMoving(false);setMode('object');}} onMove={(id,delta)=>edit(s=>{s.groups.find(g=>g.id===id)!.translation=delta;})}/>}
        <div className="space-bottom"><span>{mode==='object'?`${group?.name||''} · 只顯示此單物件`:mode==='plan'&&contrast?'平面不套用場景光照；柔化地板、保留家具色彩與邊線，實際材質不變。':'平面與 3D 共用同一模型，修改後請保存。'}</span><button className="primary" disabled={busy} onClick={onContinue}>設定光影 →</button></div>
      </div>
      <aside className="studio-inspector assembly-inspector">
        <h3>{mode==='object'?'單物件與子物件':'選取單物件'}</h3>
        {mode!=='object'&&<><input aria-label="搜尋單物件" placeholder="搜尋椅子、桌子、牆面…" value={search} onChange={e=>setSearch(e.target.value)}/><select size={6} aria-label="單物件清單" value={selected} onChange={e=>select(e.target.value)}><option value="" disabled>點選畫面或選擇單物件</option>{groups.map(g=><option value={g.id} key={g.id}>{g.deleted?'已刪除 · ':''}{g.name} · {g.children.length} 個組成</option>)}</select><label className="inline-check"><input type="checkbox" checked={showDeleted} onChange={e=>setShowDeleted(e.target.checked)}/>顯示已刪除物件</label></>}
        {!group&&<p>點選平面圖或 3D 中的家具，整張椅子會一起選取。不同椅子各自獨立。</p>}
        {group&&<><label>單物件名稱<input value={group.name} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.name=e.target.value;})}/></label><p className="muted">{group.children.length} 個子物件 · {group.method==='source_id'?'依模型來源分組':group.method==='hierarchy'?'依模型階層分組':group.method==='name_prefix'?'依物件命名分組':'獨立物件，未推測合併'}</p>
          <div className="object-actions"><button disabled={group.deleted||mode==='object'} className={moving?'primary':''} aria-pressed={moving} onClick={()=>setMoving(!moving)}>{moving?'結束移動':'移動模式'}</button><button disabled={group.deleted} onClick={inspect}>單物件導覽</button><button className="danger" onClick={()=>{edit(s=>{s.groups.find(g=>g.id===group.id)!.deleted=!group.deleted;});setMoving(false);if(mode==='object')setMode('plan');}}>{group.deleted?'還原物件':'刪除物件'}</button></div>
          {moving&&<><p>拖曳画面彩色軸／平面，或輸入相對匯入位置的位移。</p><div className="coordinates">{['X','Y','Z'].map((label,i)=><label key={label}>{label} 位移（m）<input aria-label={`${label} 位移`} type="number" step="0.1" value={group.translation[i]} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.translation[i]=Number(e.target.value);})}/></label>)}</div></>}
          <label>歸屬空間<select value={scene.objects.find(o=>o.id===group.children[0])?.room_id||''} onChange={e=>edit(s=>{s.objects.filter(o=>group.children.includes(o.id)).forEach(o=>o.room_id=e.target.value||null);})}><option value="">待確認</option>{scene.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          {mode==='object'&&<><h4>組成與材質</h4><p>點選模型中的子物件，或從清單選擇。材質只套用到所選的組成。</p><select size={7} aria-label="子物件清單" value={child} onChange={e=>select(group.id,e.target.value)}><option value="" disabled>選擇子物件</option>{group.children.map(id=><option key={id} value={id}>{scene.objects.find(o=>o.id===id)?.name||id}</option>)}</select>
            {part&&<><label>子物件名稱<input value={part.name} onChange={e=>edit(s=>{s.objects.find(o=>o.id===part.id)!.name=e.target.value;})}/></label><label>材質描述<textarea value={part.material.description} placeholder="例如：椅腳改成霧黑金屬" onChange={e=>material(m=>m.description=e.target.value)}/></label><label>材質參考連結<input value={part.material.url} placeholder="https://…" onChange={e=>material(m=>m.url=e.target.value)}/></label><label>材質選擇<select aria-label="子物件材質選擇" value="" onChange={e=>{const presets:Record<string,[string,number,string]>={wood:['#b68d60',.65,'溫潤淺木色'],metal:['#353638',.35,'霧黑金屬'],fabric:['#a1aa9d',.9,'淺灰綠布料']};if(e.target.value==='original')material(m=>{m.color=null;});else{const [color,roughness,description]=presets[e.target.value];material(m=>{Object.assign(m,{color,roughness,description});});}}}><option value="" disabled>選擇基本材質…</option><option value="original">原材質</option><option value="wood">淺木色</option><option value="metal">霧黑金屬</option><option value="fabric">淺灰綠布料</option></select></label><div className="material-controls"><label>基本色<input type="color" value={part.material.color||'#d2c7b8'} onChange={e=>material(m=>m.color=e.target.value)}/></label><label>粗糙度<input type="number" min="0" max="1" step="0.05" value={part.material.roughness} onChange={e=>material(m=>m.roughness=Number(e.target.value))}/></label></div><button className="primary" disabled={busy} onClick={()=>onCandidate(part.id)}>請 Agent 整理候選</button><p className="muted">基本色／粗糙度即時預覽；連結記為需求，不會自動下載貼圖。</p></>}
          </>}
        </>}
        <details className="space-names"><summary>空間名稱管理</summary>{scene.rooms.map(r=><label key={r.id}>空間名稱<input value={r.name} onChange={e=>edit(s=>{s.rooms.find(x=>x.id===r.id)!.name=e.target.value;})}/></label>)}<button onClick={()=>edit(s=>{s.rooms.push({id:'room-'+crypto.randomUUID().slice(0,8),name:'新空間'});})}>＋ 新增空間</button></details>
      </aside>
    </div>
  </section>;
}
