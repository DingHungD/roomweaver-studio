"""Read-only semantic layers; source CAD fragments are not independent objects."""
import re
import math


def furniture_category(item):
    """Use explicit Agent category, then a cautious legacy name/asset fallback."""
    if item.get('category'):return item['category']
    name=item['name'].lower()
    rules=[('toilet',r'馬桶|坐便|便器|\btoilet\b'),('sink',r'洗手盆|洗手台|洗臉|水槽|\bsink\b|\bbasin\b'),
           ('shower',r'淋浴|浴缸|shower|bathtub'),('cabinet',r'櫃|櫥|cabinet|wardrobe|cupboard'),
           ('chair',r'椅|chair|stool'),('table',r'桌|茶几|table|desk'),('television',r'電視|television|\btv\b'),
           ('kitchen',r'廚具|爐具|瓦斯爐|流理|cooker|kitchen|stove'),('bed',r'床|\bbed\b|bunk'),
           ('sofa',r'沙發|sofa|couch'),('appliance',r'冰箱|洗衣機|微波|烤箱|fridge|refrigerator|washer|microwave|oven'),
           ('air_conditioner',r'空調|冷氣|air conditioner'),('plant',r'植栽|盆栽|\bplant\b'),('rug',r'地毯|\brug\b|carpet'),
           ('curtain',r'窗簾|curtain'),('art',r'掛畫|壁畫|artwork'),('mirror',r'鏡子|鏡面|\bmirror\b'),('decor',r'花瓶|裝飾|擺飾|\bvase\b|decor')]
    for key,pattern in rules:
        if re.search(pattern,name):return key
    return {'desk':'table','bunk_bed':'bed','cooker':'kitchen','washer':'appliance'}.get(item.get('asset'),item.get('asset') or 'other')


def category_layer(category):
    if category in ('plant','rug','curtain','art','mirror','decor'):return 'decoration'
    if category in ('toilet','kitchen','sink','shower','appliance','air_conditioner','switch','socket','vent'):return 'equipment'
    return 'other' if category in ('other','column','beam') else 'furniture'


def object_details(item,assumptions,confirmed=None):
    """Keep candidate defaults distinguishable from geometry evidence and confirmation."""
    parameters=[]
    for key,label in [('height','高度'),('base','離地高度'),('thickness','牆厚')]:
        if key not in item or key=='thickness' and item.get('role')!='wall':continue
        derived=key=='thickness' and ((item.get('derivation') or {}).get('method') in ('pair','portal') or item.get('category') in ('column','wall_junction') and (item.get('derivation') or {}).get('method') in ('outline','solid_outline'))
        if key=='thickness' and item.get('category') in ('column','wall_junction'):label='截面最小外包寬度'
        accepted=(confirmed or {}).get(key,{})
        confirmed_value=key in ('height','base') and accepted.get('after')==item[key]
        parameters.append(dict(key=key,label=label,value=item[key],unit='m',status='confirmed' if confirmed_value else 'derived' if derived else 'unconfirmed',description='使用者已確認' if confirmed_value else '由來源幾何推導，仍需核對' if derived else '候選值，尚未確認'))
    name=item['name']
    # Do not broadcast whole-house assumptions as if they applied to every item.
    notes=[s for s in assumptions if len(name)>=2 and name in s]
    return dict(parameters=parameters,notes=notes)


