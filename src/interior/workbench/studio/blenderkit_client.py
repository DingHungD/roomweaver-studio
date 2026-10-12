"""Bounded BlenderKit catalog access. Credentials never enter Agent prompts or logs."""
import hashlib
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse, urljoin
from uuid import UUID
import httpx

API = 'https://www.blenderkit.com/api/v1/'
HOSTS = {'www.blenderkit.com', 'www.blendkit.com', 'assets.blenderkit.com',
         'public.blenderkit.com', 'assets.blendkit.com', 'public.blendkit.com'}
MAX_BYTES = 150_000_000

def identifier(value):
    return str(UUID(str(value)))

def trusted_url(value):
    p = urlparse(value)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.port not in (None, 443) or p.username or p.password:
        raise ValueError('BlenderKit 回傳了不支援的下載／圖片來源')
    return value

def request(url, *, params=None):
    """Fetch small JSON, validating redirects before making the next request."""
    for _ in range(4):
        trusted_url(url)
        headers = {'User-Agent': 'Roomweaver-Studio/0.1'}
        if url.startswith(API) and os.environ.get('BLENDERKIT_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['BLENDERKIT_API_KEY']
        try:
            with httpx.stream('GET', url, params=params, headers=headers, timeout=40, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location']); params = None
                    continue
                if response.status_code in (401, 403):
                    raise ValueError('BlenderKit 需要登入或此帳號沒有素材下載權限；請設定 BLENDERKIT_API_KEY 後重試')
                if response.status_code != 200:
                    raise ValueError(f'BlenderKit 暫時無法使用（HTTP {response.status_code}），請稍後重試')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 8_000_000: raise ValueError('BlenderKit 回應過大')
                import json
                return json.loads(data)
        except httpx.HTTPError:
            raise ValueError('BlenderKit 連線逾時或失敗，未切換其他素材來源') from None
    raise ValueError('BlenderKit 重新導向次數過多')

def normalize(raw):
    base = identifier(raw['assetBaseId']); version = identifier(raw['id'])
    kind = raw['assetType']
    if kind not in ('model', 'material'): raise ValueError('素材種類不支援')
    p = raw.get('dictParameters') or {}
    dims = [p.get('dimension'+axis) for axis in 'XYZ']
    if not all(isinstance(v, (float, int)) and math.isfinite(v) and 0 < v < 1000 for v in dims): dims = None
    files = raw.get('files', [])
    # Official texture-resolution variants are native Blender packages too.
    # Prefer 2K to avoid fetching an 8K original just to try a material.
    f = next((f for f in files if f.get('fileType')=='resolution_2K'),None) or next((f for f in files if f.get('fileType')=='blend'),{})
    download = f.get('downloadUrl')
    if download:
        trusted_url(download)
        if not download.startswith(API+'downloads/'): raise ValueError('素材下載入口無效')
    thumbnail = raw.get('thumbnailMiddleUrl') or raw.get('thumbnailSmallUrl') or ''
    if thumbnail: trusted_url(thumbnail)
    return dict(asset_id=base, version_id=version, name=str(raw.get('displayName') or raw.get('name') or base)[:200],
        kind=kind, url=f'https://www.blenderkit.com/asset-gallery-detail/{base}/', thumbnail=thumbnail,
        description=str(raw.get('description') or '')[:1800], dimensions=dims,
        is_free=raw.get('isFree') is True, license=str(raw.get('license') or 'unknown'),
        author=' '.join(str((raw.get('author') or {}).get(k) or '') for k in ('firstName','lastName')).strip()[:200],
        download_url=download, bytes=f.get('fileUploadSize'), download_resolution=f.get('fileType','unknown'),
        can_download=raw.get('canDownload') is True, reason='', warnings=(['來源為程序材質；GLB 預覽無法完整重現 Blender 節點效果'] if p.get('procedural') else []))

def search(query, kind, free=True):
    # Model output can choose keywords, never API filters or URLs.
    words = ' '.join(re.findall(r'[\w-]+', query, flags=re.UNICODE))[:120]
    if not words: return []
    result = request(API+'search/', params={'query':f'{words}+asset_type:{kind}+is_free:{str(free).lower()}',
        'page_size':12, 'dict_parameters':1})
    candidates = []
    for raw in result.get('results', [])[:12]:
        try: item = normalize(raw)
        except (ValueError, KeyError, TypeError): continue
        if item['kind'] == kind and item['is_free'] == free: candidates.append(item)
    return candidates

def detail(asset_id):
    base = identifier(asset_id)
    result = request(API+'search/', params={'query':'asset_base_id:'+base, 'page_size':1, 'dict_parameters':1})
    for raw in result.get('results', []):
        item = normalize(raw)
        if item['asset_id'] == base: return item
    raise ValueError('BlenderKit 素材已移除或目前不可存取')

def download(candidate, destination, scene_id):
    """Recheck version/price/license before requesting a signed download URL."""
    fresh = detail(candidate['asset_id'])
    for key in ('version_id','kind','is_free','license'):
        if fresh[key] != candidate[key]: raise ValueError('素材版本、價格或授權已變更，請重新配對後確認')
    if fresh['license'] not in ('cc_zero','royalty_free'): raise ValueError('素材授權不明，請先確認來源')
    if not fresh['download_url']: raise ValueError('素材尚無可用的 Blender 檔案')
    if not fresh['is_free'] and not os.environ.get('BLENDERKIT_API_KEY'):
        raise ValueError('付費候補需要自己的 BlenderKit 帳號與下載權限，不會自動購買')
    if fresh.get('bytes') and fresh['bytes'] > MAX_BYTES: raise ValueError('素材超過 150 MB 下載上限')
    packet = request(fresh['download_url'], params={'scene_uuid':str(UUID(scene_id))})
    url = trusted_url(packet.get('filePath',''))
    destination = Path(destination); temporary = destination.with_suffix('.partial')
    try:
        for _ in range(4):
            trusted_url(url)
            with httpx.stream('GET', url, timeout=90, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url,response.headers['location']); continue
                if response.status_code != 200: raise ValueError(f'素材檔下載失敗（HTTP {response.status_code}）')
                count = 0; checksum = hashlib.sha256()
                with temporary.open('wb') as stream:
                    for chunk in response.iter_bytes():
                        count += len(chunk)
                        if count > MAX_BYTES: raise ValueError('素材超過 150 MB 下載上限')
                        stream.write(chunk); checksum.update(chunk)
                # Blender compressed files may use zstd or gzip headers.
                with temporary.open('rb') as stream: header=stream.read(12)
                if not header.startswith((b'BLENDER', b'\x1f\x8b', b'\x28\xb5\x2f\xfd')):
                    raise ValueError('下載內容不是 Blender 模型／材質檔')
                temporary.replace(destination)
                return dict(sha256=checksum.hexdigest(), bytes=count, asset_id=fresh['asset_id'], version_id=fresh['version_id'],
                    license=fresh['license'],url=fresh['url'],download_resolution=fresh['download_resolution'])
        raise ValueError('素材重新導向次數過多')
    except httpx.HTTPError:
        raise ValueError('素材下載逾時或失敗，原模型未變更') from None
    finally:
        temporary.unlink(missing_ok=True)
