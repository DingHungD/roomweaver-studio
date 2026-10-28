// Raster coordinates are registered to the exact source view saved with a task.
export function sourcePoint(view,point) {
  return [view.pad+(point[0]-view.bounds[0])*view.scale,view.pad+(view.bounds[3]-point[1])*view.scale];
}
export function sourceWorld(view,point) {
  return [view.bounds[0]+(point[0]-view.pad)/view.scale,view.bounds[3]-(point[1]-view.pad)/view.scale];
}
export function sourceBox(view,box) {
  const [x0,, ,y1]=view.bounds,[a,b,c,d]=box;
  return [view.pad+(a-x0)*view.scale,view.pad+(y1-d)*view.scale,(c-a)*view.scale,(d-b)*view.scale];
}
export function questionView(view,box) {
  if(!box)return [0,0,view.width,view.height];
  const [x,y,w,h]=sourceBox(view,box),pad=Math.max(90,view.scale*1.4,Math.max(w,h)*.35);
  const left=Math.max(0,x-pad),top=Math.max(0,y-pad);
  return [left,top,Math.max(1,Math.min(view.width,x+w+pad)-left),Math.max(1,Math.min(view.height,y+h+pad)-top)];
}
