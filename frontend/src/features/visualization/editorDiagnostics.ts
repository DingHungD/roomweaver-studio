import type {Scene,ManualDoor,DoorControl} from './api';
import type {DoorPose} from './doorGeometry';
import type {IncompleteItem} from './configurationIncomplete';
export type EditorIssue={category:'door'|'viewpoint';target_id:string|null;part?:string|null;shot_id?:string|null;reason:string;status?:string};
function append(items:Map<string,IncompleteItem>,item:IncompleteItem){
 const previous=items.get(item.id);if(previous){if(!previous.reason.split('\n').includes(item.reason))previous.reason+='\n'+item.reason;if(previous.part!==item.part)previous.part=null;if(previous.target&&item.target?.shotId&&!previous.target.shotId)previous.target.shotId=item.target.shotId;}else items.set(item.id,item);
}
export function doorIncomplete(scene:Scene,doors:ManualDoor[],poses:DoorPose[],external:EditorIssue[]=[]):IncompleteItem[]{
 const result=new Map<string,IncompleteItem>();
 function add(door:ManualDoor,reason:string,status='需要處理',part:string|null=null){
  const control=scene.door_controls?.find(c=>c.opening_id===door.id);if(control?.deleted)return;
  const [a,b]=door.points;
  const lo:[number,number,number]=[Math.min(a[0],b[0])-.12,Math.min(a[1],b[1])-.12,0],hi:[number,number,number]=[Math.max(a[0],b[0])+.12,Math.max(a[1],b[1])+.12,door.height];
  append(result,{id:door.id,name:control?.name||door.name,part,task:'',status,reason,available:true,target:{kind:'door',position:[(a[0]+b[0])/2,(a[1]+b[1])/2,door.height/2],bounds:[lo,hi]}});
 }
 for(const door of doors){
  const c:DoorControl=scene.door_controls?.find(c=>c.opening_id===door.id)||{opening_id:door.id,hinge:'auto',swing:'auto'};
  if(c.deleted)continue;
  if(scene.opening_details||scene.manual_doors?.some(d=>d.id===door.id)){
   if(!c.kind)add(door,'尚未設定門種類。');
   else if(['single','double','folding'].includes(c.kind)&&!c.side)add(door,'尚未設定開口方向。');
   if(c.kind==='single'&&c.swing==='auto')add(door,'尚未設定單開門的順逆時針方向。');
   if(c.kind==='folding'&&c.hinge==='auto')add(door,'尚未設定折疊門收折端。');
  }
  const pose=poses.find(p=>p.id===door.id);
  if(['blocked','limited'].includes(pose?.opening?.state||''))add(door,pose?.opening?.source||'開門路徑受阻，請核對方向與周邊物件。');
  if(c.allow_width_adjustment&&pose?.passage_check&&pose.passage_check.projected_clear_width<(c.min_passage??.7))add(door,`通行投影估算 ${(pose.passage_check.projected_clear_width*100).toFixed(1)} cm，未達本門設定目標 ${((c.min_passage??.7)*100).toFixed(1)} cm；需核對，非施工驗收。`);
 }
 for(const issue of external.filter(i=>i.category==='door')){
  const door=doors.find(d=>d.id===issue.target_id);
  if(door)add(door,issue.reason,issue.status,issue.part||null);
  else if(!issue.target_id)append(result,{id:'door-unlocated',name:'門配置工作',status:issue.status||'需要處理',reason:issue.reason+'（尚無可定位的門識別）',part:null,task:'',available:false});
 }
 return [...result.values()];
}
export function viewpointIncomplete(scene:Scene,external:EditorIssue[]=[]):IncompleteItem[]{
 const result=new Map<string,IncompleteItem>();
 function add(id:string,reason:string,status='需要處理',shotId:string|null=null){
  const point=scene.viewpoints.find(p=>p.id===id);if(!point)return;
  const valid=point.eye.length===3&&point.eye.every(Number.isFinite),[x,y,z]=valid?point.eye:[0,0,0];
  append(result,{id,name:point.name,part:null,task:'',status,reason,available:valid,editable:true,target:valid?{kind:'viewpoint',position:[x,y,z],bounds:[[x-.25,y-.25,z-.25],[x+.25,y+.25,z+.25]],shotId}:undefined});
 }
 for(const p of scene.viewpoints){
  if(!scene.rooms.some(r=>r.id===p.room_id))add(p.id,'尚未指定有效的所屬空間。');
  if(p.eye.length!==3||!p.eye.every(Number.isFinite))add(p.id,'觀看點座標無效，請於右側修正；無法推測定位。');
  else if(p.eye[2]<=0)add(p.id,'觀看點眼高需大於 0。');
  // An empty shots list is a valid panorama-only output, not an unfinished task.
  for(const s of p.shots)if(![s.yaw,s.pitch,s.lens].every(Number.isFinite)||s.lens<=0||Math.abs(s.pitch)>90||s.eye&&(!s.eye.every(Number.isFinite)||s.eye.length!==3))add(p.id,`${s.name} 的角度、焦距或取景座標無效。`,'方向待處理',s.id);
 }
 for(const issue of external.filter(i=>i.category==='viewpoint')){
  if(issue.target_id)add(issue.target_id,issue.reason,issue.status,issue.shot_id||null);
  else append(result,{id:'viewpoint-unlocated',name:'取景檢查工作',part:null,task:'',status:issue.status||'需要處理',reason:issue.reason+'（尚無可定位的觀看點識別）',available:false});
 }
 return [...result.values()];
}
