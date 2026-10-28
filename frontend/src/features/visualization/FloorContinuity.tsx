export type FloorReport={patches:{id:string;points:number[][];area:number}[];remaining:{points:number[][];area:number;reason:string}[];repair_area:number;notes:string[];outline?:number[][][]};
export function FloorReportView({value}:{value:FloorReport}){
 const points=(value.outline||[]).flat();const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const x=Math.min(...xs),y=Math.max(...ys),w=Math.max(...xs)-x,h=y-Math.min(...ys);
 const path=(ps:number[][])=>ps.map(p=>`${p[0]},${-p[1]}`).join(' ');
 return <div><p>建模時自動補齊 {value.patches.length} 處 · {value.repair_area.toFixed(3)} m²；另 {value.remaining.length} 處需核對來源。</p>
 {w>0&&h>0&&<svg role="img" aria-label="地板缺口示意：青色自動補齊，橘色待核對" viewBox={`${x-.15} ${-y-.15} ${w+.3} ${h+.3}`} style={{width:'100%',height:230,background:'#faf8f1'}}>{(value.outline||[]).map((p,i)=><polygon key={i} points={path(p)} fill="#d7c4a3" stroke="#99876d" strokeWidth=".015"/>)}{value.remaining.map((p,i)=><polygon key={'r'+i} points={path(p.points)} fill="#e88942"/>)}{value.patches.map((p,i)=><g key={p.id}><polygon points={path(p.points)} fill="#009d9b" stroke="#007270" strokeWidth=".02"/><text x={p.points.reduce((s,q)=>s+q[0],0)/p.points.length} y={-p.points.reduce((s,q)=>s+q[1],0)/p.points.length} fontSize=".17" fill="#003a39">{i+1}</text></g>)}</svg>}
 <small>青色：兩側已有地板、約 20 cm 內的短縫。橘色：單側邊界或來源不明，保留不填。牆、柱與室外範圍不補。</small>{value.notes.map((n,i)=><p key={i}>{n}</p>)}</div>;
}
