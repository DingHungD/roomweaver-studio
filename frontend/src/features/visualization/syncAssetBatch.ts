import type {Revision} from './api';

// Publishing a terminal status stops polling. Load its model BEFORE that cleanup.
export async function syncAssetBatch<T extends {placement_revision?:string}>(
 batch:T, current:()=>{revision:string|null;dirty:boolean;onAccept:(r:Revision)=>void},
 fetchScene:()=>Promise<Revision>, active:()=>boolean, publish:(b:T)=>void,
){
 if(!active())return;
 const state=current();
 if(batch.placement_revision&&batch.placement_revision!==state.revision&&!state.dirty){
  const result=await fetchScene();
  if(active()&&!current().dirty)current().onAccept(result);
 }
 if(active())publish(batch);
}
