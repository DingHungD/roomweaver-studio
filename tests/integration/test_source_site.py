"""Real Blender source preservation and automatic floor cameras, using synthetic data."""
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pytest
from interior.workbench.storage import write_json,read_json
from interior.workbench.studio.service import digest
from interior.workbench.studio.source_site import execute_source_site


def test_native_source_auto_cameras_and_portable_site(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    project=tmp_path/'synthetic';project.mkdir();model='a'*32
    write_json(project/'project.json',dict(id='SYNTHETIC',name='Synthetic',kind='synthetic'))
    native=project/'runs/interior-studio'/model/'model.blend';native.parent.mkdir(parents=True)
    script=tmp_path/'make.py'
    script.write_text('''import bpy,sys,math
from pathlib import Path
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
mat=bpy.data.materials.new('Original shared checker');mat.use_nodes=True
tree=mat.node_tree;checker=tree.nodes.new('ShaderNodeTexChecker');checker.inputs['Color1'].default_value=(.2,.6,.35,1)
tree.links.new(checker.outputs['Color'],tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.mesh.primitive_plane_add(size=9);floor=bpy.context.object;floor.data.materials.append(mat)
bpy.ops.mesh.primitive_plane_add(size=9,location=(0,0,3));bpy.context.object.data.materials.append(mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(2,2,.5));cube=bpy.context.object;cube.rotation_euler.z=.35;cube.scale=(1,.7,1);cube.data.materials.append(mat)
linked=cube.copy();linked.data=cube.data;linked.location=(-2,2,.5);bpy.context.collection.objects.link(linked)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index('--')+1])
''',encoding='utf-8')
    result=subprocess.run([blender,'-b','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(native)],capture_output=True,timeout=90)
    assert result.returncode==0,result.stdout[-3000:]
    source=project/'source.glb';source.write_bytes(b'synthetic source binding')
    write_json(project/'workflows/interior-studio/source.json',dict(native='source.glb',preview='source.glb',sha256=digest(source)))
    write_json(native.parent/'model.json',dict(source_sha256=digest(source),native_sha256=digest(native)))
    before=digest(native);output=project/'runs/interior-studio'/('b'*32)
    result=execute_source_site(project,output,dict(model_id=model,source_sha256=digest(source),quality='preview',views=2,lighting='preview',viewpoints=[],title='Synthetic source test'),blender)
    assert result['preserved'] and result['view_count']==2 and digest(native)==before
    report=read_json(output/'preservation.json');assert report['before']==report['after']
    device=read_json(output/'render-device.json')
    assert device['requested_backend'] and any('Path tracing on' in line for line in device['execution_trace'])
    manifest=read_json(output/'site/tour.json');assert len(manifest['views'])==2
    assert all(abs(v['eye'][2]-1.55)<.01 for v in manifest['views'])
    with zipfile.ZipFile(output/'website.zip') as bundle:
        names=bundle.namelist();assert 'index.html' in names and 'tour.json' in names
        assert not any(n.endswith(('.skp','.blend','.glb')) for n in names)
        assert b'"/assets/' not in bundle.read('index.html')
        assert len([n for n in names if n.endswith('.jpg')])==6
        assert 'renders/gallery.json' in names and 'tour-navigation.json' in names
