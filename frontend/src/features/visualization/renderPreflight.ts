import type {Scene} from './api';

export type RenderReadiness={status:string;light_count:number;world_available:boolean;issues:string[];missing_images?:string[];emissive_materials?:string[]};
export type RenderIssue={id:string;title:string;detail:string;step:0|1|2|3;action:string};

/** Only definite omissions block here; Blender probes remain the lighting authority. */
export function renderPreflight(scene:Scene|null,revision:string|null,confirmed:string|null,dirty:boolean,report:RenderReadiness|null,currentRevision=revision):RenderIssue[]{
  if(!scene||!revision)return [{id:'import',title:'尚未匯入設計',detail:'先匯入模型或開啟已保存的設計。',step:0,action:'前往匯入'}];
  if(currentRevision!==revision)return [{id:'revision',title:'此頁的設計版本已過期',detail:'另一個頁面已保存新版。請先保留目前草稿內容，再從匯入頁開啟已保存設計；不會自動覆蓋此頁草稿。',step:0,action:'前往匯入'}];
  const issues:RenderIssue[]=[];
  if(report?.missing_images?.length)issues.push({id:'textures',title:'模型缺少貼圖',detail:`找不到：${report.missing_images.join('、')}。請補齊並重新匯入完整模型，調亮燈光無法修復貼圖。`,step:0,action:'前往匯入'});
  const setup=scene.lighting_setup;
  if(setup?.enabled){
    const emitting=setup.lights.some(l=>l.enabled&&l.power>0&&l.color.some(c=>c>0)&&!scene.groups.find(g=>g.id===l.group_id)?.deleted&&(setup.mode!=='indoor'||l.kind!=='SUN'));
    const environment=setup.mode==='day'||(setup.mode==='existing'&&(report?.world_available||!!setup.source_job_id));
    // A restored World or emissive shader may illuminate even without lamp objects.
    if(!emitting&&!environment&&report?.emissive_materials?.length===0)issues.push({id:'lighting',title:'目前沒有可用照明',detail:'請啟用至少一盞有亮度及光色的光源，或選用日間環境。已關閉、零功率、黑色光源及已刪除燈具不會照亮場景。',step:2,action:'前往光影設定'});
  }else if(report?.status==='blocked'&&(!report.missing_images?.length||(report.light_count===0&&!report.world_available&&!report.emissive_materials?.length))){
    issues.push({id:'lighting',title:'原模型尚未具備出圖條件',detail:report.issues.join('；')||'請先配置照明，再確認設計。',step:2,action:'前往光影設定'});
  }
  if(!scene.viewpoints.length)issues.push({id:'viewpoints',title:'尚未設定觀看點',detail:'至少新增一個觀看點以產生全景；效果圖方向可按需要增加，不是必填項目。',step:3,action:'前往觀看點'});
  if(dirty||confirmed!==revision)issues.push({id:'confirmation',title:dirty?'編輯修改尚未保存與確認':'尚未確認目前版本的編輯',detail:'請檢查材質、光影與觀看點，再按「確認編輯，前往整合輸出」。這個動作會保存修改並確認版本，不會立即渲染。',step:3,action:'前往確認編輯'});
  return issues;
}
