import type {Scene,StudioLight,LightingSetup} from './api';
export const defaultLighting=():LightingSetup=>({enabled:false,mode:'existing',exposure:0,auto_adjust:true,agent_review:false,lights:[]});
function transformLight(light:StudioLight,scene:Scene,point:number[],inverse=false):[number,number,number]{
  const group=scene.groups.find(g=>g.id===light.group_id),delta=group?.translation||[0,0,0],pivot=group?.rotation_pivot||[0,0,0];
  const a=(group?.rotation||0)*Math.PI/180*(inverse?-1:1),c=Math.cos(a),s=Math.sin(a);
  const v=point.map((n,i)=>n-pivot[i]-(inverse?delta[i]:0));
  return [v[0]*c-v[1]*s+pivot[0]+(inverse?0:delta[0]),v[0]*s+v[1]*c+pivot[1]+(inverse?0:delta[1]),point[2]+(inverse?-delta[2]:delta[2])];
}
export function lightPosition(light:StudioLight,scene:Scene):[number,number,number]{return transformLight(light,scene,light.position);}
export function lightRotation(light:StudioLight,scene:Scene):[number,number,number]{return [light.rotation[0],light.rotation[1],light.rotation[2]+(scene.groups.find(g=>g.id===light.group_id)?.rotation||0)*Math.PI/180];}
export function placeLight(light:StudioLight,scene:Scene,world:number[]):StudioLight{return {...light,position:transformLight(light,scene,world,true)};}
export function bindLight(light:StudioLight,scene:Scene,group_id:string|null):StudioLight{
  return placeLight({...light,group_id},scene,lightPosition(light,scene));
}
export function newLight(position:[number,number,number],name='新增面光源'):StudioLight{
  return {id:crypto.randomUUID().replaceAll('-',''),name,kind:'AREA',position,rotation:[0,0,0],power:150,color:[1,.85,.65],size:1,angle:90,enabled:true,locked:false,group_id:null,origin:'manual'};
}
