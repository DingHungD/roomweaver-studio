import type {Scene,ConceptFurniture,ObjectGroup} from './api';
export type PlacementArea={center:[number,number];size:[number,number];height:number};
export const decorAssets=new Set(['vase','books','cookware','tableware','soap','plant','rug']);
export function makeArea(a:[number,number],b:[number,number],height=0):PlacementArea {
 if(![...a,...b,height].every(Number.isFinite))throw new Error('範圍座標無效');
 const mm=(n:number)=>Math.round(n*1000)/1000;
 return {center:[mm((a[0]+b[0])/2),mm((a[1]+b[1])/2)],size:[mm(Math.abs(a[0]-b[0])),mm(Math.abs(a[1]-b[1]))],height:mm(height)};
}
export function isDecoration(scene:Scene,g:ObjectGroup){
 if(g.editor_kind)return g.editor_kind==='decor';
 const f=scene.concept_furniture?.find(f=>f.id===g.id);
 return !!f&&decorAssets.has(f.asset)||/^(花瓶|書籍|鍋具|餐具|洗手乳|地毯|盆栽)|\b(vase|rug|books|cookware|tableware)\b/i.test(g.name);
}
export function addPlacedItem(scene:Scene,f:ConceptFurniture,position:[number,number,number],kind:'furniture'|'decor',prompt:string,url:string,room:string|null):Scene{
 if(scene.groups.some(g=>g.id===f.id))throw new Error('此元件已新增，請選取現有元件');
 const s=structuredClone(scene);
 s.concept_furniture=[...(s.concept_furniture||[]),f];
 s.groups.push({id:f.id,name:f.name,children:f.parts.map(p=>p.id),translation:position,deleted:false,method:'concept',editor_kind:kind,design_prompt:prompt,model_url:url});
 s.objects.push(...f.parts.map(p=>({id:p.id,name:p.name,room_id:room,material:{description:'概念占位，尚未選定模型',url:'',color:null,roughness:.7}})));
 return s;
}
