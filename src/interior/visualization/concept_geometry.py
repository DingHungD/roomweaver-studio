"""Shared deterministic concept furniture: metre box parts, Z up, front -Y."""
CATALOG={
 'chair':{'name':'椅子','size':[.5,.5,.85]}, 'desk':{'name':'書桌','size':[1.2,.6,.75]},
 'table':{'name':'餐桌','size':[1.4,.8,.75]},'bed':{'name':'床','size':[1.5,2,.55]},
 'sofa':{'name':'沙發','size':[2.1,.9,.8]},'cabinet':{'name':'收納櫃','size':[1.2,.45,1.8]},
 'bunk_bed':{'name':'上下舖','size':[1.12,2.06,1.8]},'washer':{'name':'洗衣機','size':[.6,.6,.85]},
 'cooker':{'name':'爐具櫃','size':[.6,.6,.85]},'television':{'name':'電視','size':[1.2,.3,1.2]},
 'ceiling_light':{'name':'天花燈具','size':[.45,.45,.12]},
 'floor_lamp':{'name':'落地燈','size':[.4,.4,1.5]},
 'vase':{'name':'花瓶與花','size':[.18,.18,.3]},'books':{'name':'書籍','size':[.24,.18,.08]},
 'cookware':{'name':'鍋具','size':[.3,.25,.18]},'tableware':{'name':'餐具','size':[.22,.22,.1]},
 'soap':{'name':'洗手乳','size':[.09,.09,.18]},'plant':{'name':'盆栽','size':[.4,.4,.7]},
 'rug':{'name':'地毯','size':[1.6,1.0,.015]}}

def parts(identifier,asset,size):
    import math
    minimum=.005 if asset in ('ceiling_light','floor_lamp','vase','books','cookware','tableware','soap','plant','rug') else .2
    if asset not in CATALOG or len(size)!=3 or any(not math.isfinite(v) or not minimum<=v<=5 for v in size):raise ValueError('概念家具類型或尺寸無效')
    w,d,h=size;result=[]
    def box(name,x,y,z,a,b,c):result.append(dict(id=identifier+'-'+name,name=name,center=[x,y,z+c/2],size=[a,b,c]))
    if asset in ('chair','desk','table'):
        top=h*.53 if asset=='chair' else h
        box('top',0,0,top-.05,w,d,.05)
        for i,x in enumerate((-w*.4,w*.4)):
            for j,y in enumerate((-d*.4,d*.4)):box(f'leg-{i}{j}',x,y,0,.04,.04,top-.05)
        if asset=='chair':box('back',0,d*.44,top,w,.06,h-top)
    elif asset=='bed':
        box('frame',0,0,0,w,d,h*.4);box('mattress',0,0,h*.4,w*.98,d*.96,h*.5)
        for i,x in enumerate((-w*.25,w*.25)):box('pillow-'+str(i),x,d*.32,h*.9,w*.4,d*.18,h*.1)
    elif asset=='sofa':
        box('base',0,0,0,w,d,h*.3);box('seat',0,-d*.05,h*.3,w*.84,d*.8,h*.25)
        box('back',0,d*.4,h*.3,w,d*.2,h*.7)
        for i,x in enumerate((-w*.46,w*.46)):box('arm-'+str(i),x,0,h*.3,w*.08,d,h*.45)
    elif asset=='bunk_bed':
        for i,z in enumerate((h*.15,h*.68)):box('mattress-'+str(i),0,0,z,w,d,h*.1)
        for i,x in enumerate((-w*.46,w*.46)):
            for j,y in enumerate((-d*.46,d*.46)):box(f'post-{i}{j}',x,y,0,.06,.06,h)
        for i in range(5):box('rung-'+str(i),0,-d*.46,h*.12+i*h*.14,w*.4,.05,.04)
    elif asset=='television':
        box('base',0,0,0,w*.5,d,.04);box('stand',0,0,.04,.05,.05,h*.25);box('screen',0,0,h*.29,w,.05,h*.71)
    elif asset=='ceiling_light':
        box('shade',0,0,0,w,d,h)
    elif asset=='floor_lamp':
        box('base',0,0,0,w,d,.04);box('stem',0,0,.04,.025,.025,h*.75)
        box('shade',0,0,h*.75,w,d,h*.25)
    elif asset in ('vase','books','cookware','tableware','soap','plant','rug'):
        box('placeholder',0,0,0,w,d,h)
    else:
        box('body',0,0,0,w,d,h);box('front',0,-d*.495,h*.08,w*.9,d*.01,h*.8)
    return result

def add_blender_furniture(furniture):
    """Add to the in-memory working scene; never overwrite the source model."""
    import bpy
    for item in furniture:
        for p in parts(item['id'],item['asset'],item['size']):
            bpy.ops.mesh.primitive_cube_add(size=1,location=p['center'])
            obj=bpy.context.object;obj.name=item['name']+' / '+p['name'];obj.dimensions=p['size']
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            obj['studio_id']=p['id'];obj['source_id']=item['id'];obj['role']='furniture'
            material=bpy.data.materials.get('Concept furniture') or bpy.data.materials.new('Concept furniture')
            material.diffuse_color=(.55,.42,.29,1);material.use_nodes=True
            material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.55,.42,.29,1)
            material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.7
            obj.data.materials.append(material)
