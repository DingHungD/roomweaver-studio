export type StudioLight={id:string;name:string;kind:"AREA"|"POINT"|"SPOT"|"SUN";position:[number,number,number];rotation:[number,number,number];power:number;color:[number,number,number];size:number;angle:number;enabled:boolean;locked:boolean;group_id:string|null;origin:"native"|"restored"|"proposal"|"manual"};
export type LightingSetup={enabled:boolean;mode:"existing"|"day"|"indoor";exposure:number;auto_adjust:boolean;agent_review:boolean;source_job_id?:string|null;lights:StudioLight[]};
export type Material = {description:string; url:string; color:string|null; roughness:number; candidate_id?:string|null};
export type StudioObject = {id:string; name:string; room_id:string|null; material:Material};
export type Shot = {id:string; name:string; yaw:number; pitch:number; lens:number};
export type Viewpoint = {id:string; name:string; room_id:string; eye:[number,number,number]; shots:Shot[]};
export type ObjectGroup = {id:string;name:string;children:string[];translation:[number,number,number];deleted:boolean;method:string};
export type Scene = {model_id:string; rooms:{id:string;name:string}[]; objects:StudioObject[]; groups:ObjectGroup[]; viewpoints:Viewpoint[]; links:[string,string][]; lighting:'existing'; lighting_setup?:LightingSetup};
export type Revision = {revision:string|null; scene:Scene|null};
export type Workflow = {run_id:string; revision:string; confirmation_id:string; status:string; quality:string; job_id?:string; job_status?:string; error?:string};
export type Job = {id:string;source_revision?:string;result?:{lighting_setup?:LightingSetup;notes?:string[]}; status:string; error?:string; progress?:{completed:number;total:number;current:string}};
export type Output = {job_id:string;name:string;file:string;thumbnail:string;stale:boolean;deleted?:boolean;kind:string;quality:string;revision:string;width:number;height:number};
export type Task = {id:string;kind:string;status:string;error?:string;response?:{text:string};candidate?:{color:string;reason:string;source_verified?:boolean};evidence?:{screenshot:string}};
export type Connection = {version:string;authenticated:boolean;auth_type:string;models:{id:string;displayName:string;isDefault:boolean}[]};
let token='';
export async function api<T>(path:string,method='GET',body?:unknown,retried=false):Promise<T> {
  if(!token) token=(await (await fetch('/api/session')).json()).token;
  const response=await fetch('/api/studio'+path,{method,headers:{'X-Workbench-Token':token,...(body instanceof FormData?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});
  const data=await response.json();
  if(response.status===403&&data.error?.code==='session_required'&&!retried){token='';return api<T>(path,method,body,true);}
  if(!response.ok) throw new Error(data.error?.message||data.detail?.[0]?.msg||'請求失敗');
  return data;
}
export const fileUrl=(project:string,job:string,name:string)=>`/api/studio/projects/${encodeURIComponent(project)}/files/${job}/${encodeURIComponent(name)}`;
