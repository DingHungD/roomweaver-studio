"""Generate two original synthetic sketches; no customer data or model answers."""
from pathlib import Path
import random
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).parent
font_path=Path('C:/Windows/Fonts/segoepr.ttf')
font=ImageFont.truetype(str(font_path),23) if font_path.exists() else ImageFont.load_default(size=23)
def make(name,outline,labels,features):
    rng=random.Random(name);im=Image.new('RGB',(1000,800),'#fffdf8');d=ImageDraw.Draw(im)
    def line(points,width=4):
        for a,b in zip(points,points[1:]):
            pts=[(a[0]+(b[0]-a[0])*i/10+rng.uniform(-1.5,1.5),a[1]+(b[1]-a[1])*i/10+rng.uniform(-1.5,1.5)) for i in range(11)]
            d.line(pts,fill='#293f65',width=width)
    line(outline+[outline[0]],5)
    for points in features:line(points,3)
    for xy,text in labels:d.text(xy,text,fill='#293f65',font=font)
    d.text((45,735),'Synthetic sketch / metres / not a real property',fill='#666666',font=font)
    im.save(ROOT/name)
make('studio-a.png',[(150,180),(750,180),(750,630),(150,630)],
    [((305,90),'4.00 m'),((775,375),'3.00 m'),((185,655),'ENTRY 0.90 m'),((390,230),'STUDIO A'),((350,140),'WINDOW'),((620,500),'?')],
    [[(150,145),(750,145)],[(150,130),(150,160)],[(750,130),(750,160)],[(795,180),(795,630)],[(780,180),(810,180)],[(780,630),(810,630)],[(340,173),(540,173)],[(340,187),(540,187)],[(190,630),(190,495),(325,630)],[(575,460),(705,460),(705,585),(575,585),(575,460)]])
make('courtyard-b.png',[(160,160),(760,160),(760,400),(460,400),(460,640),(160,640)],
    [((355,75),'5.00 m'),((70,350),'4.00 m'),((515,415),'2.50 m'),((270,660),'2.50 m'),((450,225),'L ROOM B'),((200,515),'?'),((480,130),'WINDOW'),((125,565),'ENTRY')],
    [[(160,125),(760,125)],[(160,110),(160,140)],[(760,110),(760,140)],[(110,160),(110,640)],[(95,160),(125,160)],[(95,640),(125,640)],[(490,154),(675,154)],[(490,166),(675,166)],[(160,580),(268,580),(160,688)],[(195,470),(295,470),(295,555),(195,555),(195,470)]])
