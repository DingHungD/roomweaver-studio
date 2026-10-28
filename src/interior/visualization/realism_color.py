"""Bounded color-balance proposals from native evidence, never automatic repainting."""


def color_balance_options(objects, lights):
    walls=[]
    for obj in objects:
        if not obj.get('editable') or not any(s in obj['name'].lower() for s in ('wall-', 'wall_', '牆')):continue
        materials=obj.get('materials',[])
        # Mixed surfaces and unknown texture colors need visual judgment, not a guess.
        if len(materials)!=1:continue
        material=materials[0];base=material.get('base_color_linear')
        if not material.get('editable') or not base or material.get('textures') or min(base)<.1:continue
        if not base[0]>=base[1]>=base[2] or base[0]/base[2]<1.2:continue
        blue=min(.72,base[2]*1.2)
        gain=[round(max(.65,min(1.2,target/value)),4) for target,value in zip((blue*1.08,blue*1.04,blue),base)]
        current=(obj.get('finish') or {}).get('albedo_gain',[1,1,1])
        walls.append(dict(object_id=obj['id'],name=obj['name'],source_linear=base,
            current_linear=[round(a*b,4) for a,b in zip(base,current)],suggested_albedo_gain=gain,
            proposed_linear=[round(a*b,4) for a,b in zip(base,gain)],
            scope='僅此可編輯牆面；保留粗糙度、凹凸、原始材質與其他精修設定'))
    lamps=[dict(light_id=l['id'],current_color=l['color'],suggested_color=[1,.98,.96],scope=l['scope'])
        for l in lights if l.get('editable') and l.get('kind')=='AREA' and l['color'][0]>l['color'][2]*1.08]
    return dict(walls=walls,lights=lamps,
        note='有界試作選項，非白平衡測量或已套用修改。須由 Agent 對照試圖選取；不改木材、布料、受保護或貼圖未知的材質。')
