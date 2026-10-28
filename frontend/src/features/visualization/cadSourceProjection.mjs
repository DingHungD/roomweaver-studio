// Map the source renderer's SVG coordinates into the saved question frame.
export function cadSourceTransform(matrix,view,origin,factor){
 const [a,b,c,d,e,f]=matrix,det=a*d-b*c;
 if(!Number.isFinite(det)||Math.abs(det)<1e-15)throw new Error('CAD 原圖座標矩陣無效');
 const inv=[d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det];
 const s=factor*view.scale,tx=view.pad-(origin[0]+view.bounds[0])*view.scale,ty=view.pad+(origin[1]+view.bounds[3])*view.scale;
 return [s*inv[0],-s*inv[1],s*inv[2],-s*inv[3],s*inv[4]+tx,-s*inv[5]+ty];
}
