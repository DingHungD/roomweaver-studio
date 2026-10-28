"""Recover openings only from this model's verified plan lineage, never another case."""
from ..storage import read_json
from .service import digest


def source_openings(root,model):
    from .plan_import import check_plan
    for identifier in [model['id'],*model.get('ancestor_model_ids',[])]:
        folder=(root/'runs/interior-studio'/identifier).resolve()
        if not folder.is_relative_to((root/'runs/interior-studio').resolve()):raise ValueError('模型來源路徑不符')
        plan_file=folder/'confirmed-plan.json'
        if not plan_file.is_file():continue
        packet=read_json(plan_file);request=read_json(folder/'request.json')
        plan=check_plan(packet['parsed'],packet['settings'])
        openings=[i for i in plan['items'] if i['role'] in ('door','window')]
        expected=[i for i in request.get('plan',{}).get('items',[]) if i['role'] in ('door','window')]
        if plan['status']!='ready' or openings!=expected:raise ValueError('門窗來源與已建模的平面不一致，未改動模型')
        return dict(model_id=identifier,plan_sha256=digest(plan_file),source_sha256=request['source_sha256'],items=openings,plan_items=plan['items'])
    return dict(items=[],reason='原生模型沒有可追溯的門窗洞口資料；不從任意牆面臆造洞口。')
