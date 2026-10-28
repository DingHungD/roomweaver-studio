import {useEffect,useId,useState} from 'react';
import type {ObjectGroup,Revision,Scene,StudioObject} from './api';
import type {ViewMode} from './SpaceViewport';
import type {IncompleteItem} from './configurationIncomplete';
import AssetConstraints from './AssetConstraints';
import AssetMatcher from './AssetMatcher';
import {IncompleteDetail} from './IncompleteItems';
import {mergeGroups} from './mergeGroups';
import {objectStyle} from './objectStyles';
import './materialInspector.css';

type Page='main'|'others'|'placement'|'materials'|'ai'|'candidates';
type Props={styleSyncUnavailable?:string;scene:Scene;group?:ObjectGroup;part?:StudioObject;mode:ViewMode;project:string;revision:string|null;dirty:boolean;model:string;busy:boolean;
  taskId:string;incomplete:IncompleteItem[];legacyStyles:Record<string,string>;size?:[number,number,number];moving:boolean;transformMode:'translate'|'rotate';
  onTransform:(mode:'translate'|'rotate')=>void;onRotate:(angle:number)=>void;onDelete:()=>void;onInspect:()=>void;onSelect:(id:string,part?:string)=>void;
  onChange:(scene:Scene)=>void;onStyleChange:(id:string,value:string)=>void;onDraw:(kind:'area'|'keep_out')=>void;onCandidate:(id:string)=>void;
  onSave:()=>Promise<string|null|undefined>;onAccept:(revision:Revision)=>void};

