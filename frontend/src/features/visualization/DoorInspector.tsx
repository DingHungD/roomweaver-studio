import {useEffect,useId,useState} from 'react';
import type {DoorControl,ManualDoor,Revision,Scene} from './api';
import DoorAssetMatcher from './DoorAssetMatcher';
import './materialInspector.css';

export type DoorDetailPage='main'|'others'|'materials'|'ai'|'candidates';
type Part='frame'|'leaf-0'|'leaf-1';
type Props={project:string;selected:string;door?:ManualDoor;doors:ManualDoor[];control:DoorControl;part:Part;single:boolean;page:DoorDetailPage;setPage:(page:DoorDetailPage)=>void;
 busy:boolean;readonly:boolean;working:boolean;revision:string|null;dirty:boolean;model:string;
 controlFor:(id:string)=>DoorControl;setSelected:(id:string)=>void;setPart:(part:Part)=>void;change:(value:Partial<DoorControl>)=>void;remove:()=>void;widthPreview:()=>Promise<void>;onInspect:()=>void;
 onSave:()=>Promise<string|null|undefined>;onAccept:(revision:Revision)=>void;setAssetPreview:(scene:Scene)=>void};

/** Door inspector tabs only change visibility; the matcher and viewport keep their state. */
export default function DoorInspector(p:Props){
 const {project,selected,door,doors,control,part,single,page,setPage,busy,readonly,working,revision,dirty,model,controlFor,setSelected,setPart,change,remove,widthPreview,onSave,onAccept,setAssetPreview}=p;
 const [search,setSearch]=useState('');const prefix=useId();
 useEffect(()=>{setPage('main');},[single]);
 useEffect(()=>{if(single)setPage('materials');},[part]);
 const tabs:[DoorDetailPage,string][]=single?[['main','主畫面'],['materials','材質'],['ai','AI 設置'],['candidates','候選清單']]:[['main','主畫面'],['others','其他門']];
 const active=tabs.some(([id])=>id===page)?page:'main';
 function tabKeys(e:React.KeyboardEvent<HTMLDivElement>){if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)||!(e.target as HTMLElement).matches('[role=tab]'))return;
  e.preventDefault();const i=tabs.findIndex(([id])=>id===active),n=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  setPage(tabs[n][0]);document.getElementById(`${prefix}-${tabs[n][0]}`)?.focus();
 }
 return <div className="material-detail door-detail">
  <div className="material-detail-title">{door?<label>物件名稱<input aria-label="門名稱" disabled={busy||readonly||control.deleted} maxLength={120} value={control.name??door.name} onChange={e=>change({name:e.target.value})}/></label>:<h3>尚未選取門</h3>}
   {door&&<small>{control.kind==='single'?'單開門':control.kind==='double'?'雙開門':control.kind==='sliding'?'拉門':control.kind==='folding'?'折疊門':control.kind==='frame'?'只有門框':'門型待設定'} · {part==='frame'?'門框':part==='leaf-0'?'門片 1':'門片 2'}</small>}
  </div>
  <div className="material-detail-tabs" role="tablist" aria-label="門詳細編輯分頁" onKeyDown={tabKeys}>{tabs.map(([id,label])=><button type="button" key={id} role="tab" id={`${prefix}-${id}`} aria-controls={`${prefix}-panel`} aria-selected={active===id} tabIndex={active===id?0:-1} onClick={()=>setPage(id)}>{label}</button>)}</div>
  <div role="tabpanel" id={`${prefix}-panel`} aria-labelledby={`${prefix}-${active}`}>
   <section hidden={single?active!=='main':active!=='others'} aria-label="切換門">
    <label>搜尋其他門<input aria-label="搜尋其他門" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜尋門名稱…"/></label>
