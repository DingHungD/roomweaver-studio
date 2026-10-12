import {createContext,useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import './editorWorkspace.css';

type Panels={left:boolean;right:boolean;tools:boolean};
const initial:Panels={left:false,right:false,tools:false};
const key='roomweaver.editor-panels.v1';
function readPanels():Panels{try{const value=JSON.parse(localStorage.getItem(key)||'{}');return Object.fromEntries(Object.entries(initial).map(([k,v])=>[k,typeof value[k]==='boolean'?value[k]:v])) as Panels;}catch{return initial;}}
const Workspace=createContext<{panels:Panels;toggle:(name:keyof Panels)=>void;focus:boolean;setFocus:(value:boolean)=>void}|null>(null);
export function EditorWorkspace({editing,children}:{editing:boolean;children:ReactNode}){
 const [saved,setSaved]=useState(readPanels),[focus,setFocus]=useState(false);
 const root=useRef<HTMLDivElement>(null);
 const panels=focus?{left:true,right:true,tools:true}:saved;
 const toggle=(name:keyof Panels)=>{setFocus(false);setSaved(previous=>({...previous,[name]:!panels[name]}));};
 useEffect(()=>{try{localStorage.setItem(key,JSON.stringify(saved));}catch{/* Editing also works when storage is unavailable. */}},[saved]);
 useEffect(()=>{if(!editing)setFocus(false);},[editing]);
 useEffect(()=>{const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!event.defaultPrevented&&!document.querySelector('dialog[open],.studio-modal')&&!(event.target as Element)?.closest('input,textarea,select'))setFocus(false);};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[]);
 useLayoutEffect(()=>{
  if(!editing||!root.current)return;
  const content=root.current.querySelector<HTMLElement>('.studio-content');if(!content)return;
  let frame=0;
  const measure=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
   const title=content.querySelector<HTMLElement>('.studio-title');
   const tools=[...content.querySelectorAll<HTMLElement>('.editor-tools')].find(e=>e.getClientRects().length);
   const titleBottom=title?title.offsetTop+title.offsetHeight:0;
   content.style.setProperty('--editor-tools-top',`${titleBottom+8}px`);
   const bottom=tools&&!panels.tools?tools.offsetTop+tools.offsetHeight:titleBottom;
   content.style.setProperty('--editor-controls-bottom',`${bottom+12}px`);
   content.dispatchEvent(new Event('studio-layout',{bubbles:true}));
  });};
  const observer=new ResizeObserver(measure);
  observer.observe(content);
  content.querySelectorAll('.studio-title,.editor-tools').forEach(el=>observer.observe(el));
  measure();return()=>{cancelAnimationFrame(frame);observer.disconnect();};
 },[editing,panels.left,panels.right,panels.tools,focus]);
 return <Workspace.Provider value={{panels,toggle,focus,setFocus}}><div ref={root} className={`editor-workspace ${editing?'is-editing':''} ${panels.left?'rail-collapsed':''} ${panels.right?'inspector-collapsed':''} ${panels.tools?'tools-collapsed':''} ${focus?'is-focused':''}`}>{children}</div></Workspace.Provider>;
}
export function WorkspaceControls(){
 const state=useContext(Workspace)!;const [fullscreen,setFullscreen]=useState(()=>!!document.fullscreenElement),[error,setError]=useState('');
 useEffect(()=>{const changed=()=>setFullscreen(!!document.fullscreenElement);document.addEventListener('fullscreenchange',changed);return()=>document.removeEventListener('fullscreenchange',changed);},[]);
 async function full(){try{setError('');if(document.fullscreenElement)await document.exitFullscreen();else await document.querySelector<HTMLElement>('.editor-workspace')!.requestFullscreen();}catch{setError('此瀏覽器未能開啟全螢幕，可使用專注模式放大畫面。');}}
 return <div className="workspace-controls" role="group" aria-label="畫面配置">
  <button onClick={()=>document.dispatchEvent(new Event('studio-frame'))}>置中顯示</button>
  <button aria-expanded={!state.panels.tools} onClick={()=>state.toggle('tools')}>{state.panels.tools?'展開工具列':'收合工具列'}</button>
  <button aria-pressed={state.focus} onClick={()=>state.setFocus(!state.focus)}>{state.focus?'離開專注':'專注模式'}</button>
  <button onClick={()=>void full()} disabled={!document.fullscreenEnabled&&!fullscreen}>{fullscreen?'離開全螢幕':'全螢幕'}</button>
  {error&&<span role="alert">{error}</span>}
 </div>;
}
export function RailToggle({label}:{label:string}){const state=useContext(Workspace)!;return <button className="rail-toggle" aria-label={state.panels.left?'展開工作區':'收合工作區'} aria-expanded={!state.panels.left} onClick={()=>state.toggle('left')}>{state.panels.left?'›':'‹'}<span>{state.panels.left?label:'收合工作區'}</span></button>;}
export function EditorTools({children}:{children:ReactNode}){return <div className="editor-tools">{children}</div>;}
export function EditorInspector({children,className=''}:{children:ReactNode;className?:string}){
 const state=useContext(Workspace);
 return <><button className="inspector-open" aria-label="展開詳細編輯" aria-expanded={false} onClick={()=>state?.toggle('right')}>‹ 詳細編輯</button><aside className={`studio-inspector assembly-inspector ${className}`}>
  <div className="inspector-heading"><span>詳細編輯</span><button aria-label="收合詳細編輯" aria-expanded={true} onClick={()=>state?.toggle('right')}>收合 ›</button></div>{children}
 </aside></>;
}
