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
    doctor.add_argument('--workspace',type=Path,default=Path('workspace'))
    for command in (init,new,serve,example):command.add_argument('--workspace',type=Path,default=Path('workspace'))
    args=parser.parse_args(argv)
    if args.command in ('serve','doctor'):
        from .runtime import configure_blender
        try:configure_blender(args.workspace,getattr(args,'blender',None))
        except ValueError as exc:parser.error(str(exc))
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
        for name,value in checks:print(f'{name}: {value}')
        return int(missing)
    if args.command=='serve':
        if not list((args.workspace/'projects').glob('*/project.json')):
            parser.error('No projects. Run roomweaver init --workspace <same path> first.')
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
