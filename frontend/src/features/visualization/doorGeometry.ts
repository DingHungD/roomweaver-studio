import type {DoorControl,ManualDoor} from './api';
export type DoorPose={id:string;passage_check?:{projected_clear_width:number};opening?:{state:string;angle?:number;source?:string;blockers?:string[]};preview_parts?:{part:string;vertices:number[][]}[]};
export type DoorPlan=ManualDoor & {control:DoorControl;pose?:DoorPose};
export function doorEndpoints(door:DoorPlan):[[number,number],[number,number]]{
 const [a,b]=door.points,w=Math.hypot(b[0]-a[0],b[1]-a[1]),width=door.control.assembly_width;
 if(width==null||width<.5||width>w)return door.points;
 const pad=(w-width)/2,u=[(b[0]-a[0])/w,(b[1]-a[1])/w];
 return [[a[0]+u[0]*pad,a[1]+u[1]*pad],[b[0]-u[0]*pad,b[1]-u[1]*pad]];
}
// Coordinates remain in the same Z-up metres as saved scenes and Blender.
export function doorLines(door:DoorPlan):[number,number][][] {
 if(door.pose?.preview_parts)return [door.points,...door.pose.preview_parts.filter(p=>p.part.startsWith('leaf-')).map(p=>[...p.vertices.slice(0,4),p.vertices[0]].map(v=>[v[0],v[1]] as [number,number]))];
 const [a,b]=doorEndpoints(door),dx=b[0]-a[0],dy=b[1]-a[1],w=Math.hypot(dx,dy),u=[dx/w,dy/w],n=[-u[1],u[0]],c=door.control;
 const out:[number,number][][]=[[a,b]];
 if(!c.kind||c.kind==='frame'||c.kind==='sliding'||!c.side)return out;
 const side=c.side==='positive'?1:-1;
 function leaf(p:[number,number],sign:number,size:number){
  const q:[number,number]=[p[0]+n[0]*side*size,p[1]+n[1]*side*size];out.push([p,q]);
  out.push(Array.from({length:25},(_,i)=>{const t=i*Math.PI/48;return [p[0]+size*(u[0]*sign*Math.cos(t)+n[0]*side*Math.sin(t)),p[1]+size*(u[1]*sign*Math.cos(t)+n[1]*side*Math.sin(t))] as [number,number];}));
 }
 if(c.kind==='folding'){
  if(c.hinge==='auto')return out;
  const sign=c.hinge==='A'?1:-1,frame=Math.min(.04,w/12,door.height/12),span=(w-2*frame)/2,t=80*Math.PI/180;
  const end=c.hinge==='A'?a:b,p:[number,number]=[end[0]+sign*u[0]*frame,end[1]+sign*u[1]*frame];
  function projected(x:number,y:number,second=false):[number,number]{
   if(second){const dx=x-span,dy=y+.0175,angle=-2*t;x=span+dx*Math.cos(angle)-dy*Math.sin(angle);y=-.0175+dx*Math.sin(angle)+dy*Math.cos(angle);}
   const rx=x*Math.cos(t)-y*Math.sin(t),ry=x*Math.sin(t)+y*Math.cos(t);
   return [p[0]+sign*u[0]*rx+side*n[0]*ry,p[1]+sign*u[1]*rx+side*n[1]*ry];
  }
  out.push([projected(.003,0),projected(span-.003,0)],[projected(span+.003,0,true),projected(2*span-.003,0,true)]);return out;
 }
 if(c.kind==='double'){leaf(a,1,w/2);leaf(b,-1,w/2);}
 else if(c.swing!=='auto'){const atA=(c.swing==='positive')===(side===1);leaf(atA?a:b,atA?1:-1,w);}
 return out;
}
