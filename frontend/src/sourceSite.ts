import {createGallery} from './source-gallery/gallery.js';
import './source-gallery/style.css';
import './source-gallery/adaptations.css';

document.body.classList.add('gallery-page');
const root=document.querySelector<HTMLDivElement>('#tour')!;
root.className='photographic-gallery';
const gallery=createGallery(root,{standalone:true});
// Read-only diagnostics are also used by the browser verification workflow.
Object.assign(window,{__gallery:gallery});
void gallery.open();
void fetch(new URL('./renders/gallery.json',document.baseURI)).then(r=>r.json()).then(manifest=>{
 document.title=(manifest.title||'Roomweaver')+' · 空間展示';
 if(manifest.comparison){const link=document.createElement('a');link.className='gallery-production-comparison';link.textContent='全屋製作前後比較 ↗';link.href=manifest.comparison;root.querySelector('.tour-panel')?.append(link);}
}).catch(()=>{/* The viewer provides its own retry and failure state. */});
