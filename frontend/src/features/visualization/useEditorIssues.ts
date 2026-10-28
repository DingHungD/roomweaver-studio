import {useEffect,useState} from 'react';
import {api} from './api';
import type {EditorIssue} from './editorDiagnostics';
const empty={issues:[] as EditorIssue[],error:''};
export function useEditorIssues(project:string,revision:string|null,active=true){
 const [data,setData]=useState<{project:string;revision:string|null;issues:EditorIssue[];error:string}>({project:'',revision:null,issues:[],error:''});
 useEffect(()=>{if(!revision||!active)return;let live=true,inFlight=false;
  async function read(){if(inFlight)return;inFlight=true;try{const r=await api<{revision:string;issues:EditorIssue[]}>(`/projects/${project}/editor-issues?revision=${encodeURIComponent(revision!)}`);if(live&&r.revision===revision)setData({project,revision,issues:r.issues,error:''});}catch(e){if(live)setData({project,revision,issues:[],error:(e as Error).message});}finally{inFlight=false;}}
  void read();const timer=setInterval(()=>void read(),5000);return()=>{live=false;clearInterval(timer);};
 },[project,revision,active]);
 return data.project===project&&data.revision===revision?data:empty;
}
