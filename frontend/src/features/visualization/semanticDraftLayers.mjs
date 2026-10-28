import {sourcePoint} from './semanticSource.mjs';
// Draft layers reference Q answers and independent M correction records, never editable CAD objects.
export function semanticDraftLayers(questions,answers,annotations,manual=[]){
 const fromQuestions=questions.flatMap(question=>{
  const answer=answers[question.id]||'',marks=annotations[question.id]||[];
  if(!answer.trim()&&!marks.length)return [];
  const points=marks.flatMap(mark=>mark.points);
  const box=points.length?[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]:question.box;
  return [{id:question.id,label:question.label,title:question.title,answer,marks,box}];
 });
 return [...fromQuestions,...manual.flatMap((item,index)=>{
  if(!item.comment.trim()&&!item.marks.length)return [];
  const points=item.marks.flatMap(mark=>mark.points);
  const box=points.length?[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]:null;
  return [{id:'manual:'+item.id,label:`M${index+1}`,title:item.title,answer:item.comment,marks:item.marks,box}];
 })];
}

export function draftCaptionLayouts(drafts,view,scale){
 const placed=[];
 for(const draft of drafts){
  if(!draft.box)continue;
  const anchor=sourcePoint(view,[draft.box[0],draft.box[3]]);
  const chars=Array.from(draft.answer.trim()),note=chars.slice(0,35).join('')+(chars.length>35?'…':'');
  const width=Math.max(130,Math.min(480,Array.from(note).length*12+20)),height=note?45:24;
  let offset=-height-6;
  const overlaps=p=>anchor[0]*scale<p.x+p.width+6&&anchor[0]*scale+width+6>p.x&&anchor[1]*scale+offset<p.y+p.height+6&&anchor[1]*scale+offset+height+6>p.y;
  while(placed.some(overlaps))offset-=height+8;
  placed.push({id:draft.id,anchor,note,width,height,offset,x:anchor[0]*scale,y:anchor[1]*scale+offset});
 }
 return placed;
}
