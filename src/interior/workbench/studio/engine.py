"""Isolated Blender dispatch; inputs are revisions, never model-generated code."""
import os
from pathlib import Path
import shutil
import subprocess
from ..storage import read_json, write_json
from .service import digest

def blender_executable():
    executable = os.environ.get('INTERIOR_BLENDER') or shutil.which('blender')
    if not executable or not Path(executable).is_file():
        raise ValueError('找不到 Blender，請設定 INTERIOR_BLENDER')
    return executable

def execute(project, operation, parameters):
    root = Path(project).resolve()
    output = (root/parameters['output']).resolve()
    if not output.is_relative_to(root/'runs/interior-studio'):
        raise ValueError('無效輸出目錄')
    # Environment failures must precede downloads and model processing.
    executable=blender_executable()
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output).free < 6*1024**3:
        raise ValueError('磁碟可用空間少於 6 GB；尚未開始渲染')
    replacing = operation == 'studio.replace'
    if replacing:
        from .blenderkit_client import download
        revision=read_json(root/'workflows/interior-studio/revisions'/f"{parameters['revision']}.json")
        scene=revision['scene'];model_dir=root/'runs/interior-studio'/scene['model_id']
        native=model_dir/'model.blend';model=read_json(model_dir/'model.json')
        actual=digest(native)
        if actual!=model['native_sha256']:raise ValueError('原工作模型已變動')
        if parameters.get('generated'):
            asset=dict(kind='generated',recipe=parameters['generated']);asset_path=native
            write_json(output/'generated-provenance.json',parameters['generated'])
        elif parameters.get('preview_only'):
            asset=dict(kind='preview');asset_path=native
        elif parameters.get('restore_revision'):
            from .asset_matching import object_context
            prior=read_json(root/'workflows/interior-studio/revisions'/f"{parameters['restore_revision']}.json")
            prior_dir=root/'runs/interior-studio'/prior['scene']['model_id']
            asset_path=prior_dir/'model.blend'
            if digest(asset_path)!=read_json(prior_dir/'model.json')['native_sha256']:raise ValueError('待回復原件雜湊不符')
            asset=dict(kind='restore',context=object_context(prior['scene'],parameters['group_id']))
        else:
            asset=parameters['asset'];asset_path=output/'asset.blend'
            provenance=download(asset,asset_path,parameters['job_id'])
            write_json(output/'asset-provenance.json',provenance)
        preview=output/'source.glb';preview_actual=None
        request=dict(mode='prepare',source=str(native),preview=str(preview),source_sha256=actual,
            output=str(output),model_id=parameters['job_id'],asset=dict(asset,path=str(asset_path)),
            design=scene,target_group=parameters['group_id'],target_object=parameters.get('object_id'),target_objects=parameters.get('object_ids'),
            asset_requirements=parameters.get('asset_requirements'),dimension_fit=parameters.get('dimension_fit','uniform'),repair_scale=parameters.get('repair_scale',1),asset_rotation=parameters['rotation'],auto_fit=parameters.get('auto_fit',False),task_id=parameters['task_id'])
        source={}
    elif operation == 'studio.prepare':
        source = parameters['source']
        if source.get('plan'):
            from .plan_import import check_plan
            plan_path=(root/source['plan']).resolve()
            if not plan_path.is_relative_to(root) or digest(plan_path)!=source['plan_sha256']:
                raise ValueError('平面修訂來源已變動')
            packet=read_json(plan_path)
            native=(root/packet['source']['path']).resolve()
            if not native.is_relative_to(root) or digest(native)!=packet['source']['sha256']:
                raise ValueError('原始圖面已變動')
            plan=check_plan(packet['parsed'],packet['settings'])
            if plan['status']!='ready':raise ValueError('平面檢查未通過')
            preview=output/'source.glb'
            write_json(output/'confirmed-plan.json',packet)
        else:
            native = (root/source['native']).resolve()
            preview = (root/source['preview']).resolve()
        if not native.is_relative_to(root) or not preview.is_relative_to(root):
            raise ValueError('來源必須位於本案')
        actual = digest(native)
        preview_actual=digest(preview) if not source.get('plan') else None
        if source.get('sha256') and source['sha256'] != actual:
            raise ValueError('原模型雜湊不符')
        request = dict(mode='prepare', source=str(native), preview=str(preview), source_sha256=actual,
            output=str(output), model_id=parameters['job_id'])
        if source.get('plan'):request['plan']=plan
    else:
        revision = read_json(root/'workflows/interior-studio/revisions'/f"{parameters['revision']}.json")
        scene = revision['scene']
        model_dir = root/'runs/interior-studio'/scene['model_id']
        model = read_json(model_dir/'model.json')
        native = model_dir/'model.blend'
        if digest(native) != model['native_sha256']:
            raise ValueError('工作模型已變動，請重新匯入')
        request = dict(mode='lighting' if operation=='studio.lighting' else 'render', job_id=parameters['job_id'], source=str(native), output=str(output), scene=scene,
            revision=parameters['revision'], quality=parameters['quality'], model_id=scene['model_id'])
    def lighting_source(value):
        if not value:return None
        path=(root/value['path']).resolve()
        if not path.is_relative_to(root) or path.suffix!='.blend' or digest(path)!=value['sha256']:
            raise ValueError('照明來源不在本案或雜湊不符')
        return dict(value,path=str(path))
    if operation=='studio.lighting':
        source_file=root/'workflows/interior-studio/lighting-source.json'
        if source_file.exists():request['lighting_source']=lighting_source(read_json(source_file))
    elif operation=='studio.render':
        setup=scene.get('lighting_setup',{})
        if setup.get('enabled') and setup.get('source_job_id'):
            from .models import LightingSetup
            setup=LightingSetup.model_validate(setup).model_dump(mode='json')
            proposal=read_json(root/'runs/interior-studio'/setup['source_job_id']/'result.json')
            if proposal.get('model_id') not in [scene['model_id'],*model.get('ancestor_model_ids',[])]:raise ValueError('照明提案不屬於目前模型')
            request['lighting_source']=lighting_source(proposal.get('lighting_source'))
    script = Path(__file__).resolve().parents[2]/'visualization/studio_blender.py'
    def run_blender(payload, folder):
        payload['stop_file']=str(output/'stop-requested.json')
        write_json(folder/'request.json',payload)
        with (folder/'blender.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([executable,'--background','--disable-autoexec','--python-exit-code','1',
                '--python',str(script),'--',str(folder/'request.json')],stdout=log,stderr=log,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            from .processes import identity
            write_json(output/'blender-process.json',dict(pid=process.pid,identity=identity(process.pid)))
            try:process.wait(timeout=14000)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=15);raise
        return process.returncode
    write_json(output/'request.json',request)
    if operation=='studio.render' and scene.get('lighting_setup',{}).get('enabled'):
        from .lighting import optimize
        optimize(request,output,run_blender)
        if (output/'stop-requested.json').exists():raise ValueError('已停止後續出圖')
    code=run_blender(request,output)
    if code:
        if (output/'stop-requested.json').exists():raise ValueError('已停止後續照明與出圖；已產生試圖保留')
        for filename in ('render-readiness.json','quality-checks.json'):
            if (output/filename).exists():
                report=read_json(output/filename)
                if report.get('status')=='blocked':
                    messages=report.get('issues') or [c.get('reason','') for c in report.get('checks',[]) if c.get('status')=='blocked']
                    raise ValueError('渲染檢查未通過：'+'；'.join(messages)+' 請完成照明／鏡位修正後，以新工作重試。')
        tail = (output/'blender.log').read_text(encoding='utf-8',errors='replace')[-2200:]
        raise ValueError('Blender 失敗：'+tail)
    if operation == 'studio.prepare' or replacing:
        model = read_json(output/'model.json')
        if replacing:
            original_model=read_json(model_dir/'model.json')
            model['ancestor_model_ids']=[scene['model_id'],*original_model.get('ancestor_model_ids',[])]
            model['replacement']=dict(source_revision=parameters['revision'],group_id=parameters['group_id'],asset_id=asset.get('asset_id'),restore_revision=parameters.get('restore_revision'))
        model['native_sha256'] = digest(output/'model.blend')
        model['preview_sha256'] = digest(output/'model.glb')
        write_json(output/'model.json', model)
        from .handoff import validate_package
        handoff=validate_package(output,persist=True)
        if digest(native) != actual:
            raise ValueError('原件完整性核對失敗')
        if preview_actual and digest(preview)!=preview_actual:
            raise ValueError('預覽來源在交接期間變動，請重新匯入')
        if source.get('plan') and digest(plan_path)!=source['plan_sha256']:
            raise ValueError('平面修訂在交接期間變動')
        return dict(model_id=parameters['job_id'], object_count=len(model['objects']), source_preserved=True,handoff=handoff,
            replacement=replacing)
    result=read_json(output/'result.json')
    if operation=='studio.lighting':
        from .models import LightingSetup
        result['lighting_setup']=LightingSetup.model_validate(result['lighting_setup']).model_dump(mode='json')
        write_json(output/'result.json',result)
    if operation=='studio.render' and (output/'effective-lighting.json').exists():
        result['lighting_setup']=read_json(output/'effective-lighting.json')['lighting_setup']
        write_json(output/'result.json',result)
    return result
