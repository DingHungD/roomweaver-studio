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
