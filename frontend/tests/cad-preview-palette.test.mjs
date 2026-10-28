import test from 'node:test';
import assert from 'node:assert/strict';
import {previewColor,previewStyle,previewPalettes,previewTheme} from '../src/features/visualization/cadPreviewPalette.mjs';
import {colorContrast} from '../src/features/visualization/cadPreviewPalette.mjs';

test('CAD colors and semantic strokes remain readable against both canvas backgrounds',()=>{
 const colors=['#ffff00','#00ffff','#ff00ff','#000000','#ffffff','#808080','#999999','#c0c0c0','#ff0000','#a50029','#39664e','#258bb6','#c37b32','#516d72','#245077'];
 // Different project palettes, including shorthand, not only the current CAD.
 for(let r=0;r<256;r+=51)for(let g=0;g<256;g+=51)for(let b=0;b<256;b+=51)colors.push('#'+[r,g,b].map(x=>x.toString(16).padStart(2,'0')).join(''));
 colors.push('#ff0','#0ff','#fff','#000');
 for(const theme of ['light','dark'])for(const source of colors){
  const mapped=previewColor(source,theme);
  assert.ok(colorContrast(mapped,previewPalettes[theme].background)>=4.5,`${theme}: ${source} => ${mapped}`);
  assert.equal(previewColor(mapped,theme),mapped);
 }
 assert.notEqual(previewColor('#ffff00'),previewColor('#00ffff'));
});
test('palette changes paint only, retaining line weights, opacity and no-paint markers',()=>{
 const style='.cad_C2 {stroke: #ffff00; stroke-width: 0.12; stroke-opacity: .75; fill: none; fill-opacity: 1;} .cad_C3{fill:#00ffff;stroke:none}';
 const next=previewStyle(style,'light');
 assert.ok(next.includes('stroke: '+previewColor('#ffff00')+';'));
 assert.ok(next.includes('fill:'+previewColor('#00ffff')+';'));
 assert.equal(next.replace(/#[\da-f]{6}/g,'COLOR'),style.replace(/#[\da-f]{6}/g,'COLOR'));
 assert.equal(previewColor('none','dark'),'none');
 assert.equal(previewColor('url(#hatch)','dark'),'url(#hatch)');
 assert.equal(previewTheme('unknown'),'light');
 assert.equal(previewTheme(null),'light');
 assert.equal(previewTheme('dark'),'dark');
});
