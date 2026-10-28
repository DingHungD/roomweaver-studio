import type {ObjectGroup} from './api';
import type {Scene} from './api';

// Null means an older scene: use its existing batch supplement/import brief.
// Empty string is an explicit user choice and must survive reload and undo.
export function objectStyle(group:ObjectGroup|undefined,legacy?:string):string {
  return group?.style_prompt??legacy??group?.design_prompt??'';
}
export function styleIndependentSceneKey(scene:Scene):string {
  return JSON.stringify({...scene,groups:scene.groups.map(({style_prompt,...group})=>group)});
}
export function modelOrigin(group:ObjectGroup):string {
  if(group.asset_reference?.status==='applied')return '網路素材（BlenderKit）';
  if(group.generated_reference)return 'AI 自行繪製（概念參數模型）';
  if(group.method==='concept')return '工具建立的概念模型';
  return '原始匯入模型';
}
