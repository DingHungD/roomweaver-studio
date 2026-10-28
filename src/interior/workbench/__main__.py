"""Roomweaver local CLI. Runtime data belongs to a separate workspace."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from .storage import Store


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init',help='Create an empty example project without copying any private data')
    new=commands.add_parser('new-project',help='Create an empty project for your own GLB')
    new.add_argument('id');new.add_argument('--name',required=True)
    serve=commands.add_parser('serve',help='Serve the UI on loopback only')
    example=commands.add_parser('example',help='Register a verified native/GLB example pair, retaining HDRI lighting')
    example.add_argument('--directory',type=Path,default=Path('examples/from-3d'))
    example.add_argument('--id',default='EXAMPLE_3D')
    serve.add_argument('--port',type=int,default=8765)
    serve.add_argument('--blender',type=Path,help='Save Blender executable path in this local workspace')
    doctor=commands.add_parser('doctor',help='Check local dependencies without calling a model')
    convert=commands.add_parser('convert-model',help='Convert SKP offline to metre GLB; optionally create an editable BLEND')
    convert.add_argument('source',type=Path)
    convert.add_argument('--output',required=True,type=Path,help='New output directory, never overwrite an earlier run')
    convert.add_argument('--blend',action='store_true')
    convert.add_argument('--blender',type=Path)
    convert.add_argument('--workspace',type=Path,default=Path('workspace'))
    site=commands.add_parser('source-site',help='Render an immutable prepared 3D model into a standalone 360 website')
    site.add_argument('project',type=Path)
    site.add_argument('--model-id',required=True)
    site.add_argument('--views',type=int,choices=range(1,9),default=3)
    site.add_argument('--quality',choices=('preview','final'),default='preview')
    site.add_argument('--lighting',choices=('preview','native','fixtures'),default='preview')
    site.add_argument('--exposure',type=float,default=0,help='Render-only exposure delta in EV, -3 to 3')
    site.add_argument('--output-id',required=True,help='New 32-character lowercase hex run ID')
    site.add_argument('--blender',type=Path,required=True)
    sync=commands.add_parser('sync-source-site',help='Verify and reuse a completed source-bound production website, without rerendering')
    sync.add_argument('project',type=Path)
    sync.add_argument('--producer',type=Path,required=True)
    sync.add_argument('--source',type=Path,required=True)
    sync.add_argument('--site',type=Path,required=True)
    sync.add_argument('--deliveries',type=Path,required=True)
    sync.add_argument('--prompt',type=Path,help='Version and retain the selected producer workflow text without executing it')
    sync.add_argument('--model-id',required=True)
    sync.add_argument('--output-id',required=True)
    doctor.add_argument('--workspace',type=Path,default=Path('workspace'))
    for command in (init,new,serve,example):command.add_argument('--workspace',type=Path,default=Path('workspace'))
    args=parser.parse_args(argv)
    if args.command=='sync-source-site':
        import re
        from .storage import read_json,write_json
        from .studio.service import digest
        from .studio.production_site import production_input,import_production
        root=args.project.resolve()
        binding=dict(producer=str(args.producer.resolve()),source=str(args.source.resolve()),site=str(args.site.resolve()),deliveries=str(args.deliveries.resolve()))
        if args.prompt:binding['prompt']=str(args.prompt.resolve())
        if not re.fullmatch(r'[a-f0-9]{32}',args.output_id):parser.error('output-id must be 32 lowercase hex characters')
        original=read_json(root/'workflows/interior-studio/source.json');native=(root/original['native']).resolve()
        if not native.is_relative_to(root):parser.error('Source outside project')
        params=dict(model_id=args.model_id,source_sha256=digest(native),upstream=production_input(root,binding),title=read_json(root/'project.json')['name'])
        result=import_production(root,root/'runs/interior-studio'/args.output_id,params)
        write_json(root/'workflows/source-website/upstream.json',binding)
        print(result);return 0
    if args.command=='source-site':
        import re
        from .storage import read_json
        from .studio.source_site import execute_source_site
        if not re.fullmatch(r'[a-f0-9]{32}',args.output_id):parser.error('output-id must be 32 lowercase hex characters')
        if not -3<=args.exposure<=3:parser.error('exposure must be between -3 and 3')
        root=args.project.resolve();output=root/'runs/interior-studio'/args.output_id
        if output.exists():parser.error('Output already exists; select a new run ID')
        source=read_json(root/'workflows/interior-studio/source.json')
        from .studio.service import digest
        native=(root/source['native']).resolve()
        if not native.is_relative_to(root):parser.error('Source outside project')
        current=root/'workflows/interior-studio/current.json';scene=None
        if current.exists():scene=read_json(root/'workflows/interior-studio/revisions'/(read_json(current)['revision']+'.json'))['scene']
        matching=scene if scene and scene['model_id']==args.model_id else None
        setup=None
        if args.lighting=='fixtures':
            from .studio.models import LightingSetup
            if not matching or not matching.get('lighting_setup',{}).get('enabled'):parser.error('No source-bound fixture lighting')
            setup=LightingSetup.model_validate(matching['lighting_setup']).model_dump(mode='json')
        parameters=dict(model_id=args.model_id,source_sha256=digest(native),views=args.views,quality=args.quality,
                        lighting=args.lighting,lighting_setup=setup,exposure=args.exposure,title=read_json(root/'project.json')['name'],
                        viewpoints=[dict(name=p['name'],eye=p['eye']) for p in matching.get('viewpoints',[])] if matching else [])
        print(execute_source_site(root,output,parameters,str(args.blender.resolve())))
        print(output/'website.zip');return 0
    if args.command in ('serve','doctor') or (args.command=='convert-model' and args.blend):
        from .runtime import configure_blender
        try:configure_blender(args.workspace,getattr(args,'blender',None))
        except ValueError as exc:parser.error(str(exc))
    if args.command=='convert-model':
        from .studio.skp_conversion import convert_skp
        report=convert_skp(args.source,args.output)
        if args.blend:
            from .studio.engine import blender_executable
            script=Path(__file__).resolve().parents[1]/'visualization/blender_convert_model.py'
            with (args.output/'blender.log').open('xb') as log:
                result=subprocess.run([blender_executable(),'--background','--disable-autoexec','--python-exit-code','1',
                    '--python',str(script),'--',str(args.output.resolve())],stdout=log,stderr=subprocess.STDOUT,timeout=1800,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise ValueError('Blender 匯入失敗，請查看輸出目錄 blender.log；GLB 已保留')
        print(args.output.resolve()); print(report['geometry'])
        return 0
    if args.command=='example':
        from .studio.example import register_example
        print(register_example(args.workspace,args.directory,args.id))
        return 0
    if args.command=='doctor':
        from .studio.engine import blender_executable
        checks=[('Python',sys.version.split()[0])]
        missing=False
        try:checks.append(('Blender',subprocess.check_output([blender_executable(),'--version'],text=True).splitlines()[0]))
        except (ValueError,OSError,subprocess.SubprocessError):checks.append(('Blender','MISSING: set INTERIOR_BLENDER to the executable'));missing=True
        dist=Path(__file__).resolve().parents[1]/'workbench_web/dist/index.html'
        checks.append(('UI','built' if dist.is_file() else 'MISSING: npm ci --prefix frontend; npm run build --prefix frontend'))
        missing=missing or not dist.is_file()
        checks.append(('Codex (optional)','found' if shutil.which('codex') else 'not on PATH; not required for local rendering'))
        from importlib.metadata import version,PackageNotFoundError
        try:checks.append(('OpenSKP (optional)',version('openskp')))
        except PackageNotFoundError:checks.append(('OpenSKP (optional)','not installed; pip install -e ".[sketchup]" for SKP import'))
        for name,value in checks:print(f'{name}: {value}')
        return int(missing)
    if args.command=='serve':
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(args.workspace),host='127.0.0.1',port=args.port)
    else:
        store=Store(args.workspace,args.workspace/'artifacts/workbench/local')
        identifier='DEMO' if args.command=='init' else args.id
        if args.command=='init' and any(p['id']==identifier for p in store.projects()):
            print('DEMO already exists; no files changed.');return 0
        print(store.create_project(dict(id=identifier,name='Demo apartment' if args.command=='init' else args.name,kind='synthetic' if args.command=='init' else 'user')))
    return 0


if __name__=='__main__':raise SystemExit(main())
