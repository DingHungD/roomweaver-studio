import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AgentHubFrame,AgentHubProvider,AgentTrigger,useAgentModel} from '../../src/features/visualization/AgentHub';
import {EditorWorkspace,WorkspaceControls} from '../../src/features/visualization/EditorWorkspace';
import '../../src/features/visualization/studio.css';

let active=false,fail=false,listReads=0,mounts=0;
const originalFetch=window.fetch;
window.fetch=async(input,options)=>{
 const url=new URL(String(input),location.origin);
 if(url.pathname==='/api/studio/agent/tasks'){
  listReads++;if(fail)throw Error('Synthetic offline');
  const offset=Number(url.searchParams.get('history_offset')||0);
  return Response.json({active:active?[{id:'demo-active',kind:'plan_semantics',status:'running',phase:'合成工作正在處理所選物件',activity:{title:'合成局部反饋',items:['測試物件']}}]:[],history:Array.from({length:Math.min(20,45-offset)},(_,i)=>({id:'history-'+(i+offset),kind:'plan_semantics',status:'passed',phase:'合成工作已完成',activity:{title:'歷史工作 '+(i+offset+1),items:[]}})),history_total:45,unavailable:0});
 }
 if(url.pathname==='/api/session')return Response.json({token:'synthetic'});
 if(url.pathname==='/api/studio/agent/status')return Response.json({authenticated:true,version:'synthetic',auth_type:'mock',models:[{id:'demo-model',displayName:'合成模型',isDefault:true}],default_model:'demo-model'});
 if(url.pathname.startsWith('/api/'))return Response.json({error:{message:'合成介面不提交模型或案件工作'}},{status:400});
 return originalFetch(input,options);
};

function Draft(){
 const [text,setText]=useState('尚未保存的測試草稿'),[count,setCount]=useState(0);const {model}=useAgentModel();
 useEffect(()=>{mounts++;setCount(mounts);},[]);
 return <div style={{height:'100%',minHeight:400,background:'#dbe5d8',padding:'130px 24px 24px'}}><p role="status">畫布掛載：{count} · 模型：{model||'預設'}</p><label>合成未保存草稿<textarea aria-label="合成未保存草稿" value={text} onChange={e=>setText(e.target.value)}/></label><button onClick={()=>{active=!active;}}>切換合成工作</button><button onClick={()=>{fail=!fail;}}>切換讀取失敗</button><button onClick={()=>alert('合成操作按鈕可使用')}>測試操作按鈕</button><p>開關側欄、切換分頁與寬度時，草稿與掛載次數保持；每次清單讀取計數：{listReads}。</p></div>;
}
function Preview(){
 const [project,setProject]=useState(false);
 return <AgentHubProvider>{project?<EditorWorkspace editing section={1}><div className="studio-app"><header className="studio-header"><b>合成專案</b><button onClick={()=>setProject(false)}>返回合成首頁</button><AgentTrigger/></header><div className="studio-shell"><nav className="studio-rail">合成導覽</nav><div className="studio-content"><div className="studio-title"><div><h1>合成編輯畫布</h1></div><WorkspaceControls/></div><Draft/></div></div></div></EditorWorkspace>:<AgentHubFrame className="agent-home-layout"><header className="studio-header"><h1>合成專案首頁</h1><button onClick={()=>setProject(true)}>開啟合成專案</button><AgentTrigger/></header><Draft/></AgentHubFrame>}</AgentHubProvider>;
}
createRoot(document.getElementById('root')!).render(<Preview/>);
