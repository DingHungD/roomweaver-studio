import * as THREE from 'three';
import {escapeHTML} from './gallery-text.js';
import { createImmersiveTour } from './immersive-tour.js';
import { GalleryResources, highResolutionPolicy, panoramaTextureBytes } from './gallery-resources.js';

// Display-referred Cycles photographs: no second tone mapping, light rig or model load.
export function createGallery(root, { standalone = false, onActive = () => {} } = {}) {
  root.innerHTML = `
    <header class="beauty-heading"><div><span class="eyebrow">ROOMWEAVER / PHOTOGRAPHIC COLLECTION</span><h2>寫實空間展覽</h2><p>同一空間，不同視角與光影。</p></div>
      ${standalone ? '<a hidden href="./" class="gallery-return">自由探索 3D ↗</a>' : '<button id="beauty-close" class="icon-button" aria-label="關閉效果圖">✕</button>'}
    </header>
    <div class="gallery-toolbar">
      <nav class="gallery-rooms" aria-label="選擇房間"></nav>
      <div class="gallery-modes" role="group" aria-label="觀看方式"><button data-mode="still">效果圖</button><button data-mode="360" class="active">360° 環景</button></div>
    </div>
    <div class="gallery-location-bar"><div class="gallery-cameras" role="group" aria-label="拍攝位置"></div><div class="gallery-light-control"><span>室內燈</span><button class="gallery-light-toggle" data-light-toggle role="switch" aria-checked="false" aria-label="室內燈" disabled><span aria-hidden="true"></span></button><strong class="gallery-light-state">關</strong></div></div>
    <div class="gallery-media" aria-busy="false">
      <canvas class="gallery-still" role="img" hidden></canvas>
      <div class="gallery-panorama"></div>
      <div class="gallery-label"><span class="gallery-index">01 / 03</span><strong class="gallery-title">客廳</strong><span class="gallery-scene-name">自然日光</span></div>
      <div class="gallery-dark-notice" hidden><span>室內燈已關閉</span><button data-turn-lights-on>開燈觀看</button></div>
      <div class="gallery-loading" role="status" hidden><span class="gallery-spinner"></span><span data-loading-text>正在載入寫實環景…</span><button class="gallery-retry" hidden>重新載入</button><button class="gallery-retry" data-show-still hidden>觀看效果圖</button></div>
      <div class="gallery-panorama-tools"><span class="gallery-angle">360°</span><button data-pano-action="in" aria-label="放大環景">＋</button><button data-pano-action="out" aria-label="縮小環景">−</button><button data-pano-action="reset" aria-label="重設環景視角">↺</button><button data-pano-action="fullscreen" aria-label="全螢幕環景">⛶</button></div>
    </div>
    <footer class="gallery-bottom"><div class="gallery-moods" role="group" aria-label="光影場景"></div><span class="gallery-hint">拖曳環顧 360° · 滾輪或雙指縮放</span><div class="gallery-quality"><span data-quality-status role="status">4K</span><button data-quality="8k" hidden>升級 8K</button><button data-quality="4k" hidden>使用 4K</button></div><a class="gallery-download" download>下載環景 ↗</a></footer>
    <p class="gallery-note">360° 為固定拍攝點，上下左右皆可環顧；切換房間可前往另一個拍攝點。</p>`;
  const $ = selector => root.querySelector(selector);
  const media = $('.gallery-media'), image = $('.gallery-still'), pano = $('.gallery-panorama');
  const url = new URL(location.href);
  let active = false, manifest, entries = [], room = 'living', entry, mode = url.searchParams.get('mode') === 'still' ? 'still' : '360';
  let renderer, camera, scene, sphere, texture, textureUrl = '', resizeObserver;
  let yaw = 0, pitch = 0, fov = 72, frame = 0, renderedFrames = 0, generation = 0, loading = false;
  let ready = false, lastPinch = 0, zoomTouched = false;
  const resources = new GalleryResources();
  let baseTexture, highTexture, highPending = false, highTimer, restoreTimer, contextLost = false;
  let upgradeFailed = false, prefer4K = false, lastInteraction = -Infinity, lastFrameAt = 0;
  let performanceWindow = [], performanceWindowAt = 0, slowWindows = 0;
  let upgradeMetrics = null, highAttempt = 0;
  const points = new Map(), rememberedRooms = new Map(), rememberedLights = new Map();
  const tour = createImmersiveTour(root, { standalone, onMove: moveTo });
  const roomEntries = () => entries.filter(item => item.room === room);
  const assetUrl = path => { const value = new URL(path, location.href); value.searchParams.set('v', manifest?.version || 1); return value.href; };
  function selectEntry(next, reset = true, explicitLightChange = false) {
    if (!next) return;
    const groupKey = `${next.lightGroupId || next.room}|${next.environment}`;
    const groupState = rememberedLights.get(groupKey);
    if (!explicitLightChange && groupState) next = entries.find(item => item.cameraId === next.cameraId && item.environment === next.environment && item.lightsState === groupState) || next;
    if (!next || (next === entry && ready)) return;
    entry = next; room = entry.room; rememberedRooms.set(room, entry.id);rememberedLights.set(groupKey,entry.lightsState);showEntry(reset);
  }
  function moveTo(cameraId) {
    const candidates = entries.filter(item => item.cameraId === cameraId);
    if (!candidates.length || cameraId === entry?.cameraId) return;
    const saved = rememberedRooms.get(candidates[0].room);
    const savedEntry = entries.find(item => item.id === saved);
    const preferred = manifest.rooms?.find(item => item.id === candidates[0].room)?.defaultScene;
    const next = candidates.find(item => item.id === saved)
      || (savedEntry ? candidates.find(item => item.environment === savedEntry.environment && item.lightsState === savedEntry.lightsState) : null)
      || (candidates[0].room === room ? candidates.find(item => item.environment === entry.environment && item.lightsState === entry.lightsState) : null)
      || candidates.find(item => item.id === preferred)
      || candidates.find(item => item.environment === 'day' && item.lightsState === 'on') || candidates[0];
    // Each arrival uses an authored view, keeping small spaces clear of nearby walls.
    mode = '360';selectEntry(next);
  }

  function schedule() {
    if (active && mode === '360' && ready && !document.hidden && !frame) frame = requestAnimationFrame(draw);
  }
  function draw() {
    frame = 0;
    if (!active || mode !== '360' || !ready || document.hidden) return;
    const horizontal = Math.cos(THREE.MathUtils.degToRad(pitch));
    const azimuth = THREE.MathUtils.degToRad(yaw);
    camera.lookAt(horizontal * Math.cos(azimuth), Math.sin(THREE.MathUtils.degToRad(pitch)), horizontal * Math.sin(azimuth));
    camera.fov = fov; camera.updateProjectionMatrix();
    renderer.render(scene, camera); renderedFrames++;
    trackInteractivePerformance(performance.now());
    tour.project(camera, ready && mode === '360');
  }
  function policy() {
    return highResolutionPolicy({ standalone, width: innerWidth, fine: matchMedia('(pointer:fine)').matches,
      maxTextureSize: renderer?.capabilities.maxTextureSize || 0, memory: navigator.deviceMemory,
      failed: upgradeFailed, source: entry?.panoramaHigh, dimensions: entry?.panoramaHighSize });
  }
  const baseLabel=()=>`${Math.round((entry?.panoramaSize?.[0] || manifest?.panoramaSize?.[0] || 4096)/1024)}K`;
  function qualityControls(message) {
    const rule = policy();
    $('[data-quality-status]').textContent = message || (highTexture ? '8K' : highPending ? '4K · 8K 載入中' : `${baseLabel()} · ${entry?.panoramaHigh ? rule.reason : "目前解析度"}`);
    $('[data-quality="8k"]').hidden = mode !== '360' || !rule.manual || !!highTexture || highPending;
    $('[data-quality="4k"]').hidden = mode !== '360' || (!highTexture && !highPending);
    $('.gallery-quality').hidden = mode !== '360';
  }
  function resetPerformance() { lastFrameAt = 0; performanceWindow = []; performanceWindowAt = 0; slowWindows = 0; }
  function interact() { lastInteraction = performance.now(); schedule(); }
  function trackInteractivePerformance(now) {
    if (!highTexture || document.hidden || now - lastInteraction > 150 || !lastFrameAt || now - lastFrameAt > 250) {
      resetPerformance(); lastFrameAt = now; return;
    }
    if (!performanceWindowAt) performanceWindowAt = now;
    performanceWindow.push(now - lastFrameAt); lastFrameAt = now;
    if (now - performanceWindowAt < 2000) return;
    const fps = performanceWindow.length * 1000 / performanceWindow.reduce((a,b) => a+b,0);
    slowWindows = fps < 45 ? slowWindows + 1 : 0;
    performanceWindow = []; performanceWindowAt = now;
    if (slowWindows >= 2) { upgradeFailed = true; downgrade(); qualityControls('4K · 互動效能較低，已回到 4K'); }
  }
  function downgrade() {
    clearTimeout(highTimer); highPending = false; highAttempt++;
    if (highTexture) { resources.release(highTexture); highTexture = null; }
    if (baseTexture && sphere) { sphere.material.map = baseTexture; sphere.material.needsUpdate = true; texture = baseTexture; }
    resetPerformance(); qualityControls(); schedule();
  }
  async function idle(signal, check) {
    while (points.size || document.hidden || performance.now() - lastInteraction < 300) {
      check();
      await new Promise(resolve => {
        const done = () => { clearTimeout(timer); signal.removeEventListener('abort',done); resolve(); };
        const timer = setTimeout(done,50); signal.addEventListener('abort',done,{once:true});
      });
    }
    check();
  }
  function nextFrame(signal) {
    return new Promise(resolve => {
      let frameId, timer;
      const done = time => { cancelAnimationFrame(frameId); clearTimeout(timer); signal.removeEventListener('abort',done); resolve(typeof time === 'number' ? time : performance.now()); };
      frameId = requestAnimationFrame(done); timer = setTimeout(done,100);
      signal.addEventListener('abort',done,{once:true}); if (signal.aborted) done();
    });
  }
  function upload(bitmap, check) {
    check();
    const next = new THREE.Texture(bitmap);
    next.flipY = false; next.colorSpace = THREE.SRGBColorSpace; next.generateMipmaps = true;
    next.minFilter = THREE.LinearMipmapLinearFilter; next.magFilter = THREE.LinearFilter;
    next.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    next.userData.dimensions = [bitmap.width,bitmap.height]; next.needsUpdate = true;
    try {
      resources.retain(next,panoramaTextureBytes(bitmap.width, bitmap.height));
      const gl = renderer.getContext();
      renderer.initTexture(next);
      if (gl.isContextLost() || gl.getError() !== gl.NO_ERROR) throw new Error('GPU upload failed');
      check(); const old = sphere.material.map;
      sphere.material.map = next; sphere.material.needsUpdate = true;
      try { ready = true; draw(); } catch (error) { sphere.material.map = old; sphere.material.needsUpdate = true; throw error; }
      // Context restore explicitly reacquires 4K; no closed ImageBitmap remains as a source.
      next.image = { width: bitmap.width, height: bitmap.height };
      return next;
    } catch (error) { resources.release(next); throw error; }
  }
  async function upgrade(manual = false) {
    const rule = policy();
    if (!active || !ready || mode !== '360' || highTexture || highPending || prefer4K || !(manual ? rule.manual : rule.automatic)) return;
    if (resources.highJob) {
      clearTimeout(highTimer); highTimer = setTimeout(() => upgrade(manual),50); return;
    }
    const token = generation, selected = entry, started = performance.now(), attempt = ++highAttempt;
    const current = () => active && ready && mode === '360' && token === generation && entry === selected && !contextLost && !prefer4K;
    highPending = true; qualityControls();
    try {
      await resources.decode(assetUrl(selected.panoramaHigh), { high: true, dimensions: selected.panoramaHighSize, current,
        consume: async (bitmap,job,signal,check) => {
          await idle(signal,check);
          const previousFrame = await nextFrame(signal);
          await idle(signal,check); job.stage = 'upload'; const before = performance.now();
          highTexture = upload(bitmap,check); texture = highTexture; job.stage = 'first-draw';
          upgradeMetrics = { scene: selected.id, firstDrawMs: performance.now()-started, uploadAndDrawMs: performance.now()-before };
          const followingFrame = await nextFrame(signal); check();
          upgradeMetrics.longestUpgradeFrameMs = Math.max(followingFrame - previousFrame,upgradeMetrics.uploadAndDrawMs);
          highPending = false; qualityControls();
        } });
    } catch (error) {
      if (token === generation && active && error.name !== 'AbortError') { upgradeFailed = true; downgrade(); qualityControls('4K · 8K 載入失敗，可手動重試'); }
    } finally { if (token === generation && attempt === highAttempt) { highPending = false; qualityControls(); } }
  }
  function resize() {
    if (!renderer || !active) return;
    const width = Math.max(1, media.clientWidth), height = Math.max(1, media.clientHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.setSize(width, height);
    camera.aspect = width / height;
    if (!zoomTouched) fov = defaultFov();
    camera.updateProjectionMatrix(); schedule();
  }
  function defaultFov() {
    // About 90 degrees horizontally on desktop; a generous portrait view on phones.
    const aspect = Math.max(.2, media.clientWidth / Math.max(1, media.clientHeight));
    return THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(2 * Math.atan(1 / aspect)), 42, 90);
  }
  function initPanorama() {
    if (renderer) return;
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'low-power' });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping;
    scene = new THREE.Scene(); camera = new THREE.PerspectiveCamera(fov, 1, .1, 50);
    // Blender camera faces +X. Image-right is Blender -Y / Three +Z.
    const geometry = new THREE.SphereGeometry(10, 64, 32); geometry.scale(1, 1, -1);
    sphere = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ toneMapped: false })); scene.add(sphere);
    const canvas = renderer.domElement; pano.appendChild(canvas);
    canvas.tabIndex = 0; canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', '寫實 360 度環景。拖曳或方向鍵環顧，滾輪、雙指或加減鍵縮放。');
    canvas.addEventListener('pointerdown', event => {
      interact();
      points.set(event.pointerId, { x: event.clientX, y: event.clientY });
      canvas.setPointerCapture(event.pointerId); lastPinch = pinchDistance(); canvas.classList.add('dragging');
    });
    canvas.addEventListener('pointermove', event => {
      const previous = points.get(event.pointerId); if (!previous) return;
      interact();
      points.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (points.size > 1) {
        zoomTouched = true;
        const distance = pinchDistance();
        if (lastPinch > 0 && distance > 0) fov = THREE.MathUtils.clamp(fov * lastPinch / distance, 35, 100);
        lastPinch = distance;
      } else {
        yaw -= (event.clientX - previous.x) * fov / media.clientHeight;
        pitch = THREE.MathUtils.clamp(pitch + (event.clientY - previous.y) * fov / media.clientHeight, -89, 89);
      }
      schedule();
    });
    function release(event) { interact(); points.delete(event.pointerId); lastPinch = pinchDistance(); if (!points.size) canvas.classList.remove('dragging'); }
    canvas.addEventListener('pointerup', release); canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('lostpointercapture', release);
    canvas.addEventListener('wheel', event => { event.preventDefault(); interact(); zoomTouched = true; fov = THREE.MathUtils.clamp(fov + event.deltaY * .04, 35, 100); schedule(); }, { passive: false });
    canvas.addEventListener('keydown', event => {
      interact();
      const keys = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, 8], ArrowDown: [0, -8] };
      if (keys[event.key]) { event.preventDefault(); yaw += keys[event.key][0]; pitch = THREE.MathUtils.clamp(pitch + keys[event.key][1], -89, 89); }
      else if (event.key === '+' || event.key === '=') { zoomTouched = true; fov = Math.max(35, fov - 6); }
      else if (event.key === '-') { zoomTouched = true; fov = Math.min(100, fov + 6); }
      else return;
      schedule();
    });
    canvas.addEventListener('webglcontextlost', event => {
      if (canvas !== renderer?.domElement) return;
      event.preventDefault(); contextLost = true; ready = false; generation++; resources.clear();
      baseTexture = highTexture = texture = null; textureUrl = ''; highPending = false; clearTimeout(highTimer);
      showError('畫面正在恢復…'); clearTimeout(restoreTimer);
      restoreTimer = setTimeout(() => { if (contextLost && active && mode === '360') { showError('環景尚未恢復，可觀看效果圖，或手動重試。'); $('[data-show-still]').hidden = false; } },5000);
    });
    canvas.addEventListener('webglcontextrestored', () => { if (canvas !== renderer?.domElement) return; contextLost = false; clearTimeout(restoreTimer); if (active && mode === '360') showEntry(false); });
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(media);
  }
  function pinchDistance() {
    const pair = [...points.values()]; return pair.length > 1 ? Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y) : 0;
  }
  function setLoading(value) {
    loading = value; media.setAttribute('aria-busy', String(value)); $('.gallery-loading').hidden = !value;
    tour.loading(value);
    $('.gallery-retry').hidden = true; $('.gallery-spinner').hidden = false;
    $('[data-show-still]').hidden = true;
    $('[data-loading-text]').textContent = mode === '360' ? '正在載入寫實環景…' : '正在載入效果圖…';
  }
  function showError(message) {
    loading = false; media.setAttribute('aria-busy', 'false'); $('.gallery-loading').hidden = false;
    $('.gallery-spinner').hidden = true; $('.gallery-retry').hidden = false; $('[data-loading-text]').textContent = message;
  }
  function updateControls() {
    const rooms = [...new Set([...(manifest.rooms || []).map(item => item.id), ...entries.map(item => item.room)])];
    $('.gallery-rooms').innerHTML = tour.roomMarkup(rooms,entries,assetUrl);
    root.querySelectorAll('[data-room]').forEach(button => { const selected=button.dataset.room===room;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected)); });
    const cameras = [...new Map(roomEntries().map(item => [item.cameraId, item])).values()];
    $('.gallery-cameras').hidden = cameras.length < 2;
    $('.gallery-cameras').innerHTML = cameras.map(item => `<button data-camera="${item.cameraId}" class="${item.cameraId === entry.cameraId ? 'active' : ''}" aria-pressed="${item.cameraId === entry.cameraId}">${escapeHTML(item.cameraLabel)}</button>`).join('');
    const environments = [...new Map(roomEntries().filter(item => item.cameraId === entry.cameraId).map(item => [item.environment, item])).values()];
    $('.gallery-moods').innerHTML = environments.map(item => `<button data-environment="${item.environment}" class="${item.environment === entry.environment ? 'active' : ''}" aria-pressed="${item.environment === entry.environment}">${escapeHTML(item.mood)}</button>`).join('');
    const lightsOn = entry.lightsState === 'on';
    const publicLights = entry.lightGroupId === 'public-area';
    $('.gallery-light-control > span').textContent = publicLights ? '客餐廚燈' : '室內燈';
    $('[data-light-toggle]').setAttribute('aria-label',publicLights ? '客餐廚照明' : '室內燈');
    const counterpart = roomEntries().find(item => item.cameraId === entry.cameraId && item.environment === entry.environment && item.lightsState !== entry.lightsState);
    $('[data-light-toggle]').setAttribute('aria-checked', String(lightsOn));
    $('[data-light-toggle]').disabled = !counterpart;
    $('[data-light-toggle]').title = counterpart ? `${lightsOn ? '關閉' : '開啟'}${publicLights ? '客廳與餐廚照明' : '室內燈'}` : '此場景尚無另一組燈光狀態';
    $('.gallery-light-state').textContent = lightsOn ? '開' : '關';
    $('.gallery-dark-notice').hidden = room !== 'bathroom' || lightsOn;
    root.querySelectorAll('[data-mode]').forEach(button => { button.classList.toggle('active', button.dataset.mode === mode); button.setAttribute('aria-pressed', String(button.dataset.mode === mode)); });
    $('.gallery-title').textContent = cameras.length > 1 ? `${entry.label}・${entry.cameraLabel}` : entry.label; $('.gallery-scene-name').textContent = `${entry.mood} · 燈${lightsOn ? '開' : '關'}`;
    $('.gallery-index').textContent = `${String(rooms.indexOf(room) + 1).padStart(2,'0')} / ${String(rooms.length).padStart(2,'0')}`;
    $('.gallery-hint').textContent = mode === '360' ? '拖曳環顧 360° · 滾輪或雙指縮放' : `寫實光影 · ${(entry.stillSize || [1600,1100]).join(' × ')}`;
    $('.gallery-note').textContent = room === 'bathroom' && !lightsOn ? '無窗浴廁關燈後接近全黑，可開啟室內燈觀看。' : mode === '360' ? '360° 為固定拍攝點；切燈保留觀看方向，切換房間可前往另一個拍攝點。' : '以 已確認模型版本渲染，保留配置、家具與材質；窗外景色為照明環境示意。';
    $('.gallery-download').href = assetUrl(mode === '360' ? (entry.panoramaHigh || entry.panorama) : entry.still);
    $('.gallery-download').download = `roomweaver-${entry.id}${mode === '360' ? '-360' : ''}.jpg`;
    $('.gallery-download').textContent = mode === '360' ? '下載環景 ↗' : '下載效果圖 ↗';
    $('.gallery-panorama-tools').hidden = mode !== '360'; pano.hidden = mode !== '360'; image.hidden = mode !== 'still';
    tour.update(entry,entries,mode);
    qualityControls();
    if (standalone) { const next = new URL(location.href); next.searchParams.set('scene', entry.id); next.searchParams.set('mode', mode); history.replaceState(null, '', next); }
  }
  async function showEntry(reset = true) {
    if (!entry || !active) return;
    const token = ++generation; resources.cancel(); clearTimeout(highTimer); downgrade();
    ready = false; prefer4K = false; setLoading(true); updateControls();
    const selected = entry;
    const current = () => token === generation && active && entry === selected;
    if (reset) { yaw = tour.initialYaw(entry); pitch = entry.pitch ?? -8; zoomTouched = false; fov = defaultFov(); }
    try {
      if (mode === 'still') {
        resources.release(baseTexture); baseTexture = texture = null; textureUrl = '';
        if (sphere) { sphere.material.map = null; sphere.material.needsUpdate = true; }
        await resources.decode(assetUrl(selected.still), { panorama: false, dimensions: selected.stillSize || [1600,1100], current,
          consume: async bitmap => {
            image.width = bitmap.width; image.height = bitmap.height;
            resources.canvas(bitmap.width * bitmap.height * 4);
            image.getContext('2d',{alpha:false}).drawImage(bitmap,0,0);
            image.setAttribute('aria-label',`${selected.label}・${selected.cameraLabel}・${selected.mood}，室內燈${selected.lightsState === 'on' ? '開' : '關'}，模型寫實效果圖`);
          } });
      } else {
        image.width = image.height = 0; resources.canvas(0);
        initPanorama(); resize();
        if (contextLost) {
          renderer.getContext().getExtension('WEBGL_lose_context')?.restoreContext();
          showError('環景需要恢復，可手動重試或觀看效果圖。'); $('[data-show-still]').hidden = false; return;
        }
        if (textureUrl !== assetUrl(selected.panorama)) {
          const sourceUrl = assetUrl(selected.panorama);
          await resources.decode(sourceUrl, { dimensions: selected.panoramaSize || manifest.panoramaSize || [4096,2048], current,
            consume: async (bitmap,job,signal,check) => {
              const next = upload(bitmap,check); resources.release(baseTexture);
              baseTexture = texture = next; textureUrl = sourceUrl;
            } });
        }
      }
      if (!current()) return;
      ready = true;if(mode==='360')draw();setLoading(false);schedule();
      qualityControls(); if (mode === '360') highTimer = setTimeout(() => upgrade(),300);
    } catch (error) { if (current() && error.name !== 'AbortError') showError('影像暫時無法載入，請重試。'); }
  }
  async function open() {
    active = true; onActive(true);
    if (!standalone && !root.open) root.showModal();
    setLoading(true);
    try {
      if (!manifest) {
        const [response] = await Promise.all([fetch(new URL('./renders/gallery.json',document.baseURI), { cache: 'no-cache' }),tour.load()]);
        if (!response.ok) throw new Error('Gallery manifest unavailable');
        manifest = await response.json(); root.querySelector('.tour-kicker').textContent=manifest.title || 'ROOMWEAVER / SPATIAL TOUR'; root.querySelector('.gallery-light-control').hidden=manifest.lightControls===false; entries = manifest.scenes.map(item => ({ ...item, cameraId: item.cameraId || `${item.room}-main`, cameraLabel: item.cameraLabel || '主要視角', environment: item.environment || (item.mood === '暖光暮色' ? 'evening' : 'day'), lightsState: item.lightsState || (item.mood === '暖光暮色' ? 'on' : 'off') }));
        entry = entries.find(item => item.id === url.searchParams.get('scene')) || entries.find(item => item.id === manifest.defaultScene) || entries[0]; room = entry.room; rememberedRooms.set(room, entry.id);rememberedLights.set(`${entry.lightGroupId || entry.room}|${entry.environment}`,entry.lightsState);
      }
      await showEntry();
    } catch { if (active) showError('影像暫時無法載入，請重試。'); }
  }
  function close() {
    active = false; ready = false; generation++; points.clear();
    cancelAnimationFrame(frame); frame = 0;
    clearTimeout(highTimer); clearTimeout(restoreTimer); resources.clear();
    baseTexture = highTexture = texture = null; textureUrl = ''; highPending = false;
    image.width = image.height = 0; resetPerformance();
    if (sphere) { sphere.material.map = null; sphere.material.needsUpdate = true; }
    tour.setPanel(false);
    if (!standalone && root.open) root.close(); onActive(false);
  }
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (event.target === root && !standalone) {
      const box = root.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
      return;
    }
    if (!button) return;
    if (button.dataset.quality) {
      if (button.dataset.quality === '4k') { prefer4K = true; resources.cancel(); downgrade(); }
      else { prefer4K = false; upgrade(true); }
      return;
    }
    if (button.id === 'beauty-close') { close(); return; }
    if (button.dataset.room) {
      const id = button.dataset.room, saved = rememberedRooms.get(id), preferred = manifest.rooms?.find(item => item.id === id)?.defaultScene;
      selectEntry(entries.find(item => item.id === saved) || entries.find(item => item.id === preferred) || entries.find(item => item.room === id));
      tour.setPanel(false);
    }
    else if (button.dataset.camera) { const candidates = roomEntries().filter(item => item.cameraId === button.dataset.camera); selectEntry(candidates.find(item => item.environment === entry.environment && item.lightsState === entry.lightsState) || candidates[0]);tour.setPanel(false); }
    else if (button.dataset.environment) { const candidates = roomEntries().filter(item => item.cameraId === entry.cameraId && item.environment === button.dataset.environment); selectEntry(candidates.find(item => item.lightsState === entry.lightsState) || candidates[0], false); }
    else if (button.hasAttribute('data-light-toggle')) { selectEntry(roomEntries().find(item => item.cameraId === entry.cameraId && item.environment === entry.environment && item.lightsState !== entry.lightsState), false,true); }
    else if (button.hasAttribute('data-turn-lights-on')) { selectEntry(roomEntries().find(item => item.cameraId === entry.cameraId && item.environment === entry.environment && item.lightsState === 'on'), false,true); }
    else if (button.dataset.mode) { mode = button.dataset.mode; showEntry(false); }
    else if (button.hasAttribute('data-show-still')) { mode = 'still'; showEntry(false); }
    else if (button.classList.contains('gallery-retry')) {
      if (contextLost && renderer) {
        resizeObserver?.disconnect();renderer.domElement.remove();renderer.dispose();
        sphere?.geometry.dispose();sphere?.material.dispose();renderer = camera = scene = sphere = null;
        contextLost = false; clearTimeout(restoreTimer);
      }
      manifest ? showEntry() : open();
    }
    else if (button.dataset.panoAction) {
      interact();
      const action = button.dataset.panoAction;
      if (action === 'reset') { yaw = tour.initialYaw(entry); pitch = entry.pitch ?? -8; zoomTouched = false; fov = defaultFov(); }
      else if (action === 'in') { zoomTouched = true; fov = Math.max(35, fov - 8); }
      else if (action === 'out') { zoomTouched = true; fov = Math.min(100, fov + 8); }
      else if (action === 'fullscreen') {
        (document.fullscreenElement ? document.exitFullscreen() : tour.element.requestFullscreen()).catch(() => {});
      }
      schedule();
    }
  });
  if (!standalone) root.addEventListener('close', () => { if (active) close(); });
  document.addEventListener('visibilitychange', () => { resetPerformance(); if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else schedule(); });
  addEventListener('resize', () => {
    if (!active) return;
    lastInteraction = performance.now();
    if (innerWidth < 1024) { resources.cancel(); downgrade(); }
    else if (ready && mode === '360' && policy().automatic && !prefer4K) { clearTimeout(highTimer); highTimer = setTimeout(() => upgrade(),300); }
    qualityControls();
  });
  addEventListener('pagehide', close);
  const api = {
    open, close,
    get state() { return { active, ready, loading, scene: entry?.id, room, cameraId: entry?.cameraId, environment: entry?.environment, lightsState: entry?.lightsState, mode, yaw, pitch, fov, renderedFrames, textureSize: texture?.userData.dimensions || null, drawCalls: renderer?.info.render.calls, triangles: renderer?.info.render.triangles, tour:tour.state, resources:resources.state, highPending, upgradeFailed, upgradeMetrics, quality:highTexture?'8K':baseLabel(), policy:policy(), contextLost }; },
    async measurePerformance(seconds = 3) {
      if (!ready || mode !== '360') throw new Error('Panorama not ready');
      const previousYaw = yaw, times = []; let previous = 0; const start = performance.now();
      await new Promise(resolve => {
        function step(now) {
          if (!active || now - start >= seconds * 1000) { resolve(); return; }
          if (previous) times.push(now - previous); previous = now; yaw += .3; lastInteraction = performance.now(); draw(); requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
      });
      yaw = previousYaw; schedule();
      const sorted = [...times].sort((a,b) => a-b);
      return { samples: times.length, averageFPS: times.length * 1000 / times.reduce((a,b) => a+b, 0), p95FrameMs: sorted[Math.floor(sorted.length * .95)], drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles };
    }
  };
  return api;
}
