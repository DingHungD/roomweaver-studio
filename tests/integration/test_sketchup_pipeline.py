"""Opt-in real SKP -> GLB -> Blender -> checked Roomweaver scene."""
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
pytest.importorskip('openskp')
from interior.workbench.jobs import Jobs
from interior.workbench.storage import Store,read_json
from interior.workbench.studio.service import Studio,digest
from interior.workbench.studio.engine import execute
from interior.workbench.studio.handoff import read_glb,validate_package
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_sketchup_import import synthetic


@pytest.mark.parametrize('size,translation,shear',[(100,(0,0,0),False),(20,(100,-50,12),False),(40,(35,20,5),True)])
def test_real_skp_to_checked_editable_scene(tmp_path,size,translation,shear):
    source=synthetic(tmp_path/'source.skp',size,translation,shear)
    original=digest(source)
    store=Store(tmp_path/'workspace',tmp_path/'workspace/state')
    store.create_project(dict(id='SKP',name='Synthetic SKP'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs)
        job=studio.upload_glb('SKP',source.name,source.read_bytes(),'synthetic-skp')
        packet=read_json(store.state_dir/'jobs'/job['id']/'request.json')
        result=execute(packet['project'],packet['operation'],packet['parameters'])
        assert result['handoff']['status']=='passed' and result['source_preserved']
        folder=studio.root('SKP')/job['output']
        assert (folder/'model.blend').is_file()
        assert validate_package(folder)['spatial_check']['checked_meshes']==2
        doc=read_glb(folder/'model.glb')
        assert len(doc['images'])==1 and len([n for n in doc['nodes'] if 'mesh' in n])==2
        job.update(status='completed',result=result);jobs.write(job)
        adopted=studio.adopt_import('SKP',job['id'])
        assert len(adopted['scene']['objects'])==2
        assert len(adopted['scene']['groups'])==2
        assert all(g['method']=='skp_source_instance' for g in adopted['scene']['groups'])
        assert digest(source)==original
        assert read_json(folder/'sketchup/conversion.json')['source']['sha256']==original
    finally:jobs.close()
