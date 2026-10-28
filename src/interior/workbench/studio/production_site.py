"""Verify and reuse a completed production delivery; never execute producer code."""
import copy
import hashlib
import math
from pathlib import Path,PurePosixPath
import re
import shutil
import zipfile
from urllib.parse import urlsplit
from PIL import Image
from ..storage import Conflict,now,read_json,write_json
from .service import digest
from .source_site import checked_model
from .site_packaging import copy_viewer,archive_site


def relative_file(root,name):
    """Resolve an untrusted artifact name without accepting URLs or escapes."""
    parsed=urlsplit(str(name));part=PurePosixPath(parsed.path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in str(name) or '..' in part.parts:raise ValueError('交付檔案路徑無效')
    clean=part.as_posix().lstrip('/')
    if not clean or ':' in clean:raise ValueError('交付檔案名稱無效')
    path=(Path(root)/clean).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():raise ValueError('交付檔案不存在或超出範圍：'+clean)
    return path,clean


def producer_path(producer,value):
    path=Path(value)
    path=(path if path.is_absolute() else producer/path).resolve()
    if not path.is_relative_to(producer) or not path.is_file():raise ValueError('製作證據不在指定來源內')
    return path


def production_input(root,binding):
    """Locate the delivery corresponding to the active, completed manifest."""
    root=Path(root).resolve();producer=Path(binding['producer']).resolve();site=Path(binding['site']).resolve()
    if not site.is_relative_to(producer):raise ValueError('展示目錄超出製作來源')
    source=producer_path(producer,binding['source'])
    config=read_json(root/'workflows/interior-studio/source.json')
    original=config.get('original_skp') or dict(path=config['native'])
    own=(root/original['path']).resolve()
    if not own.is_relative_to(root) or own.suffix.lower()!='.skp' or digest(own)!=digest(source):raise Conflict('製作成果的原始 SKP 與本案不一致')
    if original.get('sha256') and digest(own)!=original['sha256']:raise Conflict('原始 SKP 已偏離保存的來源雜湊')
    manifest=site/'renders/gallery.json';sha=digest(manifest)
    directory=Path(binding['deliveries']).resolve()
    if not directory.is_relative_to(producer):raise ValueError('交付目錄超出製作來源')
    deliveries=[]
    for path in directory.glob('*/delivery.json'):
        if not path.resolve().is_relative_to(producer):continue
        packet=read_json(path)
        if packet.get('passed') and packet.get('manifestSha256')==sha:deliveries.append((packet.get('completedAt',''),path))
    if not deliveries:raise Conflict('目前展示清單沒有對應的完成交付，保留上一版本')
    delivery=max(deliveries)[1]
    result=dict(binding,delivery=str(delivery),delivery_sha256=digest(delivery),manifest_sha256=sha,original_skp_sha256=digest(source))
    if binding.get('prompt'):result['prompt_sha256']=digest(producer_path(producer,binding['prompt']))
    return result


def import_production(root,output,parameters):
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.parent!=root/'runs/interior-studio' or not re.fullmatch(r'[a-f0-9]{32}',output.name):raise ValueError('匯入輸出位置無效')
    if output.exists() and any(output.iterdir()):raise Conflict('執行目錄已有內容，請建立新版本')
    upstream=parameters['upstream'];producer=Path(upstream['producer']).resolve();source_site=Path(upstream['site']).resolve()
    frozen=production_input(root,upstream)
    for key in ('delivery_sha256','manifest_sha256','original_skp_sha256',*(['prompt_sha256'] if 'prompt_sha256' in upstream else [])):
        if frozen[key]!=upstream[key]:raise Conflict('排隊後製作交付已變更，請重新同步')
    native,model=checked_model(root,parameters['model_id'],parameters['source_sha256'])
    source_config=root/'workflows/interior-studio/source.json';source_config_sha=digest(source_config)
    configured_native=(root/read_json(source_config)['native']).resolve()
    if not configured_native.is_relative_to(root) or digest(configured_native)!=parameters['source_sha256']:raise Conflict('排隊後本案模型來源已變更')
    native_sha=digest(native)
    delivery_path=producer_path(producer,upstream['delivery']);delivery=read_json(delivery_path)
    release=read_json(source_site/'release.json')
    if release['contentHash']!=delivery['releaseContentHash']:raise Conflict('網站版本與完成交付不一致')
    files=release['fileSha256']
    # Verify all retained publish files, not just the currently selected room.
    for name,sha in files.items():
        path,_=relative_file(source_site,name)
        if not re.fullmatch(r'[a-f0-9]{64}',sha) or digest(path)!=sha:raise Conflict('發布檔案雜湊不符：'+name)
    evidence={}
    for name,record in delivery['reports'].items():
        path=producer_path(producer,record['path'])
        if digest(path)!=record['sha256']:raise Conflict('製作驗收證據已變更：'+name)
        packet=read_json(path)
        if packet.get('passed') is not True:raise Conflict('製作驗收未通過：'+name)
        evidence[name]=dict(path=str(path),sha256=record['sha256'])
    for name in ('nativeMaster','archive'):
        record=delivery[name];path=producer_path(producer,record['path'])
        if digest(path)!=record['sha256']:raise Conflict('製作母檔或交付包已變更')
    with zipfile.ZipFile(producer_path(producer,delivery['archive']['path'])) as archive:
        members=archive.namelist()
        if len(members)!=delivery['archive']['majorImages']+delivery['archive']['thumbnails'] or any('..' in PurePosixPath(n).parts or PurePosixPath(n).is_absolute() for n in members):raise Conflict('交付壓縮包內容不符')
    manifest=read_json(source_site/'renders/gallery.json');scenes=manifest['scenes']
    if not scenes:raise ValueError('交付沒有場景')
    camera_ids={s['cameraId'] for s in scenes};ids={s['id'] for s in scenes}
    if len(ids)!=len(scenes):raise ValueError('場景識別碼重複')
    for scene in scenes:
        for key in ('id','room','cameraId','environment','lightGroupId'):
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',scene[key]):raise ValueError('場景識別欄位無效')
        if scene.get('lightsState') not in ('on','off'):raise ValueError('開關燈狀態無效')
        if len(scene.get('position',[]))!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in scene['position']):raise ValueError('拍攝點位置無效')
        for name,size in (('still',(3200,2200)),('panorama',(4096,2048)),('panoramaHigh',(8192,4096))):
            path,relative=relative_file(source_site,scene[name])
            if relative not in files:raise Conflict('場景圖檔未包含於發布雜湊')
            with Image.open(path) as image:
                if image.size!=size or image.format!='JPEG':raise Conflict('正式圖檔尺寸或格式不符：'+relative)
            if scene.get(name+'Size')!=list(size):raise Conflict('清單宣告的圖檔尺寸不符')
        for name in ('thumbnail','productionSummary'):
            path,relative=relative_file(source_site,scene[name])
            if relative not in files:raise Conflict('場景配套未包含於發布雜湊')
        other=[s for s in scenes if s['cameraId']==scene['cameraId'] and s['environment']==scene['environment'] and s['lightsState']!=scene['lightsState']]
        if len(other)!=1 or other[0].get('exposure')!=scene.get('exposure'):raise Conflict('開關燈配對或曝光不一致')
        if any(other[0].get(key)!=scene.get(key) for key in ('room','lightGroupId','position','yaw','pitch')):raise Conflict('開關燈配對的取景或燈組不一致')
    if delivery['archive']['majorImages']!=len(scenes)*3 or delivery['archive']['thumbnails']!=len(camera_ids):raise Conflict('交付數量不一致')
    navigation=read_json(source_site/'tour-navigation.json')
    if set(navigation['nodes'])!=camera_ids:raise Conflict('導航拍攝點與場景不一致')
    for node in navigation['nodes'].values():
        if any(link['to'] not in camera_ids for link in node.get('links',[])):raise Conflict('導航目的地不存在')
    total=sum((source_site/name).stat().st_size for name in files)
    if shutil.disk_usage(root).free<total*3+1024**3:raise ValueError('同步網站的可用磁碟空間不足')
    output.mkdir(parents=True,exist_ok=True);site=output/'site';site.mkdir()
    from . import site_packaging
    code_inputs={Path(__file__).name:digest(Path(__file__)),Path(site_packaging.__file__).name:digest(Path(site_packaging.__file__))}
    for path in (Path(__file__),Path(site_packaging.__file__)):
        target=output/'provenance/code'/path.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    if upstream.get('prompt'):
        shutil.copyfile(producer_path(producer,upstream['prompt']),output/'provenance/upstream-workflow.txt')
        if digest(output/'provenance/upstream-workflow.txt')!=upstream['prompt_sha256']:raise Conflict('同步期間操作規範變更')
    if delivery.get('reusablePrompt'):
        record=delivery['reusablePrompt'];path=producer_path(producer,record['deliveryCopy'])
        if digest(path)!=record['sha256']:raise Conflict('原製作規範快照已變更')
        shutil.copyfile(path,output/'provenance/completed-production-workflow.txt')
    copied={}
    for name,sha in files.items():
        path,relative=relative_file(source_site,name)
        if relative.startswith('renders/') and path.suffix.lower() in ('.jpg','.png','.json') or relative=='tour-navigation.json':
            target=site/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);copied[relative]=sha
            if digest(target)!=sha:raise Conflict('複製期間來源圖檔變更，保留上一版本')
    # Keep the comparison page and its verified image dependencies. Only rebase
    # root-relative URLs; source images and production receipts remain exact.
    comparison=manifest.get('comparison')
    if comparison:
        path,relative=relative_file(source_site,comparison)
        if relative not in files or path.suffix!='.html':raise Conflict('比較頁缺少發布證據')
        text=path.read_text(encoding='utf-8')
        text=re.sub(r'(["\'])/(renders/|gallery\.html)',r'\1./\2',text)
        (site/relative).write_text(text,encoding='utf-8')
    adapted=copy.deepcopy(manifest);adapted['title']=parameters['title'];adapted['lightControls']=True
    for scene in adapted['scenes']:
        for key in ('still','panorama','panoramaHigh','thumbnail','productionSummary'):
            if scene.get(key):scene[key]=relative_file(source_site,scene[key])[1]
    if comparison:adapted['comparison']=relative_file(source_site,comparison)[1]
    write_json(site/'renders/gallery.json',adapted)
    copy_viewer(site)
    # The local package has its own version and hashes. Upstream measurements
    # remain attributed evidence and are never presented as fresh measurements.
    local_hashes={p.relative_to(site).as_posix():digest(p) for p in site.rglob('*') if p.is_file()}
    local_version=hashlib.sha256(str(sorted(local_hashes.items())).encode()).hexdigest()
    write_json(site/'release.json',dict(version=2,contentHash=local_version,upstreamContentHash=release['contentHash'],
        sceneCount=len(scenes),cameraCount=len(camera_ids),fileSha256=local_hashes))
    archive_site(output)
    if digest(native)!=native_sha or digest(source_config)!=source_config_sha or digest(configured_native)!=parameters['source_sha256']:raise Conflict('本案原模型在同步期間變更')
    if digest(source_site/'renders/gallery.json')!=upstream['manifest_sha256'] or digest(delivery_path)!=upstream['delivery_sha256']:raise Conflict('同步期間交付版本變更，保留上一版本')
    result=dict(kind='verified-production',model_id=parameters['model_id'],source_sha256=parameters['source_sha256'],
        original_skp_sha256=upstream['original_skp_sha256'],quality='production-8k',view_count=len(camera_ids),scene_count=len(scenes),
        major_images=len(scenes)*3,asset_version=delivery['assetFolder'],site='site/index.html',archive='website.zip',
        original_files_unchanged=True,render_copy_modified=True,preserved=False,upstream_release_hash=release['contentHash'],
        upstream_performance=delivery.get('performance'),local_release_hash=local_version,published=False)
    write_json(output/'source-request.json',parameters)
    write_json(output/'upstream-verification.json',dict(passed=True,delivery_path=str(delivery_path),
        delivery_sha256=upstream['delivery_sha256'],manifest_sha256=upstream['manifest_sha256'],
        verified_publish_files=len(files),copied_assets=copied,evidence=evidence,code_inputs=code_inputs,original_files_unchanged=True,
        render_copy_modified=True,scope='Reuse completed production; no render, geometry or shader operation executed'))
    write_json(output/'result.json',result)
    write_json(output/'source-site.json',dict(id=output.name,project_id=read_json(root/'project.json')['id'],operation='studio.source-site',
        status='completed',created_at=now(),output=output.relative_to(root).as_posix(),model_id=parameters['model_id'],
        source_sha256=parameters['source_sha256'],result=result,error=None))
    return result
