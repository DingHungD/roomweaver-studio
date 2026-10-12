import {useEffect,useState} from 'react';
import QuestionReview from './QuestionReview';
import type {QuestionNote,SourceMark} from './QuestionReview';
import {api} from './api';

type Answer={id:string;answers:Record<string,string>;source_marks:SourceMark[]};
type Draft={base_answer_id:string|null;answers:Record<string,string>;source_marks:SourceMark[]};
export default function LayoutSourceReview({endpoint,revision,notes,image,imageUrl,stale}:{endpoint:string;revision:string;notes:QuestionNote[];image:{width:number;height:number};imageUrl:string;stale:boolean}){
  const [draft,setDraft]=useState<Draft|null>(null),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const key='layout-source-reply:'+endpoint+':'+revision;
  useEffect(()=>{let alive=true;void api<Answer|null>(endpoint+'/answers').then(saved=>{
    if(!alive)return;
    let local:Draft|null=null;try{local=JSON.parse(localStorage.getItem(key)||'null');}catch{/* Use saved evidence if a local draft is unavailable. */}
    setDraft(local||{base_answer_id:saved?.id||null,answers:saved?.answers||Object.fromEntries(notes.map(n=>[n.question_id,''])),source_marks:saved?.source_marks||[]});
    setDirty(!!local);if(local)setMessage('已恢復此候選的未保存草稿；請確認後保存。');
  }).catch(e=>{if(alive)setMessage(e.message);});return()=>{alive=false;};},[endpoint,key]);
  function change(next:Draft){setDraft(next);setDirty(true);setMessage('答覆尚未保存至案件。');try{localStorage.setItem(key,JSON.stringify(next));}catch{setMessage('瀏覽器無法暫存，請勿離開，先保存答覆。');}}
  async function save(){if(!draft||busy)return;setBusy(true);try{
    const result=await api<Answer>(endpoint+'/answers','PUT',{...draft,base_revision:revision});
    setDraft({...draft,base_answer_id:result.id});setDirty(false);localStorage.removeItem(key);setMessage('已保存原圖端點與答覆；尚未套用到平面，也未採用配置。');
  }catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}
  return <details className="layout-context" open><summary>在原始手繪圖標註配置疑點（{notes.length} 項，可直接畫 A→B）</summary>
    <p>先點問題放大，再按「畫 A→B」依序點兩個端點，填寫線段意思。同一問題可畫多條線標示不同位置，並選擇對應疑點；未知處可寫「待量測」。</p>
    {draft&&<fieldset disabled={busy||stale} style={{border:0,padding:0}}><QuestionReview notes={notes.map(n=>({...n,answer:draft.answers[n.question_id]||''}))} image={image} url={imageUrl} sourceMarks={draft.source_marks} numberPrefix="Q" saveLabel="保存配置問題答覆" onChange={next=>change({...draft,answers:Object.fromEntries(next.map(n=>[n.question_id,n.answer]))})} onMarksChange={marks=>change({...draft,source_marks:marks})}/>
      <button type="button" className="primary" disabled={!dirty||busy||stale} onClick={save}>{busy?'保存中…':'保存配置問題答覆'}</button></fieldset>}
    <p role="status">{stale?'平面已更新，此候選答覆只供參考，請重新核對。':message}</p>
  </details>;
}
