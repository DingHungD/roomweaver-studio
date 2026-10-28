import {memo,useMemo,useId} from 'react';
import type {CSSProperties} from 'react';
import type {SourceView} from './SemanticSourceReview';
import {cadSourceTransform} from './cadSourceProjection.mjs';
import {previewColor,previewStyle,previewPalettes} from './cadPreviewPalette.mjs';
export type CadSource={version:string;markup:string;width:number;height:number;viewBox:string;matrix:[number,number,number,number,number,number];view:SourceView;full_bounds:[number,number,number,number];layers:string[];source_sha256:string;original_sha256:string;source_entities:number;drawing_paths:number;limitations:string[];missing_glyphs?:boolean};
export default memo(function CadSourceDrawing({drawing,view,origin,factor,layers,clipToMain=true,theme='light',screenScale=1}:{drawing:CadSource;view:SourceView;origin:[number,number];factor:number;layers:Set<string>;clipToMain?:boolean;theme?:'light'|'dark';screenScale?:number}){
 const clip='cadClip'+useId().replaceAll(':','');
 const layerKey=[...layers].sort().join('\u0000');
 const markup=useMemo(()=>{
  // The server generates SVG paths from CAD, never forwards arbitrary SVG/HTML.
  // Keep original draw order and only toggle paths belonging to each CAD layer.
  const doc=new DOMParser().parseFromString(`<svg xmlns="http://www.w3.org/2000/svg">${drawing.markup}</svg>`,'image/svg+xml');
  for(const node of doc.querySelectorAll('style'))node.textContent=previewStyle(node.textContent||'',theme).replace(/\bstroke-width:\s*([\d.]+)\s*;/g,'stroke-width: max($1px, var(--cad-min-line, 0px));');
  for(const node of doc.querySelectorAll('[fill],[stroke],[style]')){
   for(const attr of ['fill','stroke'])if(node.hasAttribute(attr))node.setAttribute(attr,previewColor(node.getAttribute(attr)!,theme));
   if(node.hasAttribute('style'))node.setAttribute('style',previewStyle(node.getAttribute('style')!,theme));
  }
  // The source renderer emits an untagged page rectangle, not CAD geometry.
  for(const node of doc.documentElement.children)if(node.localName==='rect'&&!node.hasAttribute('data-cad-handle'))node.setAttribute('fill',previewPalettes[theme].background);
  for(const node of doc.querySelectorAll('[data-cad-layer]'))if(!layers.has(node.getAttribute('data-cad-layer')!))node.setAttribute('display','none');
  return [...doc.documentElement.children].map(n=>new XMLSerializer().serializeToString(n)).join('');
 },[drawing,layerKey,theme]);
 const matrix=cadSourceTransform(drawing.matrix,view,origin,factor),transform='matrix('+matrix.join(' ')+')';
 // A CSS variable makes thin strokes readable without reparsing paths on zoom.
 const style={'--cad-min-line':`${.8/Math.max(1e-12,Math.hypot(matrix[0],matrix[1])*screenScale)}px`} as CSSProperties;
 return <g aria-label="來源CAD原圖" data-source-version={drawing.version} transform={transform} style={style}><defs><clipPath id={clip}><rect width={drawing.width} height={drawing.height}/></clipPath></defs><g clipPath={clipToMain?`url(#${clip})`:undefined} dangerouslySetInnerHTML={{__html:markup}}/></g>;
});
