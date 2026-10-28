// Conservative decoded RGBA reservations, including temporary browser conversion buffers.
// GPU reservations include every mip level used to suppress minification shimmer.
const MiB = 1024 * 1024;
export const LIMITS = Object.freeze({ cpu: 320 * MiB, gpu: 224 * MiB, baseCPU: 64 * MiB, highCPU: 256 * MiB });
const aborted = () => new DOMException('Stale image job', 'AbortError');

export function panoramaTextureBytes(width, height) {
  let bytes = 0;
  for (;;) {
    bytes += width * height * 4;
    if (width === 1 && height === 1) return bytes;
    width = Math.max(1, Math.floor(width / 2));
    height = Math.max(1, Math.floor(height / 2));
  }
}

export class GalleryResources {
  constructor() {
    this.cpu = 0; this.gpu = 0; this.jobs = new Set(); this.textures = new Map();
    this.decodeTail = Promise.resolve(); this.decoding = 0; this.highJob = null;
    this.waiters = new Set(); this.serial = 0; this.maxCPU = 0; this.maxGPU = 0;
    this.canvasBytes = 0;
  }
  wake() { for (const resolve of this.waiters) resolve(); this.waiters.clear(); }
  cancel() { for (const job of this.jobs) job.controller.abort(); this.wake(); }
  async wait(signal) {
    if (signal.aborted) throw aborted();
    await new Promise(resolve => {
      const done = () => { this.waiters.delete(done); signal.removeEventListener('abort', done); resolve(); };
      this.waiters.add(done); signal.addEventListener('abort', done, { once: true });
    });
    if (signal.aborted) throw aborted();
  }
  async decode(url, { high = false, panorama = true, dimensions, current, consume }) {
    const job = { id: ++this.serial, high, stage: 'reserve', controller: new AbortController() };
    this.jobs.add(job);
    const signal = job.controller.signal, bytes = high ? LIMITS.highCPU : LIMITS.baseCPU;
    let reserved = false, bitmap;
    const check = () => { if (signal.aborted || !current()) throw aborted(); };
    try {
      while (this.cpu + bytes > LIMITS.cpu || (high && this.highJob)) { check(); await this.wait(signal); }
      check(); this.cpu += bytes; reserved = true; this.maxCPU = Math.max(this.maxCPU, this.cpu);
      if (high) this.highJob = job;
      job.stage = 'download';
      const response = await fetch(url, { signal, cache: 'default' });
      if (!response.ok) throw new Error(`Image download HTTP ${response.status}`);
      const blob = await response.blob(); check(); job.stage = 'decode-wait';
      const previous = this.decodeTail;
      let unlock; this.decodeTail = new Promise(resolve => { unlock = resolve; });
      // An obsolete createImageBitmap cannot be cancelled: it retains both the lock and reservation.
      await previous;
      try {
        check(); job.stage = 'decode'; this.decoding++;
        try {
          bitmap = await createImageBitmap(blob, { imageOrientation: panorama ? 'flipY' : 'none', premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
        } finally { this.decoding--; }
      } finally { unlock(); }
      check();
      if (dimensions && (bitmap.width !== dimensions[0] || bitmap.height !== dimensions[1])) throw new Error('Unexpected image dimensions');
      if (bitmap.width * bitmap.height * 4 > bytes / 2) throw new Error('Image exceeds decode reservation');
      job.stage = high ? 'idle' : 'upload';
      await consume(bitmap, job, signal, check);
    } finally {
      bitmap?.close();
      if (reserved) this.cpu -= bytes;
      if (this.highJob === job) this.highJob = null;
      this.jobs.delete(job); this.wake();
    }
  }
  retain(texture, bytes) {
    if (this.gpu + bytes > LIMITS.gpu) throw new Error('Panorama GPU budget exceeded');
    this.textures.set(texture, bytes); this.gpu += bytes; this.maxGPU = Math.max(this.maxGPU, this.gpu);
  }
  release(texture) {
    if (!texture) return;
    this.gpu -= this.textures.get(texture) || 0; this.textures.delete(texture); texture.dispose();
  }
  canvas(bytes) {
    if (this.cpu - this.canvasBytes + bytes > LIMITS.cpu) throw new Error('Still canvas exceeds CPU budget');
    this.cpu += bytes - this.canvasBytes; this.canvasBytes = bytes; this.maxCPU = Math.max(this.maxCPU,this.cpu); this.wake();
  }
  clear() { this.cancel(); this.canvas(0); for (const texture of this.textures.keys()) this.release(texture); }
  get state() {
    return { cpuMiB: this.cpu / MiB, gpuMiB: this.gpu / MiB, maxCPUMiB: this.maxCPU / MiB, maxGPUMiB: this.maxGPU / MiB,
      stillCanvasMiB: this.canvasBytes / MiB, decoding: this.decoding, highJobs: this.highJob ? 1 : 0, jobs: [...this.jobs].map(({ id, high, stage }) => ({ id, high, stage })) };
  }
}

export function highResolutionPolicy({ standalone, width, fine, maxTextureSize, memory, failed, source, dimensions }) {
  if (!source) return { manual: false, automatic: false, reason: '此場景提供 4K 環景' };
  if (!dimensions || dimensions[0] !== 8192 || dimensions[1] !== 4096 || maxTextureSize < 8192) return { manual: false, automatic: false, reason: '裝置不支援 8K 貼圖' };
  if (width < 1024) return { manual: false, automatic: false, reason: '較小視窗使用 4K' };
  if (failed) return { manual: true, automatic: false, reason: '本頁已停止自動升級，可手動重試 8K' };
  if (!standalone) return { manual: true, automatic: false, reason: '3D 模型保留中，預設使用 4K' };
  if (!fine) return { manual: true, automatic: false, reason: '觸控裝置預設使用 4K' };
  if (typeof memory !== 'number') return { manual: true, automatic: false, reason: '裝置未提供記憶體資訊，可手動選擇 8K' };
  if (memory < 8) return { manual: true, automatic: false, reason: '裝置回報記憶體較低，預設使用 4K' };
  return { manual: true, automatic: true, reason: '4K 已就緒，閒置後升級 8K' };
}
