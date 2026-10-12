import {EditorTools,EditorInspector} from './EditorWorkspace';
import EditorToolbar from './EditorToolbar';
import {useState} from 'react';
import {fileUrl} from './api';
import type {Scene,Revision} from './api';
import StagingPanel from './StagingPanel';
import SpaceViewport from './SpaceViewport';
import LightingPanel from './LightingPanel';
import {lightPosition,placeLight,newLight} from './lightGeometry';

export default function LightEditor(props:{model:string;onAccept:(r:Revision)=>void;onContinue:()=>void;active:boolean;canUndo:boolean;onUndo:()=>void;project:string;revision:string|null;scene:Scene;dirty:boolean;busy:boolean;onChange:(s:Scene)=>void;onSave:()=>Promise<string|null|undefined>}){
  const {scene,project,onChange}=props;
  const [viewId,setViewId]=useState(scene.viewpoints[0]?.id||'');
  const [softLighting,setSoftLighting]=useState(true);
  const [explain,setExplain]=useState(false);
  const [mode,setMode]=useState<'plan'|'walk'>('plan');
  const [selected,setSelected]=useState(''),[center,setCenter]=useState<[number,number]>([0,0]);
  return <section className="space-editor light-editor"><EditorTools>
    <StagingPanel {...props} kind="lighting" toolbar={(configure,locked)=><EditorToolbar views={<><button role="tab" aria-selected={mode==='plan'} onClick={()=>setMode('plan')}>2D 平面圖</button><button role="tab" aria-selected={mode==='walk'} onClick={()=>setMode('walk')}>3D 畫面</button></>} actions={<><button disabled={locked||props.busy} onClick={()=>{const next=structuredClone(scene);next.lighting_setup||={enabled:true,mode:'existing',exposure:0,auto_adjust:true,agent_review:false,lights:[]};const l=newLight([...center,2.5]);next.lighting_setup.enabled=true;next.lighting_setup.lights.push(l);onChange(next);setSelected(l.id);setMode('plan');}}>＋ 新增光源</button>{configure}<button disabled={locked||!props.canUndo||props.busy} onClick={props.onUndo}>復原上一步</button></>}><span>{scene.lighting_setup?.lights.length||0} 個光源 · 家具位置鎖定</span></EditorToolbar>}/>
    {mode==='walk'&&!!scene.viewpoints.length&&<label className="lighting-preview-eye">預覽位置<select value={viewId} onChange={e=>setViewId(e.target.value)}>{scene.viewpoints.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
    {mode==='walk'&&<div className="lighting-preview-explanation" role="note"><label className="inline-check"><input type="checkbox" checked={softLighting} onChange={e=>setSoftLighting(e.target.checked)}/>柔和光影預覽</label><p>{softLighting?'以近似反射光提亮暗部，優先為選取的面光源分散光線與陰影；關閉可對照原直接光。':'目前只顯示直接光，背光面可能偏黑。'} 只影響操作畫面，不修改燈光或出圖設定。</p><button onClick={()=>setExplain(v=>!v)} aria-expanded={explain}>預覽與成圖的差異</button>{explain&&<p>柔和預覽依有效燈光估算環境補光，沒有追蹤隔間反射，因此隔壁房間也可能偏亮。最多兩盞面光源使用四點取樣近似柔影；仍非 Cycles 的完整間接光，請以低解析出圖確認實際效果。</p>}</div>}
    </EditorTools><div className="space-editor-grid"><div>
      {props.active&&<SpaceViewport url={fileUrl(project,scene.model_id,'model.glb')} design={scene} mode={mode} focusPoint={scene.viewpoints.find(p=>p.id===viewId)} selected="" child="" moving={false} onSelect={()=>{}} onMove={()=>{}}
        lightEditing softLighting={softLighting} lightId={selected} onLightSelect={setSelected} onPlanCenter={setCenter}
        onLightMove={(id,xy)=>{const next=structuredClone(scene);const lights=next.lighting_setup!.lights;const i=lights.findIndex(l=>l.id===id);if(i<0)return;const pos=lightPosition(lights[i],next);lights[i]=placeLight(lights[i],next,[...xy,pos[2]]);onChange(next);}}/>}
      <div className="space-bottom"><span>{mode==='plan'?'點選／拖曳光源調整平面位置，高度與方向在右側微調。':'在右側調整亮度、光色、位置與方向，3D 即時更新；W/S 行走、A/D 水平平移，拖曳環看。'}</span><button className="primary" disabled={props.busy} onClick={props.onContinue}>設定觀看點 →</button></div>
      {mode==='walk'&&<p className="light-preview-note">即時近似光影：最多顯示 24 盞來源光源；柔和模式另含面光源取樣、最多 8 張陰影圖及近似反射補光。未載入原生環境貼圖，不等同 Cycles 的精確光照；最終效果請於整合輸出試渲染。{!scene.lighting_setup?.enabled?' 尚未啟用照明設定，請先配置或開啟設定。':''}</p>}
    </div><EditorInspector className="light-inspector"><LightingPanel {...props} selected={selected} onSelect={setSelected} center={center}/></EditorInspector></div>
  </section>;
}
