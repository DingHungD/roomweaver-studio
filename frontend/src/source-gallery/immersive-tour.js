import * as THREE from 'three';
import {escapeHTML} from './gallery-text.js';
import './tour.css';

const arrow = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 14 6-6 6 6M6 20l6-6 6 6"/></svg>';

export function createImmersiveTour(root, { standalone, onMove }) {
  root.classList.add('immersive-tour');
  const shell = document.createElement('div'); shell.className = 'tour-shell';
  while (root.firstChild) shell.appendChild(root.firstChild);
  root.appendChild(shell);
  const media = root.querySelector('.gallery-media');
  const panel = document.createElement('aside'); panel.className = 'tour-panel'; panel.id = 'tour-panel'; panel.hidden = true;
  panel.setAttribute('aria-label', '場景與光線');
  const heading = root.querySelector('.beauty-heading');
  const exit = heading.querySelector('#beauty-close');
  heading.querySelector('h2').textContent = '場景與光線';
  heading.querySelector('p').textContent = '選擇位置，走進另一個空間。';
  for (const selector of ['.beauty-heading','.gallery-toolbar','.gallery-location-bar','.gallery-bottom','.gallery-note']) panel.appendChild(root.querySelector(selector));
  panel.insertAdjacentHTML('afterbegin', '<button class="tour-panel-close" data-tour-action="panel-close" aria-label="關閉場景選單">✕</button>');
  shell.appendChild(panel);
  const hud = document.createElement('header'); hud.className = 'tour-hud';
  hud.innerHTML = '<div class="tour-identity"><span class="tour-mark">◇</span><div><span class="tour-kicker">ROOMWEAVER / SPATIAL TOUR</span><strong class="tour-location">空間漫遊</strong></div></div><div class="tour-quick-controls"><button class="tour-menu-button" data-tour-action="panel" aria-expanded="false" aria-controls="tour-panel"><span aria-hidden="true">▦</span> 場景</button></div>';
  const quick = hud.querySelector('.tour-quick-controls');
  quick.prepend(root.querySelector('.gallery-light-control'));
  if (exit) { exit.className = 'tour-exit'; exit.setAttribute('aria-label','離開環景，返回 3D'); quick.appendChild(exit); }
  shell.appendChild(hud);
  const scrim = document.createElement('button'); scrim.className = 'tour-panel-scrim'; scrim.hidden = true;
  scrim.dataset.tourAction = 'panel-close'; scrim.setAttribute('aria-label','關閉場景選單');shell.appendChild(scrim);
  const hotspotLayer = document.createElement('div');hotspotLayer.className = 'tour-hotspots';hotspotLayer.setAttribute('aria-label','畫面內移動點');media.appendChild(hotspotLayer);
  const nearby = document.createElement('nav');nearby.className = 'tour-nearby';nearby.setAttribute('aria-label','附近可前往的場景');shell.appendChild(nearby);
  const hint = document.createElement('p');hint.className = 'tour-hint';hint.textContent = '拖曳環顧 · 點擊地面標記或下方按鈕移動';shell.appendChild(hint);
  const credit = document.createElement('span');credit.className = 'tour-credit';credit.textContent = 'ROOMWEAVER / 360°';shell.appendChild(credit);
  let navigation = { nodes: {} }, markers = [], lastCameraId, lastMode, entries = [];
  const forward = new THREE.Vector3(), projected = new THREE.Vector3();

  function setPanel(value) {
    panel.hidden = !value;scrim.hidden = !value;
    hud.querySelector('[data-tour-action="panel"]').setAttribute('aria-expanded',String(value));
    root.classList.toggle('tour-panel-open',value);
    if (value) panel.querySelector('.tour-panel-close').focus();
  }
  root.addEventListener('click', event => {
    const button = event.target.closest('button');if (!button) return;
    if (button.dataset.tourNode) { setPanel(false);onMove(button.dataset.tourNode); }
    else if (button.dataset.tourAction === 'panel') setPanel(panel.hidden);
    else if (button.dataset.tourAction === 'panel-close') setPanel(false);
  });
  root.addEventListener('keydown',event => {
    if(event.key==='Escape'&&!panel.hidden){event.preventDefault();event.stopPropagation();setPanel(false);hud.querySelector('[data-tour-action="panel"]').focus();}
  });
  root.addEventListener('pointerdown',event => { if(event.target.tagName==='CANVAS')root.classList.add('tour-interacted'); });
  root.addEventListener('wheel',event => { if(event.target.tagName==='CANVAS')root.classList.add('tour-interacted'); },{passive:true});

  function refresh(entry) {
    const node = navigation.nodes[entry.cameraId];
    markers = [];hotspotLayer.replaceChildren();
    const links = (node?.links || []).filter(link => entries.some(item => item.cameraId === link.to));
    nearby.innerHTML = '<span class="tour-nearby-label">移動至</span>' + links.map(link => `<button data-tour-node="${link.to}">${arrow}<span>${escapeHTML(link.label)}</span></button>`).join('');
    nearby.hidden = !links.length;
    const origin = new THREE.Vector3().fromArray(entry.position);
    for (const link of links) {
      if (!link.anchor) continue;
      const direction = new THREE.Vector3().fromArray(link.anchor).sub(origin).normalize();
      const button = document.createElement('button');button.className = 'tour-hotspot';button.dataset.tourNode = link.to;
      button.setAttribute('aria-label',`前往${escapeHTML(link.label)}`);button.hidden = true;
      button.innerHTML = `<span class="tour-hotspot-ring">${arrow}</span><span class="tour-hotspot-label">${escapeHTML(link.label)}</span>`;
      hotspotLayer.appendChild(button);markers.push({button,direction});
    }
  }
  return {
    element: shell, setPanel,
    async load() {
      const response = await fetch(new URL('./tour-navigation.json',document.baseURI),{cache:'no-cache'});
      if (!response.ok) throw new Error('Tour navigation unavailable');
      navigation = await response.json();
      if(!Object.values(navigation.nodes).some(node=>node.links?.some(link=>link.anchor)))hint.textContent="拖曳環顧 · 下方按鈕切換觀看點";
    },
    initialYaw(entry) { return navigation.nodes[entry.cameraId]?.initialYaw ?? entry.yaw; },
    update(entry, catalogue, mode) {
      entries = catalogue;root.dataset.mode = mode;
      root.querySelector('.tour-location').textContent = navigation.nodes[entry.cameraId]?.label || entry.label;
      if(lastCameraId!==entry.cameraId||lastMode!==mode){refresh(entry);lastCameraId=entry.cameraId;lastMode=mode;}
      hotspotLayer.hidden = mode!=='360';hint.hidden = mode!=='360';
    },
    project(camera, visible) {
      camera.updateMatrixWorld();camera.getWorldDirection(forward);
      const width=media.clientWidth,height=media.clientHeight;
      for(const marker of markers){
        projected.copy(marker.direction).multiplyScalar(8).project(camera);
        const inView=visible&&marker.direction.dot(forward)>.05&&projected.z<1&&Math.abs(projected.x)<.91&&Math.abs(projected.y)<.83;
        marker.button.hidden=!inView;
        if(inView){marker.button.style.left=`${(projected.x*.5+.5)*width}px`;marker.button.style.top=`${(-projected.y*.5+.5)*height}px`;}
      }
    },
    loading(value){root.classList.toggle('tour-loading',value);if(value)for(const marker of markers)marker.button.hidden=true;},
    roomMarkup(roomIds, catalogue, assetUrl) {
      return roomIds.map((id,index)=>{
        const item=catalogue.find(item=>item.room===id&&item.lightsState==='on')||catalogue.find(item=>item.room===id);
        return `<button data-room="${id}" aria-pressed="false"><img src="${assetUrl(item.thumbnail || `renders/thumbs/${item.cameraId}.jpg`)}" alt="" loading="lazy" decoding="async"/><span><small>${String(index+1).padStart(2,'0')}</small><strong>${escapeHTML(item.label)}</strong></span></button>`;
      }).join('');
    },
    get state(){return {panelOpen:!panel.hidden,links:markers.map(marker=>({to:marker.button.dataset.tourNode,visible:!marker.button.hidden}))};}
  };
}
