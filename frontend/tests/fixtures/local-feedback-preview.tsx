import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import SemanticSourceReview from '../../src/features/visualization/SemanticSourceReview';
import type {AnswerMarks} from '../../src/features/visualization/SemanticSourceReview';
import type {CorrectionItem} from '../../src/features/visualization/SemanticCorrections';
import type {SemanticLayerItem} from '../../src/features/visualization/SemanticLayers';
import '../../src/features/visualization/planImport.css';
import '../../src/features/visualization/studio.css';

const source='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="white"/><path d="M100 100H700V400H100Z" fill="none" stroke="#777"/><rect x="200" y="200" width="160" height="90" fill="#eee" stroke="#555"/></svg>');
const view={width:800,height:500,bounds:[0,0,8,5] as [number,number,number,number],scale:100,pad:0};
const items:SemanticLayerItem[]=[{id:'recognition:table',name:'合成測試桌子',role:'mask',category:'table',layer:'furniture',points:[[2,2.1],[3.6,2.1],[3.6,3],[2,3]] as [number,number][],closed:true,source_ids:['synthetic-table'],evidence:'Synthetic only',status:'interpreted',details:{parameters:[],notes:[]}}];
function Preview(){
 const [drafts,setDrafts]=useState<CorrectionItem[]>([]),[answers,setAnswers]=useState<Record<string,string>>({q1:'此處是桌子',q2:'保留'}),[annotations,setAnnotations]=useState<AnswerMarks>({}),[submitted,setSubmitted]=useState('尚未提交');
 const questions=[{id:'q1',label:'Q1',title:'桌子用途',ask:'請核對桌子',reason:'Synthetic question',source_ids:['synthetic-table'],box:[2,2.1,3.6,3] as [number,number,number,number],located:true},{id:'q2',label:'Q2',title:'其他區域',ask:'請核對其他區域',reason:'Unrelated synthetic question',source_ids:[],box:[5,1,6,2] as [number,number,number,number],located:true}];
 return <main style={{height:'95vh',fontFamily:'system-ui'}}><p role="status">合成UI驗證，不呼叫模型或寫入案件。提交紀錄：{submitted}</p><SemanticSourceReview url={source} view={view} questions={questions} answers={answers} onChange={setAnswers} annotations={annotations} onAnnotations={setAnnotations} disabled={false} onSave={()=>setSubmitted('只保存草稿')} onReview={id=>setSubmitted('Q局部提交：'+id)} layerData={{items,lighting_reviewed:true}} initialTab="result" manual={{items:drafts,onChange:setDrafts,dirty:true,onSave:async()=>true,onBatch:ids=>setSubmitted('M局部提交：'+ids.join(',')),results:[],resultsCurrent:true,disabled:false,canBatch:true}} result={<p>保留同一套綜合物件結果</p>} correction={<p>物件或標註範圍內修正</p>} status={submitted}/></main>;
}
createRoot(document.getElementById('root')!).render(<Preview/>);
