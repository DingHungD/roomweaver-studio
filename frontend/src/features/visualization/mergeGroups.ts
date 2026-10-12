import type {Scene} from './api';
export function mergeGroups(scene:Scene,keep:string,others:string[]):Scene {
 const ids=new Set([keep,...others]);const groups=scene.groups.filter(g=>ids.has(g.id));
 if(groups.length!==ids.size||groups.length<2||groups.some(g=>g.deleted))throw new Error('請選擇至少兩個有效物件');
 const first=groups.find(g=>g.id===keep)!;
 const transform=(g:typeof first)=>JSON.stringify([g.translation,g.rotation||0,g.rotation_pivot||[0,0,0]]);
 if(groups.some(g=>transform(g)!==transform(first)))throw new Error('物件位移或旋轉不同，請先恢復相同變換後再合併，以免改變位置');
 if(groups.some(g=>g.asset_reference||scene.concept_furniture?.some(f=>f.id===g.id)))throw new Error('目前只能合併原始模型組件；已替換素材與概念家具各自保留來源');
 const next=structuredClone(scene);const target=next.groups.find(g=>g.id===keep)!;
 target.children=groups.flatMap(g=>g.children);target.method='manual_merge';
 next.groups=next.groups.filter(g=>g.id===keep||!ids.has(g.id));
 next.lighting_setup?.lights.forEach(l=>{if(l.group_id&&ids.has(l.group_id))l.group_id=keep;});
 return next;
}
