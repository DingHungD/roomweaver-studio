"""Offline SKP to metre/Y-up GLB, retaining component instances and textures.

OpenSKP is optional and pinned: its public instanced scene is already in metres;
its stock Python GLB exporter changes that to millimetres. Write those public
scene buffers directly to glTF instead. No geometry simplification is performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from importlib.metadata import version
import json
import logging
from pathlib import Path
import struct
import sys
import time

SKP_LIMIT = 512_000_000
GLB_LIMIT = 512_000_000
OPEN_SKP_VERSION = '1.3.0'
ADAPTER_VERSION = 3


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def valid_header(header):
    return 'SketchUp Model' in header[:128].decode('utf-16-le', errors='replace')


def normalize_affine_nodes(document):
    """Represent shear with two TRS-compatible nodes, without changing vertices.

    Blender decomposes a single glTF matrix into TRS and loses its shear. SVD
    factors A into U*S*Vt; two parented rotations preserve the full affine map,
    including reflected instances. Both factors have orthogonal columns.
    """
    import numpy as np
    count=0
    for index,node in enumerate(list(document['nodes'])):
        if 'matrix' not in node:continue
        matrix=np.asarray(node['matrix'],dtype=float).reshape(4,4,order='F')
        if not np.isfinite(matrix).all() or not np.allclose(matrix[3],(0,0,0,1),atol=1e-9):
            raise ValueError('模型元件矩陣無效或含非仿射變換')
        linear=matrix[:3,:3];gram=linear.T@linear
        off=gram-np.diag(np.diag(gram))
        if np.max(np.abs(off))<=1e-7*max(1,float(np.max(np.abs(gram)))):continue
        u,s,vt=np.linalg.svd(linear)
        if np.linalg.det(u)<0:u[:,-1]*=-1;s[-1]*=-1
        if np.linalg.det(vt)<0:vt[-1,:]*=-1;s[-1]*=-1
        parent=np.eye(4);parent[:3,:3]=u@np.diag(s);parent[:3,3]=matrix[:3,3]
        child=np.eye(4);child[:3,:3]=vt
        original=dict(node);original['matrix']=child.flatten(order='F').tolist()
        helper=len(document['nodes']);document['nodes'].append(original)
        document['nodes'][index]=dict(name='affine_'+node['name'],matrix=parent.flatten(order='F').tolist(),
                                      children=[helper],extras=dict(skp_affine_factor=True))
        count+=1
    return count


def annotate_source_assemblies(document):
    """Carry each top-level SKP instance to the editor as one source assembly."""
    nodes=document['nodes']
    def visit(index,identifier,label):
        node=nodes[index]
        if 'mesh' in node:
            node.setdefault('extras',{}).update(skp_assembly_id=identifier,skp_assembly_name=label)
        for child in node.get('children',[]):visit(child,identifier,label)
    for scene_root in document['scenes'][document.get('scene',0)]['nodes']:
        root=nodes[scene_root]
        if 'mesh' in root:
            root.setdefault('extras',{}).update(skp_assembly_id=f'skp-{scene_root}-loose',skp_assembly_name='SketchUp 未分組幾何')
        for index in root.get('children',[]):
            node=nodes[index];label=node.get('extras',{}).get('skp_name') or node['name']
            visit(index,f'skp-{index}',label)


def _visible_geometry(skp):
    """Apply explicit source visibility to the pinned parser's working copy.

    OpenSKP 1.3.0's instance scene omits hidden flags; this small adapter uses
    its retained raw parse. It never edits the input file or site settings.
    """
    parsed = skp._parsed
    removed = dict(instances=0, faces=0)
    hidden_layers = parsed.get('layer_hidden', {})
    names = parsed.get('layer_id_to_name', {})
    for definition in parsed['defs_dict'].values():
        builder = definition['builder']
        instances = builder.instances
        builder.instances = [i for i in instances if not i.get('hidden') and
                             not hidden_layers.get(names.get(i.get('layer_id')), False)]
        removed['instances'] += len(instances) - len(builder.instances)
        faces = builder.faces
        builder.faces = {k: f for k, f in faces.items() if not f.get('hidden') and
                         not hidden_layers.get(names.get(f.get('layer_id')), False)}
        removed['faces'] += len(faces) - len(builder.faces)
    return removed


def write_glb(scene, destination):
    """Serialize OpenSKP's metre buffers without baking repeated components."""
    import numpy as np
    document = dict(asset=dict(version='2.0', generator='Roomweaver/OpenSKP 1.3.0'),
                    scene=0, scenes=[dict(nodes=[])], nodes=[], meshes=[],
                    accessors=[], bufferViews=[], buffers=[], materials=copy.deepcopy(scene.gltf_materials))
    binary = bytearray()

    def blob(data, target=None):
        binary.extend(b'\0' * (-len(binary) % 4))
        index = len(document['bufferViews'])
        view = dict(buffer=0, byteOffset=len(binary), byteLength=len(data))
        if target: view['target'] = target
        document['bufferViews'].append(view)
        binary.extend(data)
        return index

    def accessor(data, width, kind, bounds=False):
        dtype = '<f4' if kind == 5126 else '<u4'
        values = np.asarray(data, dtype=dtype).reshape(-1, width)
        if not len(values) or (kind == 5126 and not np.isfinite(values).all()):
            raise ValueError('模型含空白或非有限幾何座標')
        item = dict(bufferView=blob(values.tobytes(), 34963 if width == 1 else 34962),
                    componentType=kind, count=len(values), type={1:'SCALAR',2:'VEC2',3:'VEC3'}[width])
        if bounds: item.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
        index = len(document['accessors'])
        document['accessors'].append(item)
        return index

    for texture in scene.textures:
        if texture.mime_type not in ('image/png', 'image/jpeg'):
            raise ValueError('模型含 GLB 不支援的貼圖；未靜默丟棄材質')
        document.setdefault('images', []).append(dict(bufferView=blob(texture.data), mimeType=texture.mime_type))
        document.setdefault('textures', []).append(dict(source=len(document['images'])-1))
    resources = {}
    triangles = 0
    for resource in scene.mesh_resources:
        primitives = []
        for primitive in resource.primitives:
            count = len(primitive.positions)//3
            if (len(primitive.indices)%3 or not primitive.indices or min(primitive.indices)<0 or
                max(primitive.indices)>=count or len(primitive.normals)!=count*3 or len(primitive.uvs)!=count*2 or
                not 0<=primitive.material_index<len(scene.gltf_materials)):
                raise ValueError('模型三角網格索引無效')
            attributes = dict(POSITION=accessor(primitive.positions,3,5126,True),
                              NORMAL=accessor(primitive.normals,3,5126),
                              TEXCOORD_0=accessor(primitive.uvs,2,5126))
            primitives.append(dict(attributes=attributes, indices=accessor(primitive.indices,1,5125),
                                   material=primitive.material_index, mode=4))
            triangles += len(primitive.indices)//3
        if primitives:
            resources[resource.id] = len(document['meshes'])
            document['meshes'].append(dict(name=resource.definition_name, primitives=primitives))

    def emit(node):
        if scene.layer_hidden.get(node.layer,False): return None
        index = len(document['nodes'])
        # A unique, readable node name is required for GLB -> BLEND ID mapping.
        label=(node.name or node.definition_name or 'Component').encode('utf-8')[:44].decode('utf-8',errors='ignore')
        name = f'skp_{index}_' + label
        item = dict(name=name, matrix=list(node.matrix), extras=dict(skp_name=node.name,
                    skp_definition=node.definition_name, skp_layer=node.layer, skp_guid=node.guid))
        if node.mesh_resource_id in resources: item['mesh'] = resources[node.mesh_resource_id]
        document['nodes'].append(item)
        children = [i for child in node.children if (i := emit(child)) is not None]
        if children: item['children'] = children
        return index

    root = emit(scene.scene_hierarchy)
    if root is None or not document['meshes']: raise ValueError('SKP 沒有可見的實體網格')
    document['scenes'][0]['nodes'] = [root]
    annotate_source_assemblies(document)
    affine_nodes=normalize_affine_nodes(document)
    document['buffers'] = [dict(byteLength=len(binary))]
    encoded = json.dumps(document,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    encoded += b' ' * (-len(encoded)%4)
    binary.extend(b'\0' * (-len(binary)%4))
    length = 12 + 8 + len(encoded) + 8 + len(binary)
    if length > GLB_LIMIT: raise ValueError('轉出的 GLB 超過 512 MB，請在來源軟體拆分模型')
    with Path(destination).open('xb') as stream:
        stream.write(struct.pack('<4sII',b'glTF',2,length))
        stream.write(struct.pack('<I4s',len(encoded),b'JSON')); stream.write(encoded)
        stream.write(struct.pack('<I4s',len(binary),b'BIN\0')); stream.write(binary)
    return dict(nodes=len(document['nodes']), mesh_instances=sum('mesh' in n for n in document['nodes']),
                mesh_resources=len(resources), unique_triangles=triangles, materials=len(scene.gltf_materials),
                textures=len(scene.textures), affine_nodes_factored=affine_nodes, bytes=length,
                bounds_y_up_m=vars(scene.bounds) if scene.bounds else None)


def convert(source, folder):
    """Create a new, immutable conversion run and a content-bound manifest."""
    source, folder = Path(source).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True,exist_ok=False)
    manifest = folder/'conversion.json'
    record = dict(status='running', tool='OpenSKP', tool_version=OPEN_SKP_VERSION,adapter_version=ADAPTER_VERSION,
                  source=dict(name=source.name,sha256=sha256(source),bytes=source.stat().st_size),
                  output_units='m', output_up_axis='Y', instanced=True,
                  limitations=['SketchUp scenes, dimensions, text, construction edges, section cuts, styles and plugin render settings are not transferred.',
                               'Only visible surface meshes are imported; hidden source content remains in the original SKP.',
                               'Mesh conversion does not establish room/wall/door semantics or design approval.'])
    started=time.monotonic()
    def save(): manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    try:
        if source.suffix.lower()!='.skp' or source.stat().st_size > SKP_LIMIT:
            raise ValueError('請選擇不超過 512 MB 的 SKP')
        with source.open('rb') as stream:
            if not valid_header(stream.read(128)): raise ValueError('SKP 檔頭無效，不能只更改副檔名')
        try:
            from openskp import SkpFile
        except ImportError as exc:
            raise ValueError('請先安裝 SKP 免費轉檔依賴：python -m pip install -e ".[sketchup]"') from exc
        if version('openskp')!=OPEN_SKP_VERSION: raise ValueError('OpenSKP 版本不符，請安裝 1.3.0')
        logging.info('Parsing %s', source.name)
        skp=SkpFile.open(str(source)); model=skp.parse()
        record.update(sketchup_version=model.version, excluded_hidden=_visible_geometry(skp))
        logging.info('Building instanced scene: %d definitions',len(model.definitions))
        del model
        # SkpFile.build_instanced_scene() reparses the input, losing our explicit
        # visibility filter and doubling large-file work. Reuse the pinned parse.
        from openskp.instanced_scene import build_instanced_scene
        scene=build_instanced_scene(skp._parsed)
        record['geometry']=write_glb(scene,folder/'model.glb')
        if skp._parsed.get('thumbnail_data'):
            (folder/'source-thumbnail.png').write_bytes(skp._parsed['thumbnail_data'])
        if sha256(source)!=record['source']['sha256']: raise ValueError('SKP 在轉換期間變動，請重新匯入')
        record.update(status='completed',seconds=round(time.monotonic()-started,3),
                      derived=dict(path='model.glb',sha256=sha256(folder/'model.glb')))
        save(); return record
    except Exception as exc:
        record.update(status='failed',error=str(exc),seconds=round(time.monotonic()-started,3))
        save(); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try: convert(args.source,args.output)
    except Exception:
        logging.exception('SKP conversion failed'); sys.exit(1)
