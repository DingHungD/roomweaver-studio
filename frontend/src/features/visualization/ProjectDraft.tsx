import {createContext,useContext,useEffect,useId,useRef} from 'react';
export type ProjectDraft={dirty:boolean;save?:()=>Promise<void>;blocked?:boolean;label:string};
export const ProjectDraftContext=createContext<((id:string,draft:ProjectDraft|null)=>void)|null>(null);
/** Optional integration: existing standalone intake components keep working. */
export function useProjectDraft(draft:ProjectDraft){
 const register=useContext(ProjectDraftContext),id=useId(),latest=useRef(draft);latest.current=draft;
 useEffect(()=>{register?.(id,{...draft,save:draft.save?()=>latest.current.save!():undefined});return()=>register?.(id,null);},[register,id,draft.dirty,draft.blocked,!!draft.save]);
}
