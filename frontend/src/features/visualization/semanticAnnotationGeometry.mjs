// All edits stay in immutable source coordinates, independent of pan or zoom.
export function annotationHandles(mark){
 if(mark.kind==='text')return [];
 if(mark.kind==='box'){
  const [a,b]=mark.points,x0=Math.min(a[0],b[0]),x1=Math.max(a[0],b[0]),y0=Math.min(a[1],b[1]),y1=Math.max(a[1],b[1]);
  return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]];
 }
 return [mark.points[0],mark.points.at(-1)];
}
export function editAnnotation(mark,start,current,handle,view){
 const left=view.bounds[0]-view.pad/view.scale,right=left+view.width/view.scale;
 const top=view.bounds[3]+view.pad/view.scale,bottom=top-view.height/view.scale;
 const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
 let points=mark.points.map(p=>[...p]);
 if(handle!==null&&mark.kind!=='text'){
  const p=[clamp(current[0],left,right),clamp(current[1],bottom,top)];
  if(mark.kind==='box'){
   const other=annotationHandles(mark)[(handle+2)%4];
   if(Math.abs(p[0]-other[0])<1e-6||Math.abs(p[1]-other[1])<1e-6)return mark;
   points=[other,p];
  }else{
   points[handle===0?0:points.length-1]=p;
   if(!points.some(q=>Math.hypot(q[0]-points[0][0],q[1]-points[0][1])>1e-6))return mark;
  }
 }else{
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const dx=clamp(current[0]-start[0],left-Math.min(...xs),right-Math.max(...xs));
  const dy=clamp(current[1]-start[1],bottom-Math.min(...ys),top-Math.max(...ys));
  points=points.map(p=>[p[0]+dx,p[1]+dy]);
 }
 return {...mark,points};
}
