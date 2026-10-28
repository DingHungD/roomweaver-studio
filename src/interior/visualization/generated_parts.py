"""Bounded semantic assemblies for concept furniture, in a unit envelope, front -Y."""
def parts(purpose, design):
    result=[]
    def box(name,x,y,z,w,d,h,material='wood'):
        result.append(dict(name=name,center=[x,y,z],size=[w,d,h],material=material))
    def legs(top):
        for x in (-.45,.45):
            for y in (-.45,.45):box('leg',x,y,top/2,.07,.07,top,'accent')
    if purpose=='vase':
        # Hollow ceramic vessel, real curved silhouette; flowers are bounded ellipsoids.
        result.append(dict(name='hollow vase',center=[0,0,0],size=[1,1,1],material='enamel',shape='lathe',profile=[(0,0),(.22,0),(.3,.08),(.32,.28),(.19,.48),(.18,.56),(.145,.56),(.155,.48),(.28,.28),(.26,.08),(0,.04)]))
        for i,(x,y,z) in enumerate(((-.2,-.04,.91),(.17,.06,.95),(.02,-.17,.85))):
            box('flower stem',x*.5,y*.5,.65,.022,.022,.58,'accent')
            result[-1]['shape']='sphere'
            for dx,dy in ((-.1,0),(.1,0),(0,-.1),(0,.1)):
                box('flower petal',x+dx,y+dy,z,.22,.22,.1,'fabric');result[-1]['shape']='sphere'
            box('flower center',x,y,z+.01,.1,.1,.08,'wood');result[-1]['shape']='sphere'
    elif purpose=='books':
        for i in range(3):
            z=i/3;w=1-.08*i;d=1-.05*i
            box('paper pages',0,0,z+.16,w-.025,d-.025,.27,'enamel')
            for dz in (.013,.307):box('book cover',0,0,z+dz,w,d,.025,'accent' if i%2==0 else 'wood')
            box('book spine',-w/2+.015,0,z+.16,.03,d,.30,'accent')
    elif purpose=='tableware':
        for i in range(2):
            result.append(dict(name='ceramic plate',center=[0,0,i*.055],size=[1,1,1],material='enamel',shape='lathe',profile=[(0,0),(.3,0),(.5,.07),(.5,.105),(.3,.035),(0,.035)]))
        result.append(dict(name='hollow bowl',center=[0,0,.09],size=[1,1,1],material='enamel',shape='lathe',profile=[(0,0),(.15,0),(.32,.45),(.34,.82),(.30,.82),(.285,.46),(.13,.04),(0,.04)]))
    elif purpose in ('table','desk','dresser'):
        top=.62 if purpose=='dresser' else .96
        box('tabletop',0,0,top+.02,1,1,.04);legs(top)
        if purpose=='dresser':box('mirror',0,.46,.82,.8,.06,.36,'glass')
    elif purpose=='chair':
        legs(.46);box('seat',0,0,.5,1,1,.08,'fabric');box('backrest',0,.45,.77,1,.1,.46,'fabric')
    elif purpose=='sofa':
        box('base',0,0,.16,1,1,.32)
        n=design.get('seats',2)
        for i in range(n):box('seat cushion',-.42+.84*(i+.5)/n,-.04,.43,.82/n,.82,.22,'fabric')
        box('backrest',0,.4,.66,1,.2,.68,'fabric')
        for x in (-.45,.45):box('armrest',x,0,.55,.1,1,.46,'fabric')
    elif purpose in ('bed','bunk_bed'):
        levels=(.14,.65) if purpose=='bunk_bed' else (.14,)
        for z in levels:
            box('bed frame',0,0,z,1,1,.12)
            box('mattress',0,0,z+.12,.94,.95,.12,'fabric')
            box('pillow',0,.32,z+.2,.7,.2,.04,'accent')
        if purpose=='bed':box('headboard',0,.46,.5,1,.08,1,'fabric')
        else:
            for x in (-.47,.47):
                for y in (-.47,.47):box('post',x,y,.5,.06,.06,1)
            # Required upper safety rails and a ladder are never optional Agent choices.
            for y in (-.47,.47):box('upper guard rail',-.1,y,.94,.75,.04,.08)
            for x in (.23,.44):box('ladder side',x,-.46,.4,.035,.04,.8)
            for i in range(6):box('ladder rung',.335,-.46,.08+i*.13,.23,.05,.035)
    elif purpose in ('cabinet','bookcase','wardrobe','shoe_cabinet','nightstand'):
        for x in (-.48,.48):box('side panel',x,0,.5,.04,1,1)
        for z in (.02,.98):box('horizontal panel',0,0,z,.92,1,.04)
        box('back panel',0,.48,.5,.92,.04,.92)
        n=design.get('shelves',3)
        for i in range(n):box('shelf',0,0,.08+.82*(i+1)/(n+1),.92,.92,.025)
        if purpose=='wardrobe':box('hanging rail',0,0,.83,.88,.04,.025,'accent')
        if purpose!='bookcase':
            n=design.get('drawers',2) if purpose=='nightstand' else 0
            if n:
                for i in range(n):
                    box('drawer front',0,-.48,(i+.5)/n,.91,.04,.94/n)
                    box('drawer pull',0,-.495,(i+.5)/n,.18,.01,.025,'accent')
            else:
                n=design.get('doors',2)
                for i in range(n):
                    x=-.46+.92*(i+.5)/n
                    box('door',x,-.48,.5,.9/n,.04,.94)
                    box('door pull',x,-.495,.55,.035,.01,.15,'accent')
    elif purpose=='television':
        box('stand base',0,0,.025,.7,1,.05,'accent');box('stand stem',0,0,.16,.05,.07,.25,'accent')
        box('screen',0,.1,.62,1,.08,.76,'glass')
    elif purpose in ('washer','dishwasher','fridge','cooker'):
        box('appliance body',0,0,.5,1,1,1,'enamel')
        box('control panel',0,-.497,.9,.85,.006,.1,'accent')
        if purpose=='washer':box('drum door',0,-.499,.46,.65,.002,.6,'glass')
        elif purpose=='cooker':
            box('oven door',0,-.499,.48,.8,.002,.62,'glass')
            for x in (-.25,.25):
                for y in (-.25,.25):box('burner',x,y,.997,.27,.27,.006,'accent')
        else:
            box('door seam',0,-.499,.55,.9,.002,.01,'accent')
            box('handle',.36,-.499,.7,.04,.002,.2,'accent')
    elif purpose in ('sink','vanity'):
        box('base cabinet',0,0,.35,1,1,.7)
        for x in (-.47,.47):box('basin side',x,0,.79,.06,1,.18,'enamel')
        for y in (-.47,.47):box('basin rim',0,y,.79,.88,.06,.18,'enamel')
        box('basin bottom',0,0,.71,.88,.88,.025,'enamel')
        box('faucet',0,.33,.92,.06,.05,.16,'accent')
        box('spout',0,.23,.985,.06,.23,.03,'accent')
    elif purpose=='toilet':
        box('pedestal',0,-.1,.2,.5,.6,.4,'enamel')
        box('seat',0,-.12,.45,1,.76,.12,'enamel')
        box('cistern',0,.38,.7,.85,.24,.6,'enamel')
    elif purpose=='shower':
        box('tray',0,0,.025,1,1,.05,'enamel')
        box('back glass',0,.49,.5,1,.02,1,'glass')
        box('side glass',.49,0,.5,.02,1,1,'glass')
        box('shower rail',0,.44,.58,.03,.03,.7,'accent')
        box('shower head',0,.32,.93,.2,.25,.04,'accent')
    else:raise ValueError('此用途尚無可保留必要機能的概念模型')
    for part in result:
        if part.get('shape')=='lathe':
            origin=list(part['center']);radius=max(p[0] for p in part['profile']);bottom=min(p[1] for p in part['profile']);top=max(p[1] for p in part['profile'])
            part.update(origin=origin,center=[origin[0],origin[1],origin[2]+(bottom+top)/2],size=[2*radius,2*radius,top-bottom])
    return result
