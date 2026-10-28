// Source image coordinates are immutable even when its display is rotated.
export function displayPoint(point, height, turned) {
  return turned ? [height - point[1], point[0]] : point;
}
export function sourcePoint(point, height, turned) {
  return turned ? [point[1], height - point[0]] : point;
}
export function buildBlockers({image, settings, questions, dirty, calibrating, busy, confirmed, check, intake}) {
  const reasons=[];
  const unnamed=(settings.assignments||[]).filter(a=>!a.name?.trim());
  if(unnamed.length) reasons.push({target:'plan-properties',text:`有 ${unnamed.length} 個元件名稱空白（${unnamed.map(a=>a.id).join('、')}），請填寫名稱後保存。`});
  if(busy) reasons.push({target:'plan-validation',text:`正在${busy}，完成後才能建立。`});
  if(calibrating) reasons.push({target:'plan-scale',text:'比例尺選點尚未完成：請選第二點或取消選點。'});
  if(image && !settings.calibration?.confirmed) reasons.push({target:'plan-scale',text:'尚未確認比例尺端點及實際長度。'});
  const pending=questions.filter(q=>!(settings.reviewed||[]).includes(q.id));
  if(image && pending.length) reasons.push({target:'plan-questions',text:`還有 ${pending.length} 項辨識疑點未確認。填寫回答或畫 A→B 不會自動勾選；先核對並修正，再確認或明確接受為概念假設。`});
  if(dirty) reasons.push({target:'plan-save',text:'修改尚未保存：請先「保存並檢查平面」，取得這次修改的檢查結果。'});
  if(intake?.status!=='ready' && intake) for(const text of intake.errors) reasons.push({target:intake.layout_mode==='generate'&&text.includes('AI 空間配置')?'plan-layout':'plan-semantics',text});
  if(!dirty && check.status!=='ready') reasons.push({target:'plan-validation',text:'保存版本尚未通過平面檢查，請處理下方列出的原因。'});
  if(!confirmed) reasons.push({target:'plan-consent',text:'尚未完成最後建模確認；保存且檢查通過後，下方確認框才會開放。'});
  return reasons;
}
