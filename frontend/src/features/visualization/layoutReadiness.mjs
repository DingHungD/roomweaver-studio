/** Explain every prerequisite; missing inputs never become a silent dead button. */
export function layoutBlockers({dirty,planStatus,errors=/** @type {string[]} */([]),busy,waiting,brief,needs,model,width,contextStale=false}) {
  const out=[];
  if(busy||waiting)out.push({target:'layout-status',text:waiting?'配置工作執行中，可等待或停止。':'正在處理要求，請稍候。'});
  if(dirty)out.push({target:'plan-save',text:'平面有未保存修改：先保存並檢查。'});
  if(planStatus!=='ready')out.push({target:'plan-validation',text:'平面尚未通過檢查：'+(errors[0]||'請回到核對平面查看原因。')});
  if(contextStale)out.push({target:'layout-context',text:'既有需求包對應舊平面版本，請重新核對，或改用自行填寫的需求。'});
  if(brief.trim().length<10)out.push({target:'layout-brief-input',text:'請填寫生活需求與設計方向（至少 10 個字）。'});
  const list=needs.split('\n').map(s=>s.trim()).filter(Boolean);
  if(!list.length||list.length>25||list.some(s=>s.length>500))out.push({target:'layout-needs-input',text:'請填寫 1～25 項必須滿足的需求，每行一項，每項不超過 500 字。'});
  if(!model)out.push({target:'layout-model-input',text:'請連接配置 Agent，並選擇可用模型。'});
  if(!Number.isFinite(width)||width<.5||width>2)out.push({target:'layout-width-input',text:'請填入 0.5～2 公尺的通道目標。'});
  return out;
}