<label>選取門<select aria-label="選取門" value={selected} onChange={e=>{setSelected(e.target.value);setPage('main');}}>{doors.filter(d=>d.id===selected||(controlFor(d.id).name??d.name).toLowerCase().includes(search.toLowerCase())).map(d=><option key={d.id} value={d.id}>{controlFor(d.id).deleted?'已刪除 · ':''}{controlFor(d.id).name??d.name}</option>)}</select></label>
   </section>
   {door&&<>
    <section hidden={active!=='main'}>
     {control.deleted&&<p role="status">物件已刪除，可在下方還原。</p>}
     <div className="object-actions material-detail-actions"><button className="danger" disabled={busy||readonly} onClick={remove}>{control.deleted?'還原物件':'刪除物件'}</button>{!single&&<button disabled={busy||readonly||control.deleted} className="primary" onClick={p.onInspect}>編輯模型與材質 →</button>}</div>
     <fieldset disabled={busy||readonly||control.deleted} style={{border:0,padding:0,minWidth:0}}>
<label>門組 AB 長度（cm）<input aria-label="門組 AB 長度" type="number" min="50" max={Math.min(300,Math.hypot(door.points[1][0]-door.points[0][0],door.points[1][1]-door.points[0][1])*100)} step="1" value={Number(((control.assembly_width??Math.hypot(door.points[1][0]-door.points[0][0],door.points[1][1]-door.points[0][1]))*100).toFixed(1))} onChange={e=>{const width=Number(e.target.value)/100,original=Math.hypot(door.points[1][0]-door.points[0][0],door.points[1][1]-door.points[0][1]);if(width>=.5&&width<=Math.min(3,original))change({assembly_width:Math.abs(width-original)<.00001?null:width});}}/></label><small>調整洞口內的門組長度，中心與開向不變；兩側保留同材質收邊。保存後視為已確認尺寸。</small><label>種類<select aria-label="門種類" value={control.kind||''} onChange={e=>change({kind:(e.target.value||null) as DoorControl['kind'],side:null,swing:'auto',hinge:'auto',assembly_width:null,allow_width_adjustment:false})}><option value="">尚未設定</option><option value="single">單開門</option><option value="double">雙開門</option><option value="sliding">拉門</option><option value="frame">只有門框</option><option value="folding">折疊門</option></select></label>{control.kind==='single'&&<><label><input type="checkbox" checked={control.allow_width_adjustment||false} onChange={e=>change({allow_width_adjustment:e.target.checked})}/>允許 Agent 微調門寬（洞口中心與開向不變）</label>{control.allow_width_adjustment&&<button disabled={working||busy} onClick={()=>void widthPreview()}>預覽門寬試算（Agent 待確認）</button>}{control.allow_width_adjustment&&<label>通行寬度目標 cm<input type="number" min="50" max="150" value={Math.round((control.min_passage??.70)*100)} onChange={e=>{const n=Number(e.target.value);if(n>=50&&n<=150)change({min_passage:n/100});}}/></label>}{control.assembly_width&&<p>試配框外寬 {(control.assembly_width*100).toFixed(1)} cm；原洞口保留，兩側以同材質收邊。</p>}</>}{(control.kind==='single'||control.kind==='double'||control.kind==='folding')&&<><label>開口方向<select aria-label="開口方向" value={control.side||''} onChange={e=>change({side:(e.target.value||null) as DoorControl['side']})}><option value="">尚未設定</option><option value="positive">A → B 的左側</option><option value="negative">A → B 的右側</option></select></label>{control.kind==='folding'&&<label>收折端<select aria-label="收折端" value={control.hinge} onChange={e=>change({hinge:e.target.value as DoorControl['hinge']})}><option value="auto">尚未設定</option><option value="A">收至 A 端</option><option value="B">收至 B 端</option></select></label>}{control.kind==='single'&&<label>旋轉方向<select aria-label="門旋轉方向" value={control.swing} onChange={e=>change({swing:e.target.value as DoorControl['swing']})}><option value="auto">尚未設定</option><option value="positive">逆時針</option><option value="negative">順時針</option></select></label>}</>}<details><summary>門洞端點與尺寸</summary><p>A {door.points[0].map(n=>n.toFixed(2)).join(', ')} → B {door.points[1].map(n=>n.toFixed(2)).join(', ')} m</p><p>門寬 {(Math.hypot(door.points[1][0]-door.points[0][0],door.points[1][1]-door.points[0][1])*100).toFixed(1)} cm · 高 {door.height*100} cm</p></details>
     </fieldset>
    </section>
    {single&&<>
     <section hidden={active!=='materials'} aria-label="門部位材質"><fieldset disabled={busy||readonly||control.deleted} style={{border:0,padding:0,minWidth:0}}>
<h4>組成與材質</h4><label>子物件<select aria-label="門子物件" value={part} onChange={e=>setPart(e.target.value as typeof part)}><option value="frame">門框</option>{control.kind&&control.kind!=='frame'&&<option value="leaf-0">門片 1</option>}{['folding','double','sliding'].includes(control.kind||'')&&<option value="leaf-1">門片 2</option>}</select></label>{control.assets?.[part]&&<p>目前使用 BlenderKit 素材。<button onClick={()=>{const assets={...control.assets};delete assets[part];change({assets});}}>改回基本材質</button></p>}<label>基本色<input disabled={!!control.assets?.[part]} type="color" aria-label="門子物件基本色" value={control.materials?.[part]?.color||'#bca07b'} onInput={e=>change({materials:{...control.materials,[part]:{roughness:control.materials?.[part]?.roughness??.6,color:e.currentTarget.value}}})}/></label><label>粗糙度<input disabled={!!control.assets?.[part]} aria-label="門子物件粗糙度" type="range" min="0" max="1" step="0.01" value={control.materials?.[part]?.roughness??.6} onInput={e=>change({materials:{...control.materials,[part]:{color:control.materials?.[part]?.color||'#bca07b',roughness:Number(e.currentTarget.value)}}})}/></label>
     </fieldset></section>
     <DoorAssetMatcher key={project+selected+part} {...{project,part,control,revision,dirty,model,onSave,onAccept}} busy={busy||readonly||!!control.deleted} opening={selected} onPreview={setAssetPreview} detailPage={active==='others'?'main':active} onDetailPage={setPage}/>
    </>}
   </>}
   {!doors.length&&<p>尚未有可追溯門洞；可在平面圖點選兩點新增。</p>}
  </div>
 </div>;
}
