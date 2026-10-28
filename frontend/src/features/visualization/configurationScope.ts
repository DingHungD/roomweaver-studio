import type {Scene,ObjectGroup,StudioLight} from './api';
import {isDecoration} from './placementArea.ts';
import {incompleteItems} from './configurationIncomplete.ts';
import type {ConfigurationRow} from './configurationIncomplete';
export type ConfigurationScope='furniture'|'decor'|'lighting';
const scopeCache=new WeakMap<Scene,WeakMap<ObjectGroup,ConfigurationScope>>();
const nameCache=new WeakMap<Scene,Map<string,string>>();
const groupCache=new WeakMap<Scene,Map<string,ObjectGroup>>();
const lampPurpose=/^(ceiling_light|floor_lamp|pendant|lamp|light|wall_light|table_lamp)$/i;
function detectScope(scene:Scene,g:ObjectGroup):ConfigurationScope{
 if(g.method==='structural_wall'||g.method==='structural_floor')return 'furniture';
 const concept=scene.concept_furniture?.find(f=>f.id===g.id);
 if(scene.lighting_setup?.lights.some(l=>l.group_id===g.id)||lampPurpose.test(concept?.asset||'')||lampPurpose.test(g.asset_requirements?.purpose||'')||lampPurpose.test(g.object_specification?.purpose||'')||/^(天花燈具|落地燈)|\b(ceiling[ _-]light|floor[ _-]lamp|pendant[ _-]light)\b/i.test(g.name))return 'lighting';
 return isDecoration(scene,g)?'decor':'furniture';
}
export function configurationScope(scene:Scene,g:ObjectGroup):ConfigurationScope{
 let cache=scopeCache.get(scene);if(!cache){cache=new WeakMap();scopeCache.set(scene,cache);}
 let value=cache.get(g);if(!value){value=detectScope(scene,g);cache.set(g,value);}return value;
}
export function configurationName(scene:Scene,g:ObjectGroup):string{
 let cache=nameCache.get(scene);if(!cache){cache=new Map();nameCache.set(scene,cache);}
 const cached=cache.get(g.id);if(cached!==undefined)return cached;
 // Legacy generated fixture labels appended the supporting floor's internal ID.
 // Present a fixture identity without renaming saved objects or user labels.
 const generated=g.name.match(/^(天花燈具|落地燈) · (?:地板|地坪|floor)/i);
 if(!generated||configurationScope(scene,g)!=='lighting')return g.name;
 const fixtures=scene.groups.filter(x=>configurationScope(scene,x)==='lighting');
 const number=String(fixtures.findIndex(x=>x.id===g.id)+1).padStart(2,'0');
 const room=scene.rooms.find(r=>r.id===scene.objects.find(o=>g.children.includes(o.id))?.room_id);
 const label=`${generated[1]} ${number}${room&&!/待分區|待確認/.test(room.name)?` · ${room.name}`:''}`;cache.set(g.id,label);return label;
}
export function lightDisplayName(scene:Scene,light:StudioLight):string{
 let groups=groupCache.get(scene);if(!groups){groups=new Map(scene.groups.map(g=>[g.id,g]));groupCache.set(scene,groups);}
 const group=groups.get(light.group_id||'');
 return group&&light.name===group.name+' 光源'?configurationName(scene,group)+' 光源':light.name;
}
export function scopedIncompleteItems(batch:{status:string;items:ConfigurationRow[]}|null,scene:Scene,scope:ConfigurationScope){
 if(!batch)return [];
 const groups=new Map(scene.groups.map(g=>[g.id,g]));
 const rows=batch.items.filter(row=>{
  const group=groups.get(row.group_id||'')||{id:row.group_id||row.task_id,name:row.name,children:[],translation:[0,0,0] as [number,number,number],deleted:false,method:''};
  return configurationScope(scene,group)===scope;
 });
 return incompleteItems({...batch,items:rows},scene.groups).map(item=>({...item,name:groups.has(item.id)?configurationName(scene,groups.get(item.id)!):item.name}));
}
