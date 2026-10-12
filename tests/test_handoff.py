"""Adoption rejects stale model bytes and ambiguous object identities."""
import json
import struct
import pytest
from interior.workbench.studio.handoff import validate_package,read_glb
from interior.workbench.studio.service import digest
from interior.workbench.storage import write_json


def packet(tmp_path,nodes):
    raw=json.dumps(dict(nodes=nodes)).encode();raw+=b' '*((-len(raw))%4)
    (tmp_path/'model.glb').write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(raw),len(raw),0x4e4f534a)+raw)
    (tmp_path/'model.blend').write_bytes(b'synthetic bytes, not a Blender test')
    write_json(tmp_path/'model.json',dict(objects=[dict(id='one',name='One',center=[0,0,0])],selectable_ids=['one'],
        native_sha256=digest(tmp_path/'model.blend'),preview_sha256=digest(tmp_path/'model.glb'),
        spatial_check=dict(passed=True),render_readiness=dict(status='blocked',issues=['no light'])))


def test_editable_is_distinct_from_render_ready(tmp_path):
    packet(tmp_path,[dict(mesh=0,extras=dict(studio_id='one'))])
    result=validate_package(tmp_path)
    assert result['status']=='passed' and result['render_readiness']['status']=='blocked'
    (tmp_path/'model.blend').write_bytes(b'changed')
    with pytest.raises(ValueError,match='雜湊'):validate_package(tmp_path)


def test_duplicate_or_missing_mapping_rejected(tmp_path):
    for nodes in ([dict(mesh=0)],[dict(mesh=0,extras=dict(studio_id='one'))]*2):
        packet(tmp_path,nodes)
        with pytest.raises(ValueError,match='唯一對應'):validate_package(tmp_path)


def test_invalid_glb_header_rejected(tmp_path):
    p=tmp_path/'bad.glb';p.write_bytes(b'glTFshort')
    with pytest.raises(ValueError,match='檔頭'):read_glb(p)
