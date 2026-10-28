import type {Scene} from './api';
import type {IncompleteItem} from './configurationIncomplete';
export type FailureDetail={asset_id?:string;name?:string;stage:string;reason:string;job_id?:string};
export type RepairRecord={id:string;status:string;phase:string;error?:string;failure_details?:FailureDetail[];revision?:string;request:{category:string;target_id:string;task_id:string;batch_id?:string;part?:string|null};proof?:{group_id?:string;reference?:unknown;generated?:unknown;materials?:Record<string,unknown>;door_id?:string;control?:unknown;model_id?:string;point_id?:string;point?:unknown}};
export function repairFailure(item:IncompleteItem,records:RepairRecord[]){
 const latest=records.find(r=>r.request.target_id===item.id&&(!item.repair||r.request.batch_id===item.repair.batch_id)&&(!item.part||r.request.part===item.part));
 return latest?.status==='needs_attention'?latest:undefined;
}
function canonical(value:unknown):string{return JSON.stringify(value,(_key,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);}
export function repairedItem(item:IncompleteItem,records:RepairRecord[],scene:Scene){
 return records.some(r=>{
  if(r.status!=='completed'||r.request.target_id!==item.id)return false;
  const p=r.proof;if(!p)return false;
  if(item.repair&&(r.request.batch_id!==item.repair.batch_id||r.request.task_id!==item.task))return false;
  if(p.group_id){const g=scene.groups.find(g=>g.id===p.group_id&&!g.deleted);if(!g)return false;
   return !!(p.reference&&canonical(g.asset_reference)===canonical(p.reference)||p.generated&&canonical(g.generated_reference)===canonical(p.generated)||p.materials&&Object.keys(p.materials).length&&Object.entries(p.materials).every(([id,ref])=>ref&&canonical(scene.objects.find(o=>o.id===id)?.material.asset_reference)===canonical(ref)));
  }
  if(p.door_id)return p.model_id===scene.model_id&&canonical(scene.door_controls?.find(c=>c.opening_id===p.door_id))===canonical(p.control);
  if(p.point_id)return canonical(scene.viewpoints.find(v=>v.id===p.point_id))===canonical(p.point);
  return false;
 });
}
