export type ConfigurationRow={task_id:string;group_id?:string;object_id?:string|null;candidate_task_id?:string;name:string;status?:string;error?:string;placement?:{status:string;error?:string}};
export type IncompleteItem={id:string;name:string;part:string|null;task:string;status:string;reason:string;available:boolean;editable?:boolean;repair?:{category:'furniture'|'decor'|'lighting';batch_id:string};target?:{kind:'door'|'viewpoint';position:[number,number,number];bounds:[[number,number,number],[number,number,number]];shotId?:string|null}};
export function incompleteItems(batch:{status:string;items:ConfigurationRow[]}|null,groups:{id:string;deleted:boolean}[]):IncompleteItem[]{
 if(!batch)return [];
 const result=new Map<string,IncompleteItem>();
 const active=['queued','running','matching','applying','stopping'].includes(batch.status);
 for(const row of batch.items){
  const state=row.placement?.status;
  if(['installed','kept'].includes(state||''))continue;
  const error=row.placement?.error||row.error||'';
  const waiting=['waiting','queued'].includes(state||row.status||'');
  const status=error?'需要處理':waiting?(active?'等待配置':'等待繼續'):active?'配置中':'未完成';
  const reason=error||(waiting?(active?'尚未輪到此物件。':'工作已暫停或結束，此物件尚未配置。'):active?'Agent 正在處理，尚未完成套用。':'尚未成功套用模型或材質，原件保留。');
  const id=row.group_id||row.task_id,available=groups.some(g=>g.id===row.group_id&&!g.deleted);
  const previous=result.get(id);
  // One visible entry per object, even when multiple sub-material tasks failed.
  if(previous){previous.reason+='\n'+reason;if(error)previous.status='需要處理';if(previous.part!==row.object_id)previous.part=null;}
  else result.set(id,{id,name:row.name,part:row.object_id||null,task:row.candidate_task_id||row.task_id,status,reason,available});
 }
 return [...result.values()];
}
