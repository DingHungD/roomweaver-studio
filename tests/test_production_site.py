"""Synthetic production reuse: source identity, complete receipts and paired views."""
from pathlib import Path
from unittest.mock import patch
import zipfile
import pytest
from PIL import Image
from interior.workbench.storage import write_json,read_json,Conflict
from interior.workbench.studio.service import digest
from interior.workbench.studio.production_site import production_input,import_production,relative_file


@pytest.fixture
def production(tmp_path):
    root=tmp_path/'case';producer=tmp_path/'producer';site=producer/'site'
    root.mkdir();producer.mkdir();site.mkdir()
    source=root/'source.skp';source.write_bytes(b'synthetic sketchup source')
    (producer/'source.skp').write_bytes(source.read_bytes())
    model='a'*32;folder=root/'runs/interior-studio'/model;folder.mkdir(parents=True)
    (folder/'model.blend').write_bytes(b'synthetic immutable prepared model')
    write_json(root/'project.json',dict(id='SOURCE',name='Synthetic',kind='synthetic'))
    write_json(root/'workflows/interior-studio/source.json',dict(native='source.skp',preview='source.skp',sha256=digest(source)))
    write_json(folder/'model.json',dict(source_sha256=digest(source),native_sha256=digest(folder/'model.blend')))
    scenes=[]
    for state in ('off','on'):
        item=dict(id='room-'+state,room='room',label='Room',cameraId='camera',cameraLabel='Camera',environment='day',
                  lightGroupId='room',lightsState=state,exposure=0,position=[0,1.5,0],yaw=0,pitch=0,
                  thumbnail='/renders/v1/camera-thumb.jpg',productionSummary='/renders/v1/production-summary.json')
        for key,size,suffix in [('still',[3200,2200],''),('panorama',[4096,2048],'-4k'),('panoramaHigh',[8192,4096],'-8k')]:
            name=f'renders/v1/{state}{suffix}.jpg';path=site/name;path.parent.mkdir(parents=True,exist_ok=True)
            image=Image.new('RGB',tuple(size),(70 if state=='off' else 180,100,90));image.save(path);image.close()
            item[key]='/'+name;item[key+'Size']=size
        scenes.append(item)
    Image.new('RGB',(320,200)).save(site/'renders/v1/camera-thumb.jpg')
    write_json(site/'renders/v1/production-summary.json',dict(majorDeliverables=6,thumbnails=1))
    write_json(site/'renders/gallery.json',dict(version=5,title='Synthetic',defaultScene='room-on',rooms=[dict(id='room',label='Room')],scenes=scenes))
    write_json(site/'tour-navigation.json',dict(version=2,nodes=dict(camera=dict(label='Camera',links=[]))))
    archive=producer/'images.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in site.rglob('*.jpg'):z.write(path,path.name)
    (producer/'master.blend').write_bytes(b'synthetic render copy')
    write_json(producer/'review.json',dict(passed=True))
    manifest_sha=digest(site/'renders/gallery.json')
    release=dict(contentHash='release-v1',fileSha256={p.relative_to(site).as_posix():digest(p) for p in site.rglob('*') if p.is_file()})
    write_json(site/'release.json',release)
    delivery=producer/'deliveries/v1/delivery.json'
    write_json(delivery,dict(passed=True,completedAt='2026-10-28',manifestSha256=manifest_sha,releaseContentHash='release-v1',assetFolder='v1',
              nativeMaster=dict(path=str(producer/'master.blend'),sha256=digest(producer/'master.blend')),
              archive=dict(path=str(archive),sha256=digest(archive),majorImages=6,thumbnails=1),
              reports=dict(review=dict(path=str(producer/'review.json'),sha256=digest(producer/'review.json')))))
    binding=dict(producer=str(producer),source=str(producer/'source.skp'),site=str(site),deliveries=str(producer/'deliveries'))
    frozen=production_input(root,binding)
    parameters=dict(model_id=model,source_sha256=digest(source),title='Synthetic',upstream=frozen)
    return root,producer,site,parameters


def viewer(site):
    (site/'index.html').write_text('<html>verified synthetic viewer</html>',encoding='utf-8')


def test_verified_production_reuse_keeps_originals_and_marks_render_copy(production):
    root,producer,site,parameters=production;output=root/'runs/interior-studio'/('b'*32)
    before=digest(root/'source.skp')
    with patch('interior.workbench.studio.production_site.copy_viewer',side_effect=viewer):result=import_production(root,output,parameters)
    assert result['kind']=='verified-production' and result['render_copy_modified'] and not result['preserved']
    assert result['scene_count']==2 and result['view_count']==1 and not result['published']
    assert digest(root/'source.skp')==before and not (root/'workflows/interior-studio/current.json').exists()
    manifest=read_json(output/'site/renders/gallery.json')
    assert manifest['scenes'][0]['panoramaHigh'].startswith('renders/')
    assert read_json(output/'source-site.json')['status']=='completed'
    with zipfile.ZipFile(output/'website.zip') as archive:assert not any(n.endswith(('.skp','.blend')) for n in archive.namelist())
    with pytest.raises(Conflict):import_production(root,output,parameters)


def test_rejects_changed_source_and_incomplete_delivery(production):
    root,producer,site,parameters=production
    (producer/'source.skp').write_bytes(b'other source')
    with pytest.raises(Conflict):production_input(root,parameters['upstream'])
    (producer/'source.skp').write_bytes((root/'source.skp').read_bytes())
    path=producer/'deliveries/v1/delivery.json';packet=read_json(path);packet['passed']=False;write_json(path,packet)
    with pytest.raises(Conflict):production_input(root,parameters['upstream'])


@pytest.mark.parametrize('file',['renders/v1/off.jpg','tour-navigation.json'])
def test_rejects_asset_changes_before_writing(production,file):
    root,producer,site,parameters=production;output=root/'runs/interior-studio'/('b'*32)
    (site/file).write_bytes(b'tampered')
    with pytest.raises(Conflict):import_production(root,output,parameters)
    assert not output.exists()


def test_rejects_changed_review_receipt(production):
    root,producer,site,parameters=production
    write_json(producer/'review.json',dict(passed=False))
    with pytest.raises(Conflict):import_production(root,root/'runs/interior-studio'/('b'*32),parameters)


@pytest.mark.parametrize('name',['../outside.json','https://example.com/image.jpg','//remote/path','C:/outside.json'])
def test_artifact_paths_reject_external_locations(tmp_path,name):
    with pytest.raises(ValueError):relative_file(tmp_path,name)
