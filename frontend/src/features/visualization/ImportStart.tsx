import {useRef} from 'react';
import './importStart.css';
export type ImportRoute='image'|'dxf'|'glb';
export const importRoutes:{id:ImportRoute;title:string;formats:string;description:string;accept:string}[]=[
 {id:'image',title:'從圖片建立',formats:'PNG／JPG',description:'辨識圖面、確認尺度與配置，再建立概念 3D。',accept:'.png,.jpg,.jpeg'},
 {id:'dxf',title:'從電子平面建立',formats:'DWG／DXF',description:'DWG 自動轉檔；確認圖面單位、牆門窗與高度，再建立 3D。',accept:'.dwg,.dxf'},
 {id:'glb',title:'完整 3D 直接出圖／網站',formats:'GLB／SKP',description:'SKP 在本機自動轉檔；保留原模型的材質與位置，直接生成效果圖和展示網站。',accept:'.glb,.skp'},
];
export default function ImportStart({disabled,examples,onFile,onExample}:{disabled:boolean;examples:Partial<Record<ImportRoute,boolean>>;onFile:(route:ImportRoute,file:File)=>void;onExample:(route:ImportRoute)=>void}){
 const inputs=useRef<Partial<Record<ImportRoute,HTMLInputElement|null>>>({});
 return <><h2>從哪一種設計開始？</h2><p>選擇入口，從電腦開啟檔案；也可用 Project04 範例練習。</p>
  <div className="import-routes">{importRoutes.map(route=><article className="import-route-card" key={route.id}>
   <button className="import-route-select" disabled={disabled} onClick={()=>inputs.current[route.id]?.click()} aria-label={route.title}>
    <small>{route.formats}</small><strong>{route.title}</strong><span>{route.description}</span><span className="import-route-open">選擇檔案 ↗</span>
   </button>
   <footer><span>Project04 範例</span><button disabled={disabled||!examples[route.id]} onClick={()=>onExample(route.id)} aria-label={`${route.title}：開啟範例`}>開啟範例</button></footer>
   {!examples[route.id]&&<small className="import-example-missing">範例檔案未安裝</small>}
   <input ref={node=>{inputs.current[route.id]=node;}} hidden type="file" accept={route.accept} aria-label={`${route.title}檔案`} onChange={e=>{const file=e.currentTarget.files?.[0];if(file)onFile(route.id,file);e.currentTarget.value='';}}/>
  </article>)}</div>
 </>;
}
