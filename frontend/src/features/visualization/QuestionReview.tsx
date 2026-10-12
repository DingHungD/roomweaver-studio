import {useEffect,useRef,useState} from 'react';
import {bindCanvasWheel} from './canvasWheel.mjs';
import {displayPoint,sourcePoint} from './planReview.mjs';
export type QuestionNote={question_id:string;title:string;known:string;ask:string;regions:{label:string;box:[number,number,number,number]}[];answer:string};
export type SourceMark={id:string;start:[number,number];end:[number,number];description:string;question_id:string|null};
const palette=['#b33939','#167783','#6644aa','#b56512','#347538','#ae396f'];

export default function QuestionReview({notes,image,url,onChange,sourceMarks=[],onMarksChange,saveLabel="保存並檢查平面",numberPrefix=""}:{notes:QuestionNote[];image:{width:number;height:number};url:string;onChange:(notes:QuestionNote[])=>void;saveLabel?:string;numberPrefix?:string;sourceMarks?:SourceMark[];onMarksChange:(marks:SourceMark[])=>void}){
  const [drawing,setDrawing]=useState(false),[start,setStart]=useState<[number,number]|null>(null),[markError,setMarkError]=useState('');
  const [turned,setTurned]=useState(false);
  const [active,setActive]=useState<number|null>(null),[zoom,setZoom]=useState(1),[pan,setPan]=useState<[number,number]>([0,0]);
  const canvas=useRef<SVGSVGElement>(null),drag=useRef<{x:number;y:number;pan:[number,number]}|null>(null);
  useEffect(()=>canvas.current?bindCanvasWheel(canvas.current,(factor:number)=>setZoom(z=>Math.min(8,Math.max(.6,z*factor)))):undefined,[]);
  function focus(i:number|null){setActive(i);setZoom(1);setPan([0,0]);canvas.current?.scrollIntoView({behavior:'smooth',block:'center'});}
  const width=turned?image.height:image.width,height=turned?image.width:image.height;
  const displayBox=(box:[number,number,number,number]):[number,number,number,number]=>turned?[image.height-box[3],box[0],image.height-box[1],box[2]]:box;
  const mapped=notes.map(n=>({...n,regions:n.regions.map(r=>({...r,box:displayBox(r.box)}))}));
  const sourceImage=<image href={url} x={0} y={0} width={image.width} height={image.height} transform={turned?`translate(${image.height} 0) rotate(90)`:undefined}/>;
  const shown=active===null?mapped:[mapped[active]];
  const regions=shown.flatMap(n=>n.regions),x0=active===null?0:Math.max(0,Math.min(...regions.map(r=>r.box[0]))-65),y0=active===null?0:Math.max(0,Math.min(...regions.map(r=>r.box[1]))-65);
  const w=active===null?width:Math.min(width,Math.max(...regions.map(r=>r.box[2]))+65)-x0,h=active===null?height:Math.min(height,Math.max(...regions.map(r=>r.box[3]))+65)-y0;
  function addPoint(e:React.PointerEvent<SVGSVGElement>){
    const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;
    const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());
    const raw=sourcePoint([p.x,p.y],image.height,turned) as [number,number];
    if(raw[0]<0||raw[0]>image.width||raw[1]<0||raw[1]>image.height){setMarkError('請點在原圖範圍內。');return;}
    const point=raw.map(v=>Math.round(v*10)/10) as [number,number];
    if(!start){setStart(point);setMarkError('');return;}
    if(Math.hypot(point[0]-start[0],point[1]-start[1])<1){setMarkError('A、B 不能是同一點，請重新選 B。');return;}
    onMarksChange([...sourceMarks,{id:crypto.randomUUID(),start,end:point,description:'',question_id:active===null?null:notes[active].question_id}]);setStart(null);setDrawing(false);setMarkError('');
  }
  function drawnMarks(){return sourceMarks.map((m,i)=>{const a=displayPoint(m.start,image.height,turned),b=displayPoint(m.end,image.height,turned);return <g key={m.id} pointerEvents="none"><line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#0759b4" strokeWidth={3} vectorEffect="non-scaling-stroke"/>{[a,b].map((p,j)=><g key={j}><circle cx={p[0]} cy={p[1]} r={7} fill="#0759b4"/><text x={p[0]+10} y={p[1]-10} fontSize={23} fontWeight="bold" stroke="white" strokeWidth={4} paintOrder="stroke" fill="#0759b4">線{i+1}{j?'B':'A'}</text></g>)}<title>{m.description||'待補說明'}</title></g>;});}
  function marks(n:QuestionNote,i:number){return n.regions.map((r,j)=><g key={j} onClick={()=>focus(i)} style={{cursor:'pointer'}}><rect x={r.box[0]} y={r.box[1]} width={r.box[2]-r.box[0]} height={r.box[3]-r.box[1]} fill={palette[i%6]} fillOpacity={.035} stroke={palette[i%6]} strokeWidth={2.5} strokeDasharray="7 4" vectorEffect="non-scaling-stroke"/><rect x={j===0&&n.regions.length>1?r.box[2]-47:r.box[0]} y={r.box[1]-27} width={47} height={27} rx={5} fill={palette[i%6]}/><text x={(j===0&&n.regions.length>1?r.box[2]-47:r.box[0])+23} y={r.box[1]-8} fill="white" fontSize={19} textAnchor="middle" fontWeight="bold">{numberPrefix}{i+1}{n.regions.length>1?String.fromCharCode(65+j):''}</text><title>{numberPrefix}{i+1}. {r.label}</title></g>);}
  return <section className="question-review" aria-label="原圖確認標註">
    <h3>{notes.length?`在原圖上一次確認（${notes.length} 項）`:'在原圖上標記端點與說明'}</h3>
    <p>彩框指出需要核對的區域，不是已確認的量測端面。數字標記對應下方問題；點標記可放大，滾輪縮放只作用在圖內，拖曳平移。</p>
    <div className="plan-actions"><button type="button" onClick={()=>focus(null)}>顯示全部標註</button><button type="button" onClick={()=>{setTurned(t=>!t);setZoom(1);setPan([0,0]);}}>{turned?'原圖方向':'順時針轉正'}</button>{notes.map((n,i)=><button type="button" key={n.question_id} aria-pressed={active===i} onClick={()=>focus(i)}>{numberPrefix}{i+1}. {n.title}</button>)}</div>
    <div className="plan-actions"><button type="button" aria-pressed={drawing} disabled={sourceMarks.length>=100} onClick={()=>{setDrawing(!drawing);setStart(null);setMarkError('');}}>{drawing?'取消 A→B 畫線':'畫 A→B，說明端點'}</button><span role="status">{drawing?(start?'請點 B：線段終點':'請點 A：線段起點'):'可先放大再畫線；原圖、端點與說明會一起保存。'}{markError}</span></div>
    <svg className="question-map" ref={canvas} style={{cursor:drawing?'crosshair':'grab'}} viewBox={`${x0+pan[0]+w*(1-1/zoom)/2} ${y0+pan[1]+h*(1-1/zoom)/2} ${w/zoom} ${h/zoom}`} role="img" aria-label="原始手繪圖與編號疑點" onPointerDown={e=>{if(drawing){addPoint(e);return;}drag.current={x:e.clientX,y:e.clientY,pan};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!drag.current)return;const m=e.currentTarget.getScreenCTM();if(!m)return;setPan([drag.current.pan[0]-(e.clientX-drag.current.x)/m.a,drag.current.pan[1]-(e.clientY-drag.current.y)/m.d]);}} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
      {sourceImage}
      {mapped.map((n,i)=><g key={n.question_id} pointerEvents={drawing?'none':undefined}>{(active===null||active===i)&&marks(n,i)}</g>)}
      {drawnMarks()}{start&&<circle cx={displayPoint(start,image.height,turned)[0]} cy={displayPoint(start,image.height,turned)[1]} r={8} fill="#0759b4" pointerEvents="none"/>}
    </svg>
    {!!sourceMarks.length&&<div className="source-mark-list"><h4>我的 A→B 說明</h4>{sourceMarks.map((m,i)=><article key={m.id}><b>線{i+1}A → 線{i+1}B</b><label>對應疑點<select value={m.question_id||''} onChange={e=>onMarksChange(sourceMarks.map(v=>v.id===m.id?{...v,question_id:e.target.value||null}:v))}><option value="">一般說明</option>{notes.map((n,j)=><option key={n.question_id} value={n.question_id}>{j+1}. {n.title}</option>)}</select></label><label>第 {i+1} 條線的意思<textarea value={m.description} maxLength={2000} placeholder="例如：A 是牆的內側完成面，B 是門框下緣；A 到 B 為 240 cm。" onChange={e=>onMarksChange(sourceMarks.map(v=>v.id===m.id?{...v,description:e.target.value}:v))}/></label><button type="button" onClick={()=>onMarksChange(sourceMarks.filter(v=>v.id!==m.id))}>刪除第 {i+1} 條標記</button></article>)}</div>}
    <p>A→B 用來表達端點及意思；手繪不按比例，不會拿這條線的像素長度當成實測，也不會自行解除疑點。完成後請按「{saveLabel}」。</p>
    <div className="question-cards">{notes.map((n,i)=>{const regions=mapped[i].regions;const minX=Math.max(0,Math.min(...regions.map(r=>r.box[0]))-20),minY=Math.max(0,Math.min(...regions.map(r=>r.box[1]))-35);const maxX=Math.min(width,Math.max(...regions.map(r=>r.box[2]))+20),maxY=Math.min(height,Math.max(...regions.map(r=>r.box[3]))+20);return <article key={n.question_id} style={{borderTopColor:palette[i%6]}}>
      <h4>{numberPrefix}{i+1}. {n.title}</h4><svg viewBox={`${minX} ${minY} ${maxX-minX} ${maxY-minY}`} role="img" aria-label={`${numberPrefix}${i+1}. ${n.title} 局部原圖`}>{sourceImage}{marks(mapped[i],i)}{drawnMarks()}</svg>
      <small>{n.regions.map((r,j)=>`${numberPrefix}${i+1}${n.regions.length>1?String.fromCharCode(65+j):''}：${r.label}`).join('；')}</small>
      <p><b>已知，不必重答：</b>{n.known}</p><p><b>只需確認：</b>{n.ask}</p>
      <label>第 {numberPrefix}{i+1} 項回答<textarea value={n.answer} maxLength={4000} placeholder="可直接描述；尚不知道的部分寫「待量測」。" onChange={e=>onChange(notes.map((v,j)=>i===j?{...v,answer:e.target.value}:v))}/></label>
    </article>;})}</div>
    <details><summary>一次回覆的文字格式</summary><textarea className="question-reply" readOnly value={notes.map((n,i)=>`${numberPrefix}${i+1}. ${n.title}\n${n.answer||'（請填回答）'}`).join('\n\n')}/></details>
    <p>回答會隨「{saveLabel}」保存，不會直接當成已解決或啟動建模。圖片匯入可在「確認紀錄與答覆後修正」帶入已保存答覆；配置提案請保存後重新提案。</p>
  </section>;
}
