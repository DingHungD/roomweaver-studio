"""Register a hash-verified example pair without modifying existing projects."""
from pathlib import Path
import shutil
from ..storage import Store, read_json, write_json
from .service import digest


def register_example(workspace: Path, directory: Path, identifier='DAYLIGHT'):
    directory = directory.resolve()
    manifest = read_json(directory/'manifest.json')
    files = {}
    for key, suffix in [('native', '.blend'), ('preview', '.glb')]:
        name = manifest[key]
        path = (directory/name).resolve()
        if not path.is_relative_to(directory) or path.suffix.lower() != suffix:
            raise ValueError('Example source must stay inside its directory')
        if digest(path) != manifest['sha256'][name]:
            raise ValueError('Example checksum mismatch: '+name)
        files[key] = path
    store = Store(workspace, workspace/'artifacts/workbench/local')
    # create_project rejects duplicate IDs before touching their files.
    store.create_project(dict(id=identifier, name=manifest['name'], kind=manifest.get('kind', 'synthetic')))
    root = store.project(identifier).root
    destination = root/'sources/example'
    destination.mkdir(parents=True)
    for path in files.values():
        shutil.copy2(path, destination/path.name)
    viewpoints = []
    for index, point in enumerate(manifest['suggested_viewpoints'], 1):
        viewpoints.append(dict(id='view'+str(index), name=point['name'], room_id='apartment',
            eye=point['eye'], shots=[dict(id='front', name=point['name']+' front',
                yaw=point['yaw'], pitch=point['pitch'], lens=point['lens'])]))
    source = dict(native='sources/example/'+files['native'].name,
        preview='sources/example/'+files['preview'].name, sha256=digest(files['native']),
        rooms=[dict(id='apartment', name='示範公寓')], viewpoints=viewpoints,
        links=[[viewpoints[0]['id'], viewpoints[1]['id']]] if len(viewpoints)>1 else [])
    write_json(root/'workflows/interior-studio/source.json', source)
    write_json(destination/'manifest.json', manifest)
    (root/'README.md').write_text(
        '# '+manifest['name']+'\n\nTeaching example; see the copied manifest for origin and the repository asset manifest for licenses.\n'
        'Original copies: sources/example/. Native HDRI and camera configuration are preserved.\n'
        'Open the configured model in the import page, then edit and confirm before rendering.\n', encoding='utf-8')
    return dict(id=identifier, status='registered', imported=False)
