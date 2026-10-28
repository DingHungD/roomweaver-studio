// Display-only palette: never changes source CAD, materials or model revisions.
export const previewPalettes = {
 light: {background:'#fcfcfa',foreground:'#263640'},
 dark: {background:'#151e28',foreground:'#dce6ef'},
};
export const previewThemeKey = 'roomweaver.plan-review.theme';
export function previewTheme(value){return value==='dark'?'dark':'light';}
function channels(color){
 const hex=color.replace(/^#/,'');
 if(!/^(?:[\da-f]{3}|[\da-f]{6})$/i.test(hex))return null;
 return (hex.length===3?[...hex].map(c=>c+c).join(''):hex).match(/../g).map(c=>parseInt(c,16));
}
function luminance(rgb){return rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);}
export function colorContrast(a,b){
 const x=channels(a),y=channels(b);if(!x||!y)return 0;
 const l=luminance(x),r=luminance(y);return (Math.max(l,r)+.05)/(Math.min(l,r)+.05);
}
export function previewColor(color,theme='light'){
 const rgb=channels(color);if(!rgb)return color;
 const palette=previewPalettes[previewTheme(theme)];
 if(Math.max(...rgb)-Math.min(...rgb)<8&&(Math.max(...rgb)<32||Math.min(...rgb)>235))return palette.foreground;
 if(colorContrast(color,palette.background)>=4.6)return color;
 const target=theme==='dark'?255:0;
 const mix=t=>'#'+rgb.map(v=>Math.round(v+(target-v)*t).toString(16).padStart(2,'0')).join('');
 let low=0,high=1;
 for(let i=0;i<20;i++){const mid=(low+high)/2;if(colorContrast(mix(mid),palette.background)>=4.6)high=mid;else low=mid;}
 return mix(high);
}
export function previewStyle(style,theme){
 // Match paint properties only; do not alter opacity, widths, dashes or IDs.
 return style.replace(/\b(fill|stroke)(\s*:\s*)(#[\da-f]{6}|#[\da-f]{3})(?![\da-f])/gi,(_,key,sep,color)=>key+sep+previewColor(color,theme));
}
