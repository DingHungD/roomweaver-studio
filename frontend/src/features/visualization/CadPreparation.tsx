export type CadPreparationReport={version:number;counts:Record<string,number>;header_units:string|null;explicit_units:string|null;curve_tolerance_raw:number;floor_area_raw:number|null;dimensions:{handle:string;text:string;raw_measurement:number;conflict:string|null}[];questions:{id:string;text:string;kind:string}[];floor_regions:{id:string;name:string;source:string;area_raw:number;points:[number,number][]}[]};
const factors:Record<string,number>={mm:.001,cm:.01,m:1,inch:.0254,foot:.3048};
const names:Record<string,string>={mm:'毫米',cm:'公分',m:'公尺',inch:'英吋',foot:'英呎'};
export default function CadPreparation({report,units,confirmed,locked,reviewed,disabled,onUnits,onReview}:{report:CadPreparationReport;units:string;confirmed:boolean;locked:boolean;reviewed:string[];disabled:boolean;onUnits:(confirmed:boolean,evidence:string)=>void;onReview:(id:string,value:boolean)=>void}){
 const c=report.counts,questions=report.questions.filter(q=>q.kind!=='units');
 return <section className="cad-preparation" aria-label="CAD 單位與尺度核對"><h3>單位與尺度核對</h3>

  <p>CAD 標頭：{report.header_units?names[report.header_units]:'未標示'} · 本次解讀：{names[units]}（{units}）{confirmed?' · 已確認':''}</p>
  <label><input type="checkbox" checked={confirmed} disabled={disabled||locked} onChange={e=>onUnits(e.target.checked,e.target.checked?`使用者確認圖面實際單位為${names[units]}（${units}）`:'')}/><span>我已確認圖面實際單位為{names[units]}（{units}）</span></label>
  {report.floor_area_raw!==null&&<p>地板推定聯集：約 {(report.floor_area_raw*factors[units]**2).toFixed(2)} m²。不同候選可能重疊，未重複加總；孔洞保留。橙色虛線為依尺寸推定、待核對區域。</p>}
  {questions.map(q=><label key={q.id} className="cad-review-question"><input type="checkbox" checked={reviewed.includes(q.id)} disabled={disabled} onChange={e=>onReview(q.id,e.target.checked)}/><span>{q.text}</span></label>)}
  <details><summary>轉換證據與尺寸標註（{report.dimensions.length} 筆）</summary>  <p>曲線 {c.curves||0} 個 · 填色 {c.hatches||0} 個 · 高程投影 {c.projected||0} 個 · 製圖參考 {(c.drafting_details||0)+(c.reference_only||0)+(c.reference_widths||0)} 個。原始檔與尺寸端點不變。</p><p>曲線最大弦差設定：{(report.curve_tolerance_raw*factors[units]*1000).toFixed(2)} mm。高程僅投影至衍生平面；沒有據此更改建模高度。</p>
   <div className="cad-evidence-grid">{report.floor_regions.map(r=><p key={r.id}>{r.name} · {r.source==='dimension_supported_outline'?'尺寸端點＋線圖':r.source==='hatch_boundary'?'填色邊界':'封閉線網'} · {(r.area_raw*factors[units]**2).toFixed(2)} m²</p>)}</div>
   <table><thead><tr><th>來源</th><th>圖面標註</th><th>端點量測（原圖單位）</th><th>核對</th></tr></thead><tbody>{report.dimensions.map(d=><tr key={d.handle}><td>{d.handle}</td><td>{d.text}</td><td>{d.raw_measurement.toFixed(3)}</td><td>{d.conflict||'數值保留，未移動端點'}</td></tr>)}</tbody></table>
  </details>
 </section>;
}
