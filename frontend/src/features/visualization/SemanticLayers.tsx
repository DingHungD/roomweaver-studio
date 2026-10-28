import {categoryNames,filterSemanticSelection} from './semanticLayerFilter.mjs';
import SemanticLayerSelector from './SemanticLayerSelector';
import type {DraftOption} from './SemanticLayerSelector';
import {sourcePoint} from './semanticSource.mjs';
import {previewColor,previewPalettes} from './cadPreviewPalette.mjs';
import type {SourceView} from './SemanticSourceReview';
export type SemanticLayerItem={id:string;name:string;layer:string;category:string;role:string;points:[number,number][];closed:boolean;areas?:{points:[number,number][];holes:[number,number][][]}[];strokes?:{points:[number,number][];closed:boolean}[];evidence:string;source_ids:string[];status:'interpreted'|'annotation'|'reference';details?:{parameters:{key:string;label:string;value:number;unit:string;status:string;description:string}[];notes:string[]}};
export type SemanticLayerData={items:SemanticLayerItem[];lighting_reviewed:boolean};
type PanelProps={showControls?:boolean;data:SemanticLayerData;selection:string[]|null;selected:string|null;onSelection:(s:string[]|null)=>void;onSelect:(i:SemanticLayerItem)=>void;background:boolean;onBackground:(v:boolean)=>void;drafts:DraftOption[];hiddenDrafts:Set<string>;onDraftVisibility:(id:string,visible:boolean)=>void;onDraftLocate:(id:string)=>void};
export function SemanticLayerPanel({showControls=true,data,selection,selected,onSelection,onSelect,background,onBackground,drafts,hiddenDrafts,onDraftVisibility,onDraftLocate}:PanelProps){
 const items=filterSemanticSelection(data.items,selection) as SemanticLayerItem[],current=items.find(i=>i.id===selected);
 return <section className="semantic-layer-panel" aria-label="判讀圖層">
  {showControls&&<><SemanticLayerSelector items={data.items} selection={selection} onSelection={onSelection} drafts={drafts} hiddenDrafts={hiddenDrafts} onDraftVisibility={onDraftVisibility}/>
  <label className="semantic-background-toggle"><input type="checkbox" checked={background} onChange={e=>onBackground(e.target.checked)}/>疊合原圖參考</label></>}
  {items.some(i=>i.layer==='lighting')&&<p className="semantic-layer-notice">{data.lighting_reviewed?'燈具圖樣與文字註記分開顯示；註記不等於已設置光源。':'這份候選尚未盤點燈具圖樣。虛線燈號僅定位原圖文字；可在「修正」重新複核。'}</p>}
  {current&&<SemanticObjectDetails item={current}/>}
  <details className="semantic-object-list" open><summary>判讀物件 ({items.length})</summary><div className="semantic-layer-items" aria-label="判讀物件清單">{items.map(item=><button key={item.id} type="button" aria-pressed={selected===item.id} onClick={()=>onSelect(item)}><span className={'semantic-item-dot '+item.layer}/><span>{item.name}<small>{item.status==='annotation'?'文字位置 · 待對照圖樣':item.status==='reference'?'參考範圍 · 待核對':categoryNames[item.category as keyof typeof categoryNames]||item.category}</small></span><span aria-hidden="true">⌖</span></button>)}{!items.length&&<p>{selection?.length===0?'尚未選取判讀類別，可從上方選單勾選。':'目前沒有這類判讀物件；不代表原圖一定沒有。'}</p>}</div></details>
  <details className="semantic-draft-list" aria-label="修改項草稿" open><summary>修改項草稿 ({drafts.length})</summary>{drafts.length?drafts.map(d=><div key={d.id}><label><input type="checkbox" checked={!hiddenDrafts.has(d.id)} onChange={e=>onDraftVisibility(d.id,e.target.checked)}/><span>{d.label} · {d.title}<small>{d.markCount} 筆標註{d.hasText?' · 有文字意見':''}</small></span></label><button type="button" disabled={!d.located} onClick={()=>onDraftLocate(d.id)} aria-label={'定位修改項 '+d.label}>定位</button></div>):<p>在「修正」新增修正項、標註或回答 Q 後，草稿會同步顯示。</p>}</details>
 </section>;
}
export function SemanticObjectDetails({item}:{item:SemanticLayerItem}){
 return <article className="semantic-layer-selection" aria-label="物件詳細資料"><h3>{item.name}</h3><details><summary>來源與判斷</summary><p>{item.evidence}</p></details>{!!item.details?.parameters.length&&<div className="semantic-object-parameters"><b>參數與預設值</b><dl>{item.details.parameters.map(p=><div key={p.key}><dt>{p.label}</dt><dd>{Number((p.value*100).toFixed(2))} cm<small>{p.description}</small></dd></div>)}</dl></div>}{!!item.details?.notes.length&&<ul>{item.details.notes.map((s,i)=><li key={i}>{s}</li>)}</ul>}<details><summary>來源元件</summary><small>{item.source_ids.join('、')||'沒有可直接引用的原圖元件，仍待核對'}</small></details></article>;
}
export function SemanticLayerDrawing({items,view,scale,selected,onSelect,interactive,theme='light'}:{items:SemanticLayerItem[];view:SourceView;scale:number;selected:string|null;onSelect:(i:SemanticLayerItem)=>void;interactive:boolean;theme?:'light'|'dark'}){
 const pts=(p:[number,number][])=>p.map(v=>sourcePoint(view,v).join(',')).join(' ');
 return <g aria-label="語意判讀圖層">{items.map(item=>{
  const active=selected===item.id,color=previewColor(active?'#be4a22':item.layer==='walls'?'#39664e':item.role==='window'?'#258bb6':item.role==='door'?'#c37b32':item.layer==='lighting'?'#a07b17':'#516d72',theme);
  const xs=item.points.map(p=>p[0]),ys=item.points.map(p=>p[1]);
  const center=sourcePoint(view,[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]);
  const pointList=item.closed?[...item.points,item.points[0]]:item.points;
  return <g key={item.id} data-semantic-item={item.id} data-layer={item.layer} role={interactive?'button':undefined} aria-label={interactive?`選取 ${item.name}`:undefined} tabIndex={interactive?0:undefined} style={{pointerEvents:interactive?'auto':'none',cursor:interactive?'pointer':'default'}} onClick={()=>interactive&&onSelect(item)} onKeyDown={e=>{if(interactive&&e.key==='Enter')onSelect(item);}}>
   <title>{item.name}：{item.evidence}</title>
   {item.role!=='lighting'&&item.role!=='drawing'&&item.role!=='floor'&&item.role!=='mask'&&<polyline points={pts(pointList)} fill={item.closed?(item.layer==='rooms'?'#a5bfa42a':'#c9bb9d36'):'none'} stroke={color} strokeWidth={active?4:item.layer==='walls'?4:2} strokeDasharray={item.layer==='rooms'?'6 4':undefined} vectorEffect="non-scaling-stroke"/>}
   {item.role==='floor'&&item.areas?.map((area,i)=><path key={i} d={[area.points,...area.holes].map(ring=>'M'+pts(ring).replaceAll(' ',' L')+' Z').join(' ')} fill={theme==='dark'?'#23323b':'#ece9dc'} fillRule="evenodd" stroke={color} strokeWidth={active?3:1} vectorEffect="non-scaling-stroke"/>)}
   {item.role==='mask'&&item.areas?.map((area,i)=><path key={'mask-'+i} d={[area.points,...area.holes].map(ring=>'M'+pts(ring).replaceAll(' ',' L')+' Z').join(' ')} fill={color} fillOpacity={active?.35:.18} fillRule="evenodd" stroke={color} strokeWidth={active?3:1} vectorEffect="non-scaling-stroke"/>)}
   {(item.strokes||[]).map((s,i)=><polyline key={i} points={pts(s.closed?[...s.points,s.points[0]]:s.points)} fill="none" stroke={color} strokeWidth={active?3:1.5} vectorEffect="non-scaling-stroke"/>)}
   {item.role==='lighting'&&<g transform={`translate(${center[0]} ${center[1]}) scale(${1/scale})`}><circle r={10} fill={theme==='dark'?'#34321f':'#fff8da'} stroke={color} strokeWidth={2} strokeDasharray={item.status==='annotation'?'3 3':undefined}/><path d="M-6 -6 L6 6 M-6 6 L6 -6" stroke={color} strokeWidth={1.5}/></g>}
   {(item.layer==='furniture'||item.layer==='rooms'||active)&&<text x={center[0]} y={center[1]-14/scale} textAnchor="middle" fill={color} stroke={previewPalettes[theme].background} strokeWidth={3/scale} paintOrder="stroke" fontSize={11/scale}>{item.name}</text>}
   {!item.closed&&item.role!=='lighting'&&<polyline points={pts(pointList)} stroke="transparent" strokeWidth={14} fill="none" vectorEffect="non-scaling-stroke"/>}
  </g>;
 })}</g>;
}
