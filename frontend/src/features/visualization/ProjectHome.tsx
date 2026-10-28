import type {ReactNode} from 'react';
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import './projectHome.css';
export type LibraryProject={id:string;name:string;configured:boolean;revision:string|null;route?:'image'|'dxf'|'glb';has_intake?:boolean};
type Card=LibraryProject&{path:string;status:string;error:string|null;updated_at:number;thumbnail:string|null;available:boolean};
type Folder={folder_token:string;path:string;name:string};
export default function ProjectHome({onOpen,agentControl}:{onOpen:(project:LibraryProject)=>void;agentControl?:ReactNode}){
 const [cards,setCards]=useState<Card[]>([]),[search,setSearch]=useState(''),[sort,setSort]=useState('updated'),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const [modal,setModal]=useState(false),[folder,setFolder]=useState<Folder|null>(null),[name,setName]=useState(''),[busy,setBusy]=useState(''),[formError,setFormError]=useState('');
 const operation=useRef(''),lock=useRef(false),alive=useRef(true),dialog=useRef<HTMLDialogElement>(null),newButton=useRef<HTMLButtonElement>(null),nameInput=useRef<HTMLInputElement>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{let live=true;void api<Card[]>('/project-library').then(r=>{if(live)setCards(r);}).catch(e=>{if(live)setError(e.message);}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[]);
 useEffect(()=>{if(modal){dialog.current?.showModal();requestAnimationFrame(()=>dialog.current?.querySelector<HTMLButtonElement>('.folder-pick')?.focus());}},[modal]);
 function close(){if(busy)return;dialog.current?.close();setModal(false);requestAnimationFrame(()=>newButton.current?.focus());}
 async function pick(){if(lock.current)return;lock.current=true;setBusy('選擇資料夾…');setFormError('');try{const selected=await api<Folder|null>('/project-library/folders/pick','POST');if(selected&&alive.current){setFolder(selected);setName(selected.name);requestAnimationFrame(()=>nameInput.current?.focus());}}catch(e){if(alive.current)setFormError((e as Error).message);}finally{lock.current=false;if(alive.current)setBusy('');}}
 async function create(){if(lock.current||!folder)return;lock.current=true;setBusy('建立專案…');setFormError('');try{const project=await api<LibraryProject>('/project-library','POST',{folder_token:folder.folder_token,name:name.trim(),operation_id:operation.current});if(alive.current){dialog.current?.close();onOpen(project);}}catch(e){if(alive.current)setFormError((e as Error).message);}finally{lock.current=false;if(alive.current)setBusy('');}}
 const visible=cards.filter(c=>c.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).sort((a,b)=>sort==='name'?a.name.localeCompare(b.name):b.updated_at-a.updated_at);
 return <main className="project-home"><header className="project-home-heading"><div><small>ROOMWEAVER STUDIO</small><h1>我的專案</h1><p>從一個空間開始，接續每一次設計。</p></div><div className="project-home-actions">{agentControl}<button ref={newButton} className="primary" onClick={()=>{setFolder(null);setName('');setFormError('');operation.current=crypto.randomUUID().replaceAll('-','');setModal(true);}}>＋新建專案</button></div></header>
  <div className="project-home-tools"><label>搜尋專案<input placeholder="搜尋專案名稱…" value={search} onChange={e=>setSearch(e.target.value)}/></label><label>排序<select value={sort} onChange={e=>setSort(e.target.value)}><option value="updated">最近更新</option><option value="name">專案名稱</option></select></label></div>
  {error&&<p role="alert">{error}</p>}{loading?<p role="status">正在讀取專案…</p>:<><p className="project-count">{visible.length} 個專案</p><div className="project-card-grid">{visible.map(card=><button key={card.id} className="project-card" disabled={!card.available} onClick={()=>onOpen(card)} aria-label={`開啟專案：${card.name}`}>
   <div className="project-card-preview">{card.thumbnail?<img src={card.thumbnail} alt="專案預覽" loading="lazy" onError={e=>{e.currentTarget.style.visibility='hidden';}}/>:<span aria-hidden="true">⌂</span>}<span className="project-stage">{card.status}</span></div>
   <div className="project-card-body"><strong>{card.name}</strong><small className="project-folder" title={card.path}>{card.path.replaceAll('\\','/').split('/').filter(Boolean).slice(-2).join(' / ')}</small>{card.error&&<small className="project-card-error">{card.error}</small>}<time>{card.updated_at?new Date(card.updated_at*1000).toLocaleDateString('zh-TW'):'位置待確認'}</time></div>
  </button>)}</div>{!visible.length&&<div className="project-home-empty"><h2>{cards.length?'找不到符合的專案':'建立你的第一個專案'}</h2><p>{cards.length?'試試其他名稱。':'選擇空白資料夾，讓圖面、模型與成果留在同一個專案裡。'}</p></div>}</>}
  {modal&&<dialog ref={dialog} className="new-project-dialog" aria-label="新建專案" onCancel={e=>{e.preventDefault();close();}}><form onSubmit={e=>{e.preventDefault();void create();}}><header><h2>新建專案</h2><button type="button" aria-label="關閉新建專案" disabled={!!busy} onClick={close}>×</button></header>
   <label>專案目錄<div className="project-folder-picker"><input aria-label="專案目錄" readOnly value={folder?.path||''} placeholder="選擇一個空白資料夾"/><button type="button" className="folder-pick" disabled={!!busy} onClick={()=>void pick()}>選擇資料夾</button></div></label>
   <label>專案名稱<input ref={nameInput} aria-label="專案名稱" value={name} onChange={e=>setName(e.target.value)} disabled={!folder||!!busy} maxLength={120}/></label><p>名稱預設為資料夾名稱；修改名稱不會重新命名資料夾。</p>
   {(busy||formError)&&<p role={formError?'alert':'status'}>{formError||busy}</p>}<footer><button type="button" disabled={!!busy} onClick={close}>取消</button><button className="primary" disabled={!folder||!name.trim()||!!busy} type="submit">建立並開始匯入</button></footer>
  </form></dialog>}
 </main>;
}
