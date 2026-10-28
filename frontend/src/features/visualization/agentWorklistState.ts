export type AgentWork={
 id:string;kind:string;status:string;model?:string|null;phase?:string;error?:string;
 created_at?:string;started_at?:string;finished_at?:string;updated_at?:string;
 last_activity_at?:string;phase_started_at?:string;
 activity?:{title:string;project_id?:string|null;plan_id?:string|null;items:string[]};
 phase_history?:{phase:string;at:string}[];
};
export type AgentWorkSnapshot={active:AgentWork[];history:AgentWork[];history_total:number;unavailable:number};
const labels:Record<string,string>={queued:'等待執行',running:'進行中',stopping:'停止中',passed:'已完成',failed:'失敗',stopped:'已停止',interrupted:'已中斷'};
export function workStatus(status:string){return labels[status]||status;}
export function elapsed(since?:string,until:number=Date.now()){
 const start=Date.parse(since||'');
 if(!Number.isFinite(start)||!Number.isFinite(until))return '時間未記錄';
 const seconds=Math.max(0,Math.floor((until-start)/1000));
 if(seconds<60)return `${seconds} 秒`;
 if(seconds<3600)return `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;
 return `${Math.floor(seconds/3600)} 小時 ${Math.floor(seconds%3600/60)} 分`;
}
export function workCounts(tasks:AgentWork[]){
 return {running:tasks.filter(t=>t.status==='running'||t.status==='stopping').length,queued:tasks.filter(t=>t.status==='queued').length};
}
export function workSummary(snapshot:AgentWorkSnapshot|null){
 if(!snapshot)return '正在讀取工作狀態…';
 const task=snapshot.active.find(t=>t.status!=='queued');
 return task?.phase||(task?'Agent 正在執行工作':snapshot.active.length?'等待 Agent 工作槽':'目前沒有進行中的 Agent 工作');
}
