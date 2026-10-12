"""Rebuild this synthetic, MIT-licensed DXF and its explanatory preview."""
from pathlib import Path
import ezdxf
from PIL import Image, ImageDraw

root=Path(__file__).parent
doc=ezdxf.new('R2013');doc.units=4
for name in ('wall','floor','door','window','furniture'):
    doc.layers.new(name)
m=doc.modelspace()
def line(layer,a,b):m.add_line(a,b,dxfattribs={'layer':layer})
def rect(layer,x,y,w,h):m.add_lwpolyline([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],close=True,dxfattribs={'layer':layer})
rect('floor',0,0,7000,6000)
for a,b in [((0,0),(7000,0)),((7000,0),(7000,6000)),((7000,6000),(0,6000)),((0,6000),(0,0)),((4000,0),(4000,6000))]:line('wall',a,b)
line('door',(1000,0),(2000,0));line('door',(4000,1100),(4000,2000))
line('window',(7000,3000),(7000,4800));line('window',(600,6000),(2700,6000))
rect('furniture',400,3400,850,2100)
rect('furniture',1800,3900,1100,600)
rect('furniture',4700,3400,1600,2100)
rect('furniture',4800,300,1800,500)
doc.saveas(root/'courtyard.dxf')
image=Image.new('RGB',(1000,900),'#fafaf5');draw=ImageDraw.Draw(image)
def screen(p):return (100+p[0]*.11,780-p[1]*.11)
for entity in m:
    layer=entity.dxf.layer
    color={'wall':'#344b42','floor':'#e0d4bb','door':'#c98633','window':'#418fa9','furniture':'#829b8b'}[layer]
    if entity.dxftype()=='LINE':draw.line([screen(entity.dxf.start),screen(entity.dxf.end)],fill=color,width=14 if layer=='wall' else 12)
    else:draw.polygon([screen(p) for p in entity.get_points()],fill=color,outline='#56675d')
draw.text((100,40),'ROOMWEAVER | DXF PLAN EXAMPLE',fill='#24493e',font_size=30)
draw.text((100,80),'7.0 x 6.0 m | 5 walls | 2 doors | 2 windows | 4 placeholders',fill='#637268',font_size=20)
draw.text((110,820),'Dark: wall   /   Amber: door opening   /   Blue: window opening',fill='#4f655a',font_size=22)
image.save(root/'preview.png')
