import {useRef,useState} from 'react';
import {fileUrl} from './api';
import type {Scene} from './api';
import SpaceViewport from './SpaceViewport';

export default function ViewpointEditor({scene,project,busy,onChange,onContinue,canUndo,onUndo,active}:{active:boolean;canUndo:boolean;onUndo:()=>void;scene:Scene;project:string;busy:boolean;onChange:(s:Scene)=>void;onContinue:()=>void}){
  const [selected,setSelected]=useState(scene.viewpoints[0]?.id||'');
  const [preview,setPreview]=useState(false),[shotId,setShotId]=useState(''),[reset,setReset]=useState(0);

  const center=useRef<[number,number]>([0,0]);const [modelReady,setModelReady]=useState(false);
  const point=scene.viewpoints.find(p=>p.id===selected),shot=point?.shots.find(s=>s.id===shotId)||point?.shots[0];
  function edit(change:(draft:Scene)=>void){const draft=structuredClone(scene);change(draft);onChange(draft);}
  function select(id:string){setSelected(id);setShotId('');}
  function add(){const id='point-'+crypto.randomUUID().slice(0,8);edit(s=>{const xy=point?[point.eye[0]+.7,point.eye[1]+.7]:center.current;s.viewpoints.push({id,name:`觀看點 ${String(s.viewpoints.length+1).padStart(2,'0')}`,room_id:point?.room_id||s.rooms[0].id,eye:[xy[0],xy[1],point?.eye[2]||1.6],shots:[{id:'direction-1',name:'方向 01',yaw:0,pitch:0,lens:24}]});});select(id);setPreview(false);}
  return <section className="space-editor viewpoint-editor">
    <div className="space-navigation" role="tablist" aria-label="觀看點檢視方式">
      <button role="tab" aria-selected={!preview} onClick={()=>setPreview(false)}>2D 觀看點配置</button>
      <button role="tab" aria-selected={preview} disabled={!point} onClick={()=>setPreview(true)}>3D 預覽（未渲染）</button>
      <span>{scene.viewpoints.length} 個觀看點 · {scene.links.length} 組雙向連結</span>
      <button disabled={!canUndo||busy} onClick={()=>{onUndo();setPreview(false);}}>復原上一步</button>
      <button disabled={!modelReady||!scene.rooms.length||busy} onClick={add}>＋ 新增觀看點</button>
    </div>
    <div className="space-editor-grid">
      <div>
        {active&&<SpaceViewport url={fileUrl(project,scene.model_id,'model.glb')} design={scene} mode={preview?'walk':'plan'} selected="" child="" moving={false} onSelect={()=>{}} onMove={()=>{}}
          pointEditing pointId={selected} focusPoint={point} focusShot={shot} previewReset={reset} onPointSelect={select}
          onPlanCenter={xy=>{center.current=xy;setModelReady(true);}} onPointMove={(id,xy)=>edit(s=>{const p=s.viewpoints.find(p=>p.id===id)!;p.eye=[xy[0],xy[1],p.eye[2]];})}/>}
        <div className="space-bottom"><span>{preview?`${point?.name||''} · ${shot?.name||'預設方向'} · 預覽操作不改鏡位`:'點選編號查看設定，拖曳圓點移動；線段表示雙向連結。'}</span>
          <button className="primary" disabled={busy||!scene.viewpoints.length} onClick={onContinue}>確認編輯，前往整合輸出 →</button>
        </div>
        {!scene.viewpoints.length&&<p className="empty-points">先新增觀看點，再拖到想要觀看空間的位置。每點會產生一張 360° 全景。</p>}
      </div>
      <aside className="studio-inspector assembly-inspector">
        <h3>觀看點設定</h3>
        <label>選取觀看點<select aria-label="選取觀看點" value={point?.id||''} onChange={e=>select(e.target.value)}><option value="" disabled>請新增或選取觀看點</option>{scene.viewpoints.map((p,i)=><option key={p.id} value={p.id}>{String(i+1).padStart(2,'0')} · {p.name}</option>)}</select></label>
        {point?<>
          <label>名稱<input aria-label="觀看點名稱" value={point.name} onChange={e=>edit(s=>{s.viewpoints.find(p=>p.id===point.id)!.name=e.target.value;})}/></label>
          <label>所屬空間<select value={point.room_id} onChange={e=>edit(s=>{s.viewpoints.find(p=>p.id===point.id)!.room_id=e.target.value;})}>{scene.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          <div className="coordinates">{['X','Y','眼高'].map((label,i)=><label key={label}>{label}（m）<input aria-label={`觀看點 ${label}`} type="number" step="0.1" value={Number(point.eye[i].toFixed(3))} onChange={e=>edit(s=>{s.viewpoints.find(p=>p.id===point.id)!.eye[i]=Number(e.target.value);})}/></label>)}</div>
          <label>預覽方向<select value={shot?.id||''} onChange={e=>setShotId(e.target.value)}>{!point.shots.length&&<option value="">預設方向 · 水平 0°</option>}{point.shots.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <button className="primary" onClick={()=>{setPreview(true);setReset(n=>n+1);}}>3D 預覽</button>
          {preview&&<button onClick={()=>setPreview(false)}>返回 2D 配置</button>}
          <p className="muted">從此位置與所選方向觀看真實模型；即時預覽不代表最終光照，也不啟動渲染。</p>
          <h4>雙向連結</h4><p>可同時連到多個觀看點。</p>
          <div className="point-connections">{scene.viewpoints.filter(p=>p.id!==point.id).map(p=><label className="inline-check" key={p.id}><input type="checkbox" checked={scene.links.some(edge=>edge.includes(point.id)&&edge.includes(p.id))} onChange={e=>edit(s=>{s.links=s.links.filter(edge=>!(edge.includes(point.id)&&edge.includes(p.id)));if(e.target.checked)s.links.push([point.id,p.id]);})}/>{point.name} ↔ {p.name}</label>)}{scene.viewpoints.length<2&&<p>新增第二個觀看點後即可建立連結。</p>}</div>
          <h4>此點的效果圖</h4><p>另含一張 360° 全景。以下每個方向各產生一張效果圖。</p>
          {point.shots.map(s=><div className="shot-card" key={s.id}><input aria-label="方向名稱" value={s.name} onChange={e=>edit(d=>{d.viewpoints.find(p=>p.id===point.id)!.shots.find(x=>x.id===s.id)!.name=e.target.value;})}/>
            {(['yaw','pitch','lens'] as const).map((key,i)=><label key={key}>{['水平角度 °','俯仰角度 °','焦距 mm'][i]}<input type="number" value={s[key]} onChange={e=>edit(d=>{d.viewpoints.find(p=>p.id===point.id)!.shots.find(x=>x.id===s.id)![key]=Number(e.target.value);})}/></label>)}
            <button onClick={()=>{setShotId(s.id);setPreview(true);setReset(n=>n+1);}}>預覽此方向</button><button onClick={()=>edit(d=>{const p=d.viewpoints.find(p=>p.id===point.id)!;p.shots=p.shots.filter(x=>x.id!==s.id);})}>移除此方向</button>
          </div>)}
          <button onClick={()=>edit(d=>{const p=d.viewpoints.find(p=>p.id===point.id)!;p.shots.push({id:'shot-'+crypto.randomUUID().slice(0,8),name:`方向 ${String(p.shots.length+1).padStart(2,'0')}`,yaw:0,pitch:0,lens:24});})}>＋ 新增效果圖方向</button>
          <button className="danger" onClick={()=>{edit(d=>{d.viewpoints=d.viewpoints.filter(p=>p.id!==point.id);d.links=d.links.filter(edge=>!edge.includes(point.id));});select(scene.viewpoints.find(p=>p.id!==point.id)?.id||'');setPreview(false);}}>刪除觀看點</button>
        </>:<p>從平面圖選取觀看點，右側即可調整位置、方向與連結。</p>}
      </aside>
    </div>
  </section>;
}
