import {useEffect,useState} from 'react';
import {api,fileUrl} from './api';
import type {Scene} from './api';
import SpaceViewport from './SpaceViewport';
import {EditorTools} from './EditorWorkspace';
import type {ReactNode} from 'react';

export default function RealismPreview({project,jobId,revision,onClose,detailAction}:{project:string;jobId:string;revision:string|null;onClose:()=>void;detailAction?:ReactNode}){
 const [data,setData]=useState<{review_summary?:string;installation_results?:{items:{name:string;status:string;reason?:string;selected?:{name:string;url:string};dimensions?:number[];attempts:{name:string;url:string;failures:string[]}[]}[]};scene:Scene;file:string;point_id:string;completion_results?:{enabled:boolean;ceiling_patches:{id:string}[];items:{id?:string;name:string;status:string;reason?:string;changes?:{action:string}[]}[]};opening_results?:{items:{id:string;name:string;style?:string;status:string;opening?:{state:string;source:string}}[]};revision:string;prepare_only?:boolean;shelf_results?:{contents:{kind:string;source_url?:string;dimensions?:number[];source?:string;reason?:string}[]}[];remaining?:string[]}|null>(null),[error,setError]=useState('');
 const [pointId,setPointId]=useState(''),[shotId,setShotId]=useState('');
 const [mode,setMode]=useState<'plan'|'walk'>('walk');
 useEffect(()=>{let active=true;setData(null);setPointId('');setShotId('');setError('');void api<NonNullable<typeof data>>(`/projects/${project}/realism-review/${jobId}/preview`).then(r=>{if(active){if(r.revision!==revision)setError('此預覽不是目前修訂，請重新試作。');else setData(r);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[project,jobId,revision]);
 const point=data?.scene.viewpoints.find(p=>p.id===(pointId||data.point_id));
 const shot=point?.shots.find(s=>s.id===shotId)||point?.shots[0];
 return <section className="space-editor" aria-label="未採用精修模型預覽"><EditorTools>
   <div className="object-actions"><button className={mode==='plan'?'primary':''} onClick={()=>setMode('plan')}>2D 平面圖</button><button className={mode==='walk'?'primary':''} onClick={()=>setMode('walk')}>3D 畫面</button><button onClick={onClose}>結束預覽，返回目前編輯</button></div>
   <p role="status">尚未採用 · 唯讀精修模型。可移動畫面檢查；編輯版本未更動。</p>
   {data&&<label>查看空間<select aria-label="精修模型查看空間" value={point?.id||data.point_id} onChange={e=>{setPointId(e.target.value);setShotId('');setMode('walk');}}>{data.scene.viewpoints.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
   {!!point&&point.shots.length>1&&<label>查看方向<select aria-label="精修模型查看方向" value={shot?.id||''} onChange={e=>{setShotId(e.target.value);setMode('walk');}}>{point.shots.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
   {detailAction}
   <p className="muted">{data?.prepare_only?'模型準備完成，尚未試渲染。':'與選定試圖共用幾何。'}即時光照、程序材質與窗外景不等同 Cycles。</p>
   {!!data?.opening_results?.items.length&&<details><summary>門窗構件（{data.opening_results.items.length} 組）</summary>{data.opening_results.items.map(o=><p key={o.id}>{o.name} · {o.style||'已有完整構件'} {o.opening&&(o.opening.state==='open'?'· 已開啟（推定展示姿態）':'· 開啟受阻，保留門片')}</p>)}</details>}
   {data?.completion_results?.enabled&&<details><summary>空間完成度檢查 · {data.completion_results.ceiling_patches.length} 處天花補面</summary><p>尺寸保留；幾何檢查完成，外觀仍需試渲染核對。</p>{data.completion_results.items.map((r,i)=><p key={r.id||i}>{r.name} · {r.status==='corrected'?'已修正':r.status==='unresolved'?'待核對':'已檢查'} {r.changes?.map(c=>({rotate:'調整使用方向',wall_fit:'靠牆平移',mount:'補安裝連接',diffuser:'補柔光面',sink_finish:'補水槽收邊'} as Record<string,string>)[c.action]||c.action).join('、')} {r.reason}</p>)}</details>}
   {!!data?.installation_results?.items?.length&&<details><summary>安裝候選與替換結果</summary>{data.installation_results.items.map((r,i)=><div key={i}><b>{r.name} · {r.status==='prepared'?'替換預覽':'保留原件'}</b><p>{r.reason}{r.selected&&<a href={r.selected.url} target="_blank" rel="noreferrer">{r.selected.name}</a>} {r.dimensions?.map(n=>(n*100).toFixed(1)).join(' × ')} cm</p>{r.attempts.map((a,j)=><p key={j}><a href={a.url} target="_blank" rel="noreferrer">{a.name}</a> {Array.from(new Set(a.failures)).join('；')}</p>)}</div>)}</details>}
   {data?.review_summary&&<details><summary>試圖複核結果</summary><p>{data.review_summary}</p></details>}
   {!!data?.remaining?.length&&<details><summary>尚未確認與可改善項目</summary>{data.remaining.map((v,i)=><p key={i}>{v}</p>)}</details>}
   {!!data?.shelf_results?.length&&<details><summary>內容、尺寸與來源</summary>{data.shelf_results.flatMap(s=>s.contents).map((c,i)=><p key={i}>{({microwave:'微波爐',coffee_machine:'咖啡機',magazines:'雜誌'} as Record<string,string>)[c.kind]||c.kind} · {c.source==='registered_native_asset'?'原模型':'概念候選'} · {c.dimensions?.map(v=>(v*100).toFixed(1)).join(' × ')} cm {c.source_url&&<a href={c.source_url} target="_blank" rel="noreferrer">素材來源</a>}{c.reason}</p>)}</details>}
   {error&&<p role="alert">{error}</p>}
 </EditorTools><div className="space-editor-grid"><div>{data&&<SpaceViewport url={fileUrl(project,jobId,data.file)} design={data.scene} mode={mode} focusPoint={point} focusShot={shot} matchShotFrame selected="" child="" moving={false} onSelect={()=>{}} onMove={()=>{}}/>}</div></div></section>;
}
