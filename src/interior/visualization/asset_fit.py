"""Purpose-aware uniform fitting; unknown placeholders are not product dimensions."""
import math

FIT_VERSION = 2
DECOR_ASSETS = {'ceiling_light','vase','books','cookware','tableware','soap','plant','rug'}
# Broad whole-mesh bounds in metres; not ergonomic/design certification.
HEIGHTS = {
    'table': (.25, 1.3), 'desk': (.55, 1.3), 'chair': (.35, 1.8),
    'sofa': (.4, 1.8), 'bed': (.15, 2.5), 'bunk_bed': (1.2, 2.9),
    'cabinet': (.25, 3.2), 'bookcase': (.25, 3.2), 'wardrobe': (.9, 3.2),
    'shoe_cabinet': (.25, 2.7), 'nightstand': (.2, 1.2), 'dresser': (.45, 2.5),
    'television': (.15, 2.5), 'sink': (.05, 1.5), 'vanity': (.25, 2.7),
    'dishwasher': (.4, 1.1), 'washer': (.5, 1.3), 'fridge': (.45, 2.7),
    'cooker': (.02, 1.3), 'toilet': (.3, 1.5), 'shower': (.1, 3.2),
}


def choose_fit(target, asset, *, envelope=False, policy=None, allow_rotate=True):
    """Keep confirmed sizes exact and envelopes bounded; soft references fit footprint."""
    if len(target)!=3 or len(asset)!=3 or any(not math.isfinite(v) or v<=0 for v in [*target,*asset]):
        raise ValueError('素材或占位尺寸無效')
    policy=policy or {}; mode=policy.get('dimension_source','unknown');purpose=policy.get('purpose')
    dimensions=policy.get('dimensions')
    if mode in ('confirmed','envelope') and (not dimensions or not policy.get('evidence')):
        raise ValueError('尺寸來源不完整，保留原件')
    if dimensions and (len(dimensions)!=3 or any(not math.isfinite(v) or v<=0 for v in dimensions)):
        raise ValueError('尺寸來源包含無效尺寸')
    target=list(dimensions if mode=='confirmed' else
                [min(a,b) for a,b in zip(target,dimensions)] if mode=='envelope' else
                dimensions or target)
    soft=mode in ('unknown','estimated') and purpose in HEIGHTS and not envelope
    choices=[]; failures=[]
    orientations=[(0,list(asset))]+([(90,[asset[1],asset[0],asset[2]])] if allow_rotate else [])
    for angle,extent in orientations:
        # Preserve native size when it fits. Soft height never forces shrinking/upscaling.
        scale=min(1.,target[0]/extent[0],target[1]/extent[1]) if soft else min(t/a for t,a in zip(target,extent))
        result=[a*scale for a in extent];ratios=[r/t for r,t in zip(result,target)]
        if mode=='confirmed':
            if any(abs(r-t)>max(.002,t*.02) for r,t in zip(result,target)):
                failures.append('素材不符合已確認三軸尺寸（容差 2%）；改試候選');continue
        elif purpose in HEIGHTS:
            lower,upper=HEIGHTS[purpose]
            if not lower<=result[2]<=upper:
                failures.append(f'用途尺寸檢查：{purpose} 整體高度 {result[2]*100:.1f} cm，超出暫用合理範圍 {lower*100:g}–{upper*100:g} cm；改試候選');continue
            if max(result[:2])<.2 or (purpose!='television' and min(result[:2])<.08):
                failures.append('用途尺寸檢查：家具本體過小，請核對素材單位或改試候選');continue
        elif not (envelope or mode in ('envelope','estimated')) and ratios[2]<.8:
            failures.append('素材適配未通過：用途未明，無法判定占位高度是否可放寬；請先指定用途');continue
        if not soft and mode not in ('confirmed','envelope') and min(ratios[:2])<.45:
            failures.append('素材適配未通過：水平比例過小，請改試候選');continue
        choices.append((scale if soft else min(ratios),angle,scale,result))
    if not choices:raise ValueError('；'.join(dict.fromkeys(failures)))
    _,angle,scale,result=max(choices,key=lambda c:c[0])
    return angle,scale,result


def fit_report(target, result, policy):
    mode=policy.get('dimension_source','unknown');purpose=policy.get('purpose')
    reference=list(policy.get('dimensions') or target)
    soft=mode in ('unknown','estimated') and purpose in HEIGHTS
    return dict(version=FIT_VERSION,purpose=purpose,dimension_source=mode,
                strategy='footprint_reference' if soft else mode,
                reference_dimensions=reference,resulting_dimensions=list(result),
                height_reference_only=soft,requires_preview=mode!='confirmed',
                note='占位尺寸為參考，保留模型比例；高度依家具類型檢查，請預覽安裝位置。' if soft else
                     '已確認尺寸保持不變。' if mode=='confirmed' else '可用範圍不超出，無須填滿。' if mode=='envelope' else '用途或安裝位置仍需核對。')
