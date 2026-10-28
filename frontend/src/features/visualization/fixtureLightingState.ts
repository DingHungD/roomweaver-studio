export type FixtureLightingResult={
  id:string;base_revision:string;status:string;phase?:string;error?:string;
  adoption?:{revision:string}|null;
  report?:{added_count?:number;restored_count?:number;uncertain_count?:number;notes:string[];
    items:{group_id:string;name:string;status:string;reason:string;light_ids?:string[];evidence?:string}[]}|null;
};
export const fixtureLightingPending=(status?:string)=>['queued','running','stopping'].includes(status||'');
export function fixtureLightingCanApply(task:FixtureLightingResult,revision:string|null,dirty:boolean){
  return task.status==='passed'&&!task.adoption&&!dirty&&task.base_revision===revision;
}
