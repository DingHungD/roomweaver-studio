"""Rebuild the paired PNG/DXF tutorials from the sanitized metric layout.

Run with the Roomweaver Python environment. The image remains a genuine raster
input; its JSON is not supplied to the recognition service.
"""
from pathlib import Path
import json, math
import ezdxf
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'layout.json').read_text())
doc=ezdxf.new('R2013');doc.units=4
m=doc.modelspace()
def layer(name):
    if name not in doc.layers:doc.layers.new(name)
    return {'layer':name}
def line(name,a,b):m.add_line([v*1000 for v in a],[v*1000 for v in b],dxfattribs=layer(name))
def polygon(name,points):m.add_lwpolyline([[v*1000 for v in p] for p in points],close=True,dxfattribs=layer(name))
# Split the concave footprint into nonoverlapping convex strips for the importer.
ys=sorted(set(p[1] for p in data['floor']))
floors=[]
for low,high in zip(ys,ys[1:]):
    mid=(low+high)/2;xs=[]
    for a,b in zip(data['floor'],data['floor'][1:]+data['floor'][:1]):
        if min(a[1],b[1])<mid<max(a[1],b[1]):xs.append(a[0])
    xs.sort()
    for left,right in zip(xs[::2],xs[1::2]):floors.append([[left,low],[right,low],[right,high],[left,high]])
for i,p in enumerate(floors):polygon(f'floor-{i+1}',p)
for w in data['walls']:line('wall-'+w['id'],w['a'],w['b'])
for o in data['openings']:line(o['kind']+'-'+o['id'],o['a'],o['b'])
def footprint(f):
    x,y=f['center'];w,h=f['size'];a=math.radians(f['angle'])
    return [[x+u*math.cos(a)-v*math.sin(a),y+u*math.sin(a)+v*math.cos(a)] for u,v in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]
for f in data['furniture']:polygon('furniture-'+f['id'],footprint(f))
doc.saveas(ROOT/'project04-plan.dxf')
img=Image.new('RGB',(1900,1750),'#faf9f4');d=ImageDraw.Draw(img)
def font(n):
    for p in ['C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(p).exists():return ImageFont.truetype(p,n)
    return ImageFont.load_default(size=n)
def screen(p):return (180+p[0]*180,1430-p[1]*180)
d.text((100,35),'PROJECT04 / IMAGE & DXF IMPORT EXAMPLE',font=font(36),fill='#244c42')
d.text((100,90),'Units: metres | dimensions describe wall centre lines | teaching derivative',font=font(24),fill='#53665e')
for p in floors:d.polygon([screen(q) for q in p],fill='#eee7d8')
for w in data['walls']:d.line([screen(w['a']),screen(w['b'])],fill='#343e3a',width=max(8,round(w['thickness']*180)))
for o in data['openings']:
    d.line([screen(o['a']),screen(o['b'])],fill='#eee7d8',width=38)
    d.line([screen(o['a']),screen(o['b'])],fill='#c57423' if o['kind']=='door' else '#2a8bb6',width=7)
    a,b=screen(o['a']),screen(o['b']);d.text(((a[0]+b[0])/2+8,(a[1]+b[1])/2),o['id'],font=font(14),fill='#34544b')
for f in data['furniture']:
    d.polygon([screen(q) for q in footprint(f)],fill='#acbfa9',outline='#52705a',width=2)
    x,y=screen(f['center']);d.text((x,y),f['id'],anchor='mm',font=font(15),fill='#173d30')
for title,p in [('CHILD ROOM',(2.55,2.5)),('MASTER ROOM',(5.1,3.25)),('BATH',(7.4,2.0)),('KITCHEN',(1.8,1.1)),('LIVING',(5.0,1.8)),('ENTRY',(7.4,-.2)),('BALCONY',(2.2,5.15))]:
    d.text(screen(p),title,anchor='mm',font=font(23),fill='#213e34')
def dimension(a,b,label):
    pa,pb=screen(a),screen(b);d.line([pa,pb],fill='#465c53',width=2)
    for x,y in [pa,pb]:d.ellipse((x-4,y-4,x+4,y+4),fill='#465c53')
    x=(pa[0]+pb[0])/2;y=(pa[1]+pb[1])/2
    box=d.textbbox((x,y-20),label,font=font(22),anchor='mm');d.rectangle((box[0]-6,box[1]-4,box[2]+6,box[3]+4),fill='#faf9f4');d.text((x,y-20),label,font=font(22),anchor='mm',fill='#182f25')
dimension((-.075,6.30),(8.03,6.30),'8.105 m')
dimension((8.7,-.649),(8.7,5.925),'6.574 m')
dimension((.956,4.85),(3.693,4.85),'2.737 m')
dimension((3.693,3.05),(6.67,3.05),'2.977 m')
dimension((0,-.35),(3.174,-.35),'3.174 m')
d.text((100,1555),'ORANGE = door opening | BLUE = window opening | GREEN = furniture footprint',font=font(25),fill='#435b50')
d.text((100,1600),'Wall thickness varies. Heights / unlabelled openings are illustrative, not construction dimensions.',font=font(23),fill='#435b50')
d.text((100,1645),'Use numeric annotations for scale; keep right angles. Review recognition before building 3D.',font=font(23),fill='#435b50')
img.save(ROOT.parent/'from-image/project04-plan.png')
print('Created DXF and PNG:',len(data['walls']),'walls,',len(data['openings']),'openings,',len(data['furniture']),'furniture,',len(floors),'floor strips')
