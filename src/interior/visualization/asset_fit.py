"""Choose upright orientation without turning full-size furniture into miniature props."""
DECOR_ASSETS = {'ceiling_light','vase','books','cookware','tableware','soap','plant','rug'}

def choose_fit(target, asset, *, envelope=False):
    import math
    if any(not math.isfinite(v) or v<=0 for v in [*target,*asset]):raise ValueError('素材或占位尺寸無效')
    choices=[]
    for angle,extent in ((0,list(asset)),(90,[asset[1],asset[0],asset[2]])):
        scale=min(t/a for t,a in zip(target,extent))
        result=[a*scale for a in extent]
        ratios=[r/t for r,t in zip(result,target)]
        choices.append((min(ratios),angle,scale,result))
    _,angle,scale,result=max(choices,key=lambda c:c[0])
    # Height encodes usability: do not turn a dining table into a coffee table.
    if (not envelope and result[2]<target[2]*.8) or min(result[i]/target[i] for i in (0,1))<.45:
        raise ValueError('素材適配未通過：等比例縮放後高度不足原占位80%或水平尺度不足45%；保留原件並嘗試其他候選。')
    return angle,scale,result