export default function MaterialInspector(p:Props){
  const {scene,group,part,mode}=p,single=mode==='object';
  const [page,setPage]=useState<Page>('main'),[search,setSearch]=useState(''),[deleted,setDeleted]=useState(false),[merge,setMerge]=useState<string[]>([]),[mergeError,setMergeError]=useState('');
  const prefix=useId();
  useEffect(()=>{setPage(single&&p.taskId?'candidates':'main');setMerge([]);setMergeError('');},[group?.id,single,p.taskId]);
  useEffect(()=>{if(single&&part)setPage('materials');},[part?.id]);
  const tabs:[Page,string][]=single?[['main','主畫面'],['materials','材質'],['ai','AI 設置'],['candidates','候選清單']]:[['main','主畫面'],['others','其他物件'],['placement','配置範圍']];
  const active=tabs.some(([id])=>id===page)?page:'main';
  const edit=(change:(draft:Scene)=>void)=>{const draft=structuredClone(scene);change(draft);p.onChange(draft);};
  const material=(change:(m:StudioObject['material'])=>void)=>{if(part)edit(s=>change(s.objects.find(o=>o.id===part.id)!.material));};
  const list=scene.groups.filter(g=>(deleted||!g.deleted)&&g.name.toLowerCase().includes(search.toLowerCase()));
  function tabKeys(e:React.KeyboardEvent<HTMLDivElement>){if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)||!(e.target as HTMLElement).matches('[role=tab]'))return;
    e.preventDefault();const index=tabs.findIndex(([id])=>id===active),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    setPage(tabs[next][0]);document.getElementById(`${prefix}-${tabs[next][0]}`)?.focus();
  }
  return <fieldset className="material-detail" disabled={p.busy}>
    <div className="material-detail-title">{group?<><label>物件名稱<input aria-label="單物件名稱" value={group.name} maxLength={200} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.name=e.target.value;})}/></label><small>{group.children.length} 個組成 · {group.method==='structural_wall'?'整屋牆壁群組':group.method==='structural_floor'?'整屋地板群組':'單物件'}</small>{single&&<details className="material-object-menu"><summary>物件操作</summary><button className="danger" onClick={p.onDelete}>{group.deleted?'還原物件':'刪除物件'}</button></details>}</>:<h3>尚未選取物件</h3>}</div>
    <div className="material-detail-tabs" role="tablist" aria-label="材質詳細編輯分頁" onKeyDown={tabKeys}>{tabs.map(([id,label])=><button key={id} type="button" role="tab" id={`${prefix}-${id}`} aria-controls={`${prefix}-panel`} aria-selected={active===id} tabIndex={active===id?0:-1} onClick={()=>setPage(id)}>{label}</button>)}</div>
    <div id={`${prefix}-panel`} role="tabpanel" aria-labelledby={`${prefix}-${active}`}>
      <IncompleteDetail item={p.incomplete.find(i=>i.id===group?.id)}/>
      {!single&&<section hidden={active!=='others'} aria-label="其他物件">
        <label>搜尋其他物件<input aria-label="搜尋單物件" placeholder="搜尋椅子、桌子、牆面…" value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <select size={6} aria-label="單物件清單" value={group?.id||''} onChange={e=>{p.onSelect(e.target.value);setPage('main');}}><option value="" disabled>選擇單物件</option>{list.map(g=><option key={g.id} value={g.id}>{g.deleted?'已刪除 · ':''}{g.name} · {g.children.length} 個組成</option>)}</select>
        {!list.length&&<p>沒有符合的物件。</p>}<label className="inline-check"><input type="checkbox" checked={deleted} onChange={e=>setDeleted(e.target.checked)}/>顯示已刪除物件</label>
        {group&&(<details><summary>合併成單物件</summary><p>合併同一家具的分散組件，保留原幾何及目前名稱。</p><select multiple size={4} aria-label="要合併的組件" value={merge} onChange={e=>setMerge(Array.from(e.target.selectedOptions,o=>o.value))}>{scene.groups.filter(g=>g.id!==group.id&&!g.deleted).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select><button disabled={!merge.length} onClick={()=>{try{p.onChange(mergeGroups(scene,group.id,merge));setMerge([]);setMergeError('');}catch(e){setMergeError((e as Error).message);}}}>合併選取組件</button>{mergeError&&<p role="alert">{mergeError}</p>}</details>)}
      </section>}
      {!group&&active==='main'&&<p>點選圖面中的物件，或到「其他物件」搜尋。</p>}
      {group&&<>
        <section hidden={active!=='main'}>
          {group.deleted&&<p role="status">物件已刪除，可在下方還原。</p>}
          {!single&&<>
            <label>歸屬空間<select value={scene.objects.find(o=>o.id===group.children[0])?.room_id||''} onChange={e=>edit(s=>{s.objects.filter(o=>group.children.includes(o.id)).forEach(o=>o.room_id=e.target.value||null);})}><option value="">待確認</option>{scene.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          <h4>目前模型尺寸</h4><div className="coordinates material-detail-size">{['寬','深','高'].map((name,i)=><label key={name}>{name} cm<input aria-label={`目前模型${name} cm`} readOnly value={p.size?(p.size[i]*100).toFixed(1):'—'}/></label>)}</div><small>模型本身尺寸；配置目標與已確認尺寸在單物件「AI 設置」。</small>
            <div className="object-actions material-detail-actions"><button disabled={group.deleted} aria-pressed={p.moving&&p.transformMode==='translate'} onClick={()=>p.onTransform('translate')}>移動</button><button disabled={group.deleted} aria-pressed={p.moving&&p.transformMode==='rotate'} onClick={()=>p.onTransform('rotate')}>旋轉</button><button className="danger" onClick={p.onDelete}>{group.deleted?'還原物件':'刪除物件'}</button></div>
            {p.moving&&(p.transformMode==='rotate'?<><label>旋轉角度（°）<input type="number" min="-360" max="360" step="5" value={group.rotation||0} onChange={e=>p.onRotate(Number(e.target.value))}/></label><div className="object-actions">{[-90,90].map(n=><button key={n} onClick={()=>p.onRotate(((group.rotation||0)+n+540)%360-180)}>{n>0?'+90°':'−90°'}</button>)}</div></>:<><p>拖曳彩色軸／平面，或輸入相對匯入位置的位移。</p><div className="coordinates">{['X','Y','Z'].map((name,i)=><label key={name}>{name} 位移（m）<input aria-label={`${name} 位移`} type="number" step="0.1" value={group.translation[i]} onChange={e=>edit(s=>{s.groups.find(g=>g.id===group.id)!.translation[i]=Number(e.target.value);})}/></label>)}</div></>)}
            <p><button className="primary" disabled={group.deleted} onClick={p.onInspect}>編輯模型與材質 →</button></p>
          </>}
        </section>
        {single&&<AssetMatcher key={p.project+group.id} styleSyncUnavailable={p.styleSyncUnavailable} detailPage={active==='others'||active==='placement'?'main':active} onDetailPage={setPage} taskId={p.taskId} project={p.project} group={group} part={part} revision={p.revision} dirty={p.dirty} model={p.model} busy={p.busy} onSave={p.onSave} onAccept={p.onAccept} onSelectPart={id=>p.onSelect(group.id,id)} stylePrompt={objectStyle(group,p.legacyStyles[group.id])} onStylePrompt={value=>p.onStyleChange(group.id,value)}/>}
        <section hidden={active!=='materials'}>
          {single&&<details className="material-part-edit" key={group.id+':'+(part?.id||'none')} open><summary>部位材質{part?' · '+part.name:''}</summary><p>點選模型中的子物件，或從清單選擇。只修改所選部位。</p>
            <select size={7} aria-label="子物件清單" value={part?.id||''} onChange={e=>p.onSelect(group.id,e.target.value)}><option value="" disabled>選擇子物件</option>{group.children.map(id=><option key={id} value={id}>{scene.objects.find(o=>o.id===id)?.name||id}</option>)}</select>
            {part&&<><label>子物件名稱<input value={part.name} onChange={e=>edit(s=>{s.objects.find(o=>o.id===part.id)!.name=e.target.value;})}/></label><label>材質描述<textarea value={part.material.description} onChange={e=>material(m=>m.description=e.target.value)}/></label><label>材質參考連結<input value={part.material.url} placeholder="https://…" onChange={e=>material(m=>m.url=e.target.value)}/></label>
              <label>快速外觀<select aria-label="子物件材質選擇" value="" onChange={e=>{const presets:Record<string,[string,number,string]>={wood:['#b68d60',.65,'溫潤淺木色'],metal:['#353638',.35,'霧黑金屬'],fabric:['#a1aa9d',.9,'淺灰綠布料']};if(e.target.value==='original')material(m=>{m.color=null;m.render_roughness=null;});else{const [color,roughness,description]=presets[e.target.value];material(m=>Object.assign(m,{color,roughness,description,render_roughness:null}));}}}><option value="" disabled>選擇基本外觀…</option><option value="original">原材質</option><option value="wood">淺木色</option><option value="metal">霧黑金屬</option><option value="fabric">淺灰綠布料</option></select></label>
              <div className="material-controls"><label>基本色<input type="color" value={part.material.color||'#d2c7b8'} onChange={e=>material(m=>m.color=e.target.value)}/></label><label>粗糙度<input type="number" min="0" max="1" step="0.05" value={part.material.render_roughness??part.material.roughness} onChange={e=>material(m=>{m.roughness=Number(e.target.value);if(m.render_roughness!=null)m.render_roughness=m.roughness;})}/></label></div><p className="muted">基本色／粗糙度即時預覽；連結記為需求，不會自動下載貼圖。</p>
            </>}
          </details>}

        </section>
        {single&&<section hidden={active!=='ai'} aria-label="物件配對依據">
            <AssetConstraints mode="matching" group={group} onDraw={p.onDraw} onPlacement={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.placement_constraints=value;})} onChange={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.asset_requirements=value;})}/>
          <button disabled={!part} onClick={()=>{if(part)p.onCandidate(part.id);}}>AI 調色建議</button><small>{part?`針對 ${part.name} 提供基本色與粗糙度建議。`:'先在模型或材質頁選取子物件，才能取得調色建議。'}</small>
        </section>}
        {!single&&<section hidden={active!=='placement'} aria-label="配置範圍">
            <AssetConstraints mode="placement" group={group} onDraw={p.onDraw} onPlacement={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.placement_constraints=value;})} onChange={value=>edit(s=>{s.groups.find(g=>g.id===group.id)!.asset_requirements=value;})}/>
        </section>}
      </>}
    </div>
  </fieldset>;
}
