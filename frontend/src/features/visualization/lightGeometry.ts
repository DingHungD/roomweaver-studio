import type {Scene,StudioLight,LightingSetup} from './api';
export const defaultLighting=():LightingSetup=>({enabled:false,mode:'existing',exposure:0,auto_adjust:true,agent_review:false,lights:[]});
export function lightPosition(light:StudioLight,scene:Scene):[number,number,number]{
  const delta=scene.groups.find(g=>g.id===light.group_id)?.translation||[0,0,0];
  return light.position.map((v,i)=>v+delta[i]) as [number,number,number];
}
// Stored coordinates are relative to the group's original placement, matching Blender.
export function placeLight(light:StudioLight,scene:Scene,world:number[]):StudioLight{
  const delta=scene.groups.find(g=>g.id===light.group_id)?.translation||[0,0,0];
  return {...light,position:world.map((v,i)=>v-delta[i]) as [number,number,number]};
}
export function bindLight(light:StudioLight,scene:Scene,group_id:string|null):StudioLight{
  return placeLight({...light,group_id},scene,lightPosition(light,scene));
}
export function newLight(position:[number,number,number],name='新增面光源'):StudioLight{
  return {id:crypto.randomUUID().replaceAll('-',''),name,kind:'AREA',position,rotation:[0,0,0],power:150,color:[1,.85,.65],size:1,angle:90,enabled:true,locked:false,group_id:null,origin:'manual'};
}
