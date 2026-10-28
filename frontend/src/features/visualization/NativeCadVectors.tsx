import {memo} from 'react';
import {sourcePoint} from './semanticSource.mjs';
import {previewColor} from './cadPreviewPalette.mjs';
import type {SourceView} from './SemanticSourceReview';
export type NativeCadData={
 geometry:{id:string;layer:string;kind:string;closed:boolean;points:[number,number][]}[];
 texts:{id:string;text:string;point:[number,number];alignment_point?:[number,number]|null;rotation?:number;height?:number;layer?:string;horizontal_alignment?:number}[];
 native_dwg:{source_sha256:string;reader:string;model_entity_count:number;layers:{name:string;model_types:Record<string,number>}[]};
};
export type BoundElement={id:string;name:string;role:string;points:[number,number][];closed:boolean;evidence:string};
export function BoundOverlay({elements,view,theme='light'}:{elements:BoundElement[];view:SourceView;theme?:'light'|'dark'}){
 const pts=(p:[number,number][])=>p.map(v=>sourcePoint(view,v).join(',')).join(' ');
 return <>{elements.filter(e=>e.role!=='furniture').map(e=><polyline key={e.id} points={pts(e.closed?[...e.points,e.points[0]]:e.points)} fill="none" stroke={previewColor(e.role==='wall'?'#386c4f':e.role==='door'?'#e17432':'#138cc0',theme)} strokeWidth={3} strokeDasharray="8 4" vectorEffect="non-scaling-stroke"><title>{e.name}：{e.evidence}</title></polyline>)}</>;
}
export default memo(function NativeCadVectors({site,view,layers,elements,overlay,theme='light'}:{site:NativeCadData;view:SourceView;layers:Set<string>;elements:BoundElement[];overlay:boolean;theme?:'light'|'dark'}){
 const pts=(p:[number,number][])=>p.map(v=>sourcePoint(view,v).join(',')).join(' ');
 return <>
 {site.geometry.filter(g=>layers.has(g.layer)).map(g=><polyline key={g.id} points={pts(g.closed?[...g.points,g.points[0]]:g.points)} fill="none" stroke={previewColor(g.kind==='HATCH'?'#a0aaa3':'#53695f',theme)} strokeWidth={g.kind==='HATCH'?.65:1} vectorEffect="non-scaling-stroke"><title>{g.id} · {g.layer} · {g.kind}</title></polyline>)}
 {site.texts.filter(t=>!t.layer||layers.has(t.layer)).map(t=>{const p=sourcePoint(view,(t.horizontal_alignment&&t.alignment_point)||t.point);return <text key={t.id} transform={`translate(${p[0]} ${p[1]}) rotate(${-(t.rotation||0)*180/Math.PI})`} fontSize={Math.max(7,(t.height||.1)*view.scale)} textAnchor={[1,4].includes(t.horizontal_alignment||0)?'middle':t.horizontal_alignment===2?'end':'start'} fill={previewColor('#245077',theme)}><title>{t.id}</title>{t.text}</text>;})}
 {overlay&&<BoundOverlay elements={elements} view={view} theme={theme}/>}
 </>;
});