def review_layers(site,proposal):
    """Expose grouped interpretation and explicitly separate light notes from symbols."""
    items=[]
    geometry={g['id']:g for g in site.get('geometry',[])}
    outline=proposal.get('floor_outline')
    floors=[outline] if outline else site.get('floors',[])
    if floors:
        areas=[dict(points=f['points'],holes=f.get('holes',[])) for f in floors]
        items.append(dict(id='floor:all',layer='floors',category='floor_surface',name='全部地坪',role='floor',points=[p for f in floors for p in f['points']],areas=areas,closed=True,source_ids=list(dict.fromkeys(k for f in floors for k in f.get('source_ids',[f['id']] if f.get('id') else []))),evidence=(outline or {}).get('evidence') or '來源地坪供參考；尚未因此確認邊界或尺寸',status='interpreted' if outline else 'reference'))
    for room in proposal['rooms']:
        items.append(dict(id='room:'+room['id'],layer='rooms',category='room',name=room['name'],role='room',points=room['points'],closed=True,evidence=room['evidence'],source_ids=room['source_ids'],status='interpreted'))
    for e in proposal['elements']:
        layer={'wall':'walls','door':'openings','window':'openings','furniture':'furniture'}[e['role']]
        category=furniture_category(e) if layer=='furniture' else e['role']
        if e['role']=='wall' and e.get('category') in ('column','wall_junction'):category=e['category']
        if layer=='furniture':layer=category_layer(category)
        refs=[r['id'] for r in (e.get('source_binding') or {}).get('refs',[])]
        strokes=[dict(points=geometry[k]['points'],closed=geometry[k].get('closed',False)) for k in dict.fromkeys(refs) if k in geometry]
        items.append(dict(id=e['id'],layer=layer,category=category,name=e['name'],role=e['role'],points=e['points'],closed=e['closed'],strokes=strokes if e['role']=='furniture' else [],source_ids=e['source_ids'],evidence=e['evidence'],status='interpreted'))
    texts={t['id']:t for t in site.get('texts',[])}
    known=set(geometry)|set(texts)|{d['id'] for d in site.get('dimensions',[])}
    seen=set();used_notes=set()
    for obj in proposal.get('drawing_objects',[]):
        if obj['id'] in seen:raise ValueError('圖樣 ID 重複')
        seen.add(obj['id'])
        if category_layer(obj['category'])!=obj['layer']:raise ValueError(obj['name']+' 圖樣類別與室內設計分層不一致')
        if not set(obj['source_ids']).issubset(known):raise ValueError(obj['name']+' 引用不存在的圖樣來源')
        binding=obj.get('source_binding')
        if binding:
            from .semantic_feedback import areas_for,shape
            areas=areas_for(shape(site,dict(obj,role='drawing')))
            strokes=[dict(points=a['points'],closed=True) for a in areas]
        else:strokes=[dict(points=geometry[k]['points'],closed=geometry[k].get('closed',False)) for k in obj['source_ids'] if k in geometry and len(geometry[k]['points'])>=2]
        if not strokes:raise ValueError(obj['name']+' 只有文字，缺少原圖圖樣')
        pts=[p for stroke in strokes for p in stroke['points']]
        items.append(dict(id='drawing:'+obj['id'],layer=obj['layer'],category=obj['category'],role='drawing',name=obj['name'],points=pts,strokes=strokes,closed=False,source_ids=obj['source_ids'],evidence=obj['evidence'],status='interpreted'))
    for lamp in proposal.get('lighting') or []:
        if lamp['id'] in seen:raise ValueError('燈具 ID 重複')
        seen.add(lamp['id'])
        refs=lamp['source_ids']
        if not set(refs).issubset(known):raise ValueError(lamp['name']+' 引用不存在的燈具來源')
        strokes=[dict(points=geometry[k]['points'],closed=geometry[k].get('closed',False)) for k in refs if k in geometry and len(geometry[k]['points'])>=2]
        if not strokes:raise ValueError(lamp['name']+' 只有文字，缺少原圖燈具圖樣')
        pts=[p for s in strokes for p in s['points']]
        if not all(math.isfinite(v) for p in pts for v in p):raise ValueError('燈具來源座標無效')
        used_notes.update(k for k in refs if k in texts)
        items.append(dict(id='light:'+lamp['id'],layer='lighting',category='wall_light' if lamp['kind']=='wall' else lamp['kind'],role='lighting',name=lamp['name'],points=pts,closed=False,strokes=strokes,source_ids=refs,evidence=lamp['evidence'],status='interpreted'))
    # Labels are locators for the annotation itself, never claimed as fixture locations.
    for t in texts.values():
        if t['id'] in used_notes or not re.search(r'軌道燈|吊燈|崁燈|嵌燈|壁燈|吸頂燈|落地燈|燈具|\b(?:pendant|downlight|luminaire|track light)\b',t['text'],re.I):continue
        items.append(dict(id='light-note:'+t['id'],layer='lighting',category='annotation',role='lighting',name=t['text'],points=[t['point']],closed=False,source_ids=[t['id']],evidence='原圖文字註記；此點為文字位置，尚未辨識對應燈具圖樣',status='annotation'))
    elements={e['id']:e for e in proposal['elements']}
    for item in items:
        item['details']=object_details(elements.get(item['id'],item),proposal.get('assumptions',[]),(site.get('dimension_confirmation') or {}).get('updates',{}).get(item['id']))
    return dict(items=items,lighting_reviewed=proposal.get('lighting') is not None)
