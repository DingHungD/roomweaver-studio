import type {OrthographicCamera,PerspectiveCamera} from 'three';
export type ViewInsets={top:number;right:number;bottom:number;left:number};
export function usableViewport(width:number,height:number,insets:ViewInsets){
 const left=Math.max(0,Math.min(insets.left,width-1)),top=Math.max(0,Math.min(insets.top,height-1));
 const right=Math.max(left+1,width-Math.max(0,insets.right));
 const bottom=Math.max(top+1,height-Math.max(0,insets.bottom));
 return {width:right-left,height:bottom-top,x:(left+right)/2,y:(top+bottom)/2};
}
/** Move the projection center, never the user's camera pose, zoom or orbit target. */
export function frameViewport(camera:OrthographicCamera|PerspectiveCamera,width:number,height:number,insets:ViewInsets){
 const safe=usableViewport(width,height,insets);
 camera.setViewOffset(width,height,width/2-safe.x,height/2-safe.y,width,height);
 return safe;
}

/** Fit the actual Blender sensor frame inside the unobscured preview area. */
export function frameShotViewport(camera:PerspectiveCamera,width:number,height:number,insets:ViewInsets,shot:{lens:number;aspect?:'4:3'|'16:9';shift_y?:number}){
 const safe=usableViewport(width,height,insets),aspect=shot.aspect==='16:9'?16/9:4/3;
 const frameHeight=Math.min(safe.height,safe.width/aspect),frameWidth=frameHeight*aspect;
 const left=safe.x-frameWidth/2,top=safe.y-frameHeight/2;
 camera.filmGauge=36;camera.aspect=aspect;camera.setFocalLength(shot.lens);
 camera.setViewOffset(frameWidth,frameHeight,-left,-top-(shot.shift_y||0)*frameWidth,width,height);
 return {left,top,width:frameWidth,height:frameHeight};
}
