const canonical=value=>JSON.stringify(normalize(value));
function normalize(value){return Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,normalize(value[k])])):value;}
export function correctionCurrent(item,outcome,legacyCurrent=false){return !!outcome&&(outcome.item_snapshot?canonical(item)===canonical(outcome.item_snapshot):legacyCurrent);}
export function correctionComplete(item,outcome,legacyCurrent=false){return correctionCurrent(item,outcome,legacyCurrent)&&outcome.preview_ready&&['corrected','no_change'].includes(outcome.status);}
export function correctionSentence(item){return (item.comment.trim().split(/[\n。！？!?]/).find(Boolean)||`${item.marks.length} 筆圖上標註`).slice(0,90);}
/** @param {string|null} editingOwner */
export function correctionHidden(items,results,legacyCurrent,hidden,shown,editingOwner=null){
 const next=new Set(hidden);
 for(const item of items){const key='manual:'+item.id;if(correctionComplete(item,results.find(r=>r.id===item.id),legacyCurrent)&&!shown.has(key))next.add(key);}
 if(editingOwner)next.delete(editingOwner);
 return next;
}
