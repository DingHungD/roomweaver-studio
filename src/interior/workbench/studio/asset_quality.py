"""Conservative, case-independent asset purpose and dimension policies.

Catalog text is evidence, never authority to change a design requirement.
Unknown purposes stay reviewable instead of being silently accepted.
"""
import re

PURPOSES = {
    'door': r'\bdoor\b|門片|木門',
    'dishwasher': r'dishwash\w*|洗碗', 'washer': r'washing machine|\bwasher\b|洗衣',
    'cooker': r'\bhob\b|cooktop|\bcooker\b|\bstove\b|爐具|瓦斯爐|電磁爐',
    'fridge': r'refrigerator|\bfridge\b|冰箱', 'sink': r'\bsink\b|水槽',
    'toilet': r'\bwc\b|\btoilet\b|馬桶', 'vanity': r'\bvanity\b|洗手台|浴櫃',
    'shower': r'\bshower\b|淋浴', 'television': r'\btv\b|television|電視',
    'bunk_bed': r'bunk|上下舖|雙層床', 'nightstand': r'nightstand|bedside|床頭櫃',
    'wardrobe': r'wardrobe|closet|衣櫃', 'bookcase': r'bookcase|bookshelf|書櫃|書架',
    'shoe_cabinet': r'shoe.*(cabinet|rack|storage)|shoe.entry|鞋櫃',
    'dresser': r'dresser|dressing table|梳妝', 'desk': r'\bdesk\b|書桌|工作桌',
    'sofa': r'\bsofa\b|\bcouch\b|沙發', 'chair': r'\bchair\b|\bstool\b|椅|凳',
    'bed': r'\bbed\b|床', 'cabinet': r'\bcabinet\b|cupboard|櫃',
    'table': r'\btable\b|桌', 'light': r'\blight\b|\blamp\b|燈',
    'vase': r'\bvases?\b|花瓶', 'books': r'\bbooks?\b|書籍',
    'cookware': r'cookware|saucepan|frying pan|鍋', 'tableware': r'tableware|dinnerware|\bplates?\b|\bbowls?\b|餐具',
    'soap': r'\bsoap\b|洗手乳', 'plant': r'\bplant\b|盆栽|植栽', 'rug': r'\brug\b|\bcarpet\b|地毯',
}
VERSION = 3
DRESSING_PATTERN=r'dressing table|make[ -]?up|vanity table|vanity desk|梳妝'

def classify(text):
    text=re.sub(r'[_-]', ' ', text or '')
    if re.search(r'\b(?:tv|television) (?:stand|cabinet|console|table)\b',text,re.I):return 'cabinet'
    if re.search(r'\b(?:desk|office|dining) chair\b',text,re.I):return 'chair'
    if re.search(DRESSING_PATTERN,text,re.I):return 'dresser'
    if re.search(r'chest of drawers',text,re.I):return 'cabinet'
    if re.search(r'\bvanity\b',text,re.I):return 'vanity'
    return next((k for k,p in PURPOSES.items() if re.search(p,text,re.I)), None)

def requirements(context):
    group=context.get('group') or {}; concept=context.get('concept') or {}
    explicit=group.get('asset_requirements') or {}
    # Never infer target purpose from an already substituted mesh's name.
    purpose=explicit.get('purpose') or (group.get('object_specification') or {}).get('purpose') or (group.get('decor_context') or {}).get('purpose') or classify(concept.get('asset','')) or classify(group.get('name','').split(' · ')[0])
    mode=explicit.get('dimension_source','unknown')
    if mode=='unknown' and concept:mode='estimated'
    return dict(purpose=purpose,dimension_source=mode,
        evidence=explicit.get('evidence',''),dimensions=explicit.get('dimensions') or context.get('dimensions_metres'))

def assess(context, candidate, kind):
    req=requirements(context); reasons=[]
    if kind=='model':
        if (context.get('group') or {}).get('method') in ('structural_wall','structural_floor'):
            reasons.append('牆地群組只能更換材質，不可替換為家具')
        found=classify(candidate.get('name',''))
        if not req['purpose']:reasons.append('目標用途未明，請在單物件的配對限制指定用途')
        elif not found:reasons.append('候選名稱無法確認用途，保留連結供人工核對')
        elif found!=req['purpose']:reasons.append(f"用途不符：需要 {req['purpose']}，候選為 {found}")
        if req['purpose']=='dresser' and not re.search(DRESSING_PATTERN,candidate.get('name',''),re.I):
            reasons.append('dresser 名稱可能是抽屜櫃，未明確符合梳妝台用途，不自動採用')
        notes=' '.join([candidate.get('reason',''),*candidate.get('warnings',[])])
        if re.search(r'低相似|用途不符|功能不符|機能不符|收納立面替代|功能不足|低匹配|用途疑|用途.*待確認|wrong purpose',notes,re.I):
            reasons.append('Agent 已標示用途或必要機能疑點，不可自動採用')
        if re.search(r'room scene|furniture set|整套場景',candidate.get('name',''),re.I):
            reasons.append('整套場景不可替換單件家具')
    return dict(version=VERSION,status='blocked' if reasons else 'eligible',reasons=reasons,requirements=req)
