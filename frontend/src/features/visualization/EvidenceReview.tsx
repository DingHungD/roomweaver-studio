export type EvidenceAudit={
  records:{id:string;source:string;text:string;source_sha256?:string|null}[];
  resolutions:{question_id:string;status:'resolved'|'partial'|'unresolved';answer:string;evidence_ids:string[];remaining_question:string}[];
  digit_readings:{dimension_id:string;text:string;confidence:string;alternatives:string[]}[];
};

export default function EvidenceReview({audit}:{audit:EvidenceAudit}){
  const resolved=audit.resolutions.filter(r=>r.status==='resolved');
  const partial=audit.resolutions.filter(r=>r.status==='partial');
  return <div className="image-evidence-review">
    <h3>已沿用本案確認紀錄</h3>
    <p>{resolved.length} 項已自動修正，不需重複回答；{partial.length} 項已有部分答案，下方只列尚未確定的內容。原圖與上次草稿保留。</p>
    <details><summary>查看採用答案與來源</summary><ul>{audit.resolutions.filter(r=>r.status!=='unresolved').map(r=><li key={r.question_id}><b>{r.status==='resolved'?'已解決':'部分已確認'}</b>：{r.answer}<ul>{r.evidence_ids.map(id=><li key={id}>{audit.records.find(e=>e.id===id)?.source||id}</li>)}</ul></li>)}</ul></details>
    {!!audit.digit_readings.length&&<details><summary>數字局部放大複核</summary><p>先獨立辨讀原始筆跡，不提供歷史答案，再與已確認值核對。存在其他可能讀值時，仍以有來源的確認紀錄為準。</p><ul>{audit.digit_readings.map(d=><li key={d.dimension_id}>{d.dimension_id}：讀到 {d.text}{d.alternatives.length>0&&`；其他可能：${d.alternatives.join('、')}`}</li>)}</ul></details>}
  </div>;
}
