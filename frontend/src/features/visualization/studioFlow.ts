/** A merged UI step retains the existing persisted design checkpoints. */
export async function confirmDesignRevision(revision:string,includePoints:boolean,confirm:(phase:string,revision:string)=>Promise<unknown>){
  for(const phase of includePoints?['spaces','materials','viewpoints']:['spaces','materials'])await confirm(phase,revision);
}
export function renderReady(revision:string|null,confirmed:string|null,dirty:boolean){
  return !!revision&&!dirty&&revision===confirmed;
}
