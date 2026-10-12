"""Direct links are catalog lookups, never arbitrary downloads or Agent tasks."""
from unittest.mock import patch
import pytest
from interior.workbench.studio.asset_matching import AssetMatching,LinkAsset,SelectAsset,link_asset_id
from interior.workbench.studio import blenderkit_client as catalog
from interior.workbench.storage import Conflict
from test_asset_matching import environment,FakeAgents,raw,FREE,PAID

def test_link_parser_restricts_host_path_and_identity():
    assert link_asset_id(f'https://www.blenderkit.com/asset-gallery-detail/{FREE}/?utm_source=test')==FREE
    for url in ['https://localhost/a.blend',f'https://blenderkit.com.evil.test/asset-gallery-detail/{FREE}/',f'https://user@blenderkit.com/asset-gallery-detail/{FREE}/','https://www.blenderkit.com/search/','http://www.blenderkit.com/asset-gallery-detail/'+FREE]:
        with pytest.raises(ValueError):link_asset_id(url)

def test_direct_link_deduplicates_without_agent_and_requires_explicit_download(tmp_path):
    studio,jobs,rev=environment(tmp_path);agents=FakeAgents();service=AssetMatching(studio,agents)
    body=LinkAsset(base_revision=rev['revision'],group_id=rev['scene']['groups'][0]['id'],operation_id='direct-link-test',url=f'https://www.blenderkit.com/asset-gallery-detail/{FREE}/')
    try:
        with patch.object(catalog,'detail',return_value=catalog.normalize(raw())) as lookup:
            result=service.from_link('ASSETS',body);again=service.from_link('ASSETS',body)
        assert again['id']==result['id'] and lookup.call_count==1 and agents.calls==0
        assert not result['replacement'] and result['target']['source']=='link'
        selection=SelectAsset(base_revision=rev['revision'],asset_id=FREE,operation_id='download-link-test')
        with pytest.raises(ValueError,match='授權'):service.replace('ASSETS',result['id'],selection)
        job=service.replace('ASSETS',result['id'],selection.model_copy(update={'accept_license':True}))
        assert job['operation']=='studio.replace'
        with pytest.raises(Conflict):service.from_link('ASSETS',body.model_copy(update={'url':f'https://www.blenderkit.com/asset-gallery-detail/{PAID}/'}))
    finally:jobs.close()

def test_link_wrong_kind_and_stale_revision_do_not_create_candidate(tmp_path):
    studio,jobs,rev=environment(tmp_path);service=AssetMatching(studio,FakeAgents())
    body=LinkAsset(base_revision=rev['revision'],group_id=rev['scene']['groups'][0]['id'],operation_id='reject-link-test',url=f'https://www.blenderkit.com/asset-gallery-detail/{FREE}/')
    try:
        with patch.object(catalog,'detail',return_value=dict(catalog.normalize(raw()),kind='material')):
            with pytest.raises(ValueError,match='不是家具'):service.from_link('ASSETS',body)
        with patch.object(catalog,'detail',return_value=catalog.normalize(raw())):
            with pytest.raises(Conflict):service.from_link('ASSETS',body.model_copy(update={'base_revision':'f'*32}))
        assert service.current('ASSETS',body.group_id) is None
    finally:jobs.close()
