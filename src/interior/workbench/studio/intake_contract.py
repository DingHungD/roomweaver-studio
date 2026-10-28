"""UI intake handoff is stricter than geometry-only legacy engineering calls."""

def intake_report(parsed,settings):
    semantic=parsed.get('intake_semantics');review=settings.get('intake_review') or {}
    counts={role:sum(a['role']==role for a in settings['assignments']) for role in ('wall','door','window','furniture')}
    errors=[]
    if parsed.get('cad_preparation') and not settings.get('cad_unit_confirmed'):errors.append('請確認 CAD 圖面實際單位。')
    if not semantic:
        errors.append('尚未完成用途區域、牆門窗及原有家具判讀；幾何可讀不代表已完成設計確認。')
        return dict(status='blocked',errors=errors,rooms=[],counts=counts,furniture_state='uncertain',layout_mode='review_first')
    if not semantic.get('rooms'):errors.append('缺少主臥室、客廳等用途區域。')
    for key,text in [('purposes','用途區域'),('structure','牆面、門窗位置'),('furniture','原圖家具是否存在及其分類')]:
        if not review.get(key):errors.append('請核對並確認'+text+'。')
    if not counts['wall']:errors.append('缺少可建模的牆體。')
    for kind in ('door','window'):
        state=semantic.get(kind+'_state','uncertain')
        if state=='uncertain':errors.append(('門' if kind=='door' else '窗')+'的位置仍不確定，不能略過交接。')
        if state=='present' and not counts[kind]:errors.append(kind+' 已辨認但未轉成可定位開口。')
    state=semantic.get('furniture_state','uncertain')
    if state=='uncertain':errors.append('原圖家具是否存在仍待核對。')
    if state=='present' and not counts['furniture']:errors.append('原圖有家具，但尚未保留其配置。')
    if state=='absent' and (not counts['furniture'] or not settings.get('layout_adoption')):errors.append('原圖未配置家具，請先由 AI 空間配置提出並採用配置。')
    return dict(status='blocked' if errors else 'ready',errors=errors,rooms=semantic.get('rooms',[]),counts=counts,furniture_state=state,
                layout_mode='preserve' if state=='present' else 'generate' if state=='absent' else 'review_first')
