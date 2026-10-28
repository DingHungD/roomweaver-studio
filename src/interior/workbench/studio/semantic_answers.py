"""Question-scoped source annotations, separate from adopted CAD geometry."""
import math

from PIL import Image,ImageDraw,ImageFont
from pathlib import Path


def validate_annotations(annotations,view):
    """Reject unbounded strokes and coordinates outside this immutable source view."""
    if sum(len(marks) for marks in annotations.values())>100:
        raise ValueError('圖上標註最多 100 筆')
    result={};seen=set()
    for question,marks in annotations.items():
        result[question]=[]
        for mark in marks:
            data=mark.model_dump(mode='json',exclude_none=True)
            if data['id'] in seen:raise ValueError('標註識別碼重複')
            seen.add(data['id'])
            if data['kind']=='line' and len(data['points'])!=2:raise ValueError('A B 標註必須有兩端點')
            if data['kind']=='box' and (len(data['points'])!=2 or any(abs(data['points'][0][k]-data['points'][1][k])<1e-6 for k in (0,1))):raise ValueError('方框需要兩個不同的對角')
            if data['kind']=='text' and (len(data['points'])!=1 or not data.get('text','').strip()):raise ValueError('文字需要一個位置及文字內容')
            if data['kind']=='freehand' and len(data['points'])<2:raise ValueError('圈畫至少需要兩個點')
            for x,y in data['points']:
                px=view['pad']+(x-view['bounds'][0])*view['scale']
                py=view['pad']+(view['bounds'][3]-y)*view['scale']
                if not all(math.isfinite(v) for v in (x,y,px,py)) or not (0<=px<=view['width'] and 0<=py<=view['height']):
                    raise ValueError('標註超出原圖，請在圖面內作答')
            if data['kind']!='text' and not any(math.dist(data['points'][0],p)>1e-6 for p in data['points'][1:]):raise ValueError('標註需要不同的端點')
            result[question].append(data)
    return result


def draw_answer_annotations(source,view,answers,folder):
    """Supply the Agent visible strokes plus exact coordinates without overwriting source."""
    outputs=[]
    for index,answer in enumerate(answers):
        marks=answer.get('annotations',[])
        if not marks:continue
        image=Image.open(source).convert('RGB');draw=ImageDraw.Draw(image)
        for mark in marks:
            points=[(view['pad']+(p[0]-view['bounds'][0])*view['scale'],view['pad']+(view['bounds'][3]-p[1])*view['scale']) for p in mark['points']]
            if mark['kind']=='box':
                a,b=points;draw.rectangle((min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])),outline='#c02d87',width=4)
            elif mark['kind']=='text':
                font=ImageFont.load_default(size=20)
                for path in ['C:/Windows/Fonts/msjh.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
                    if Path(path).is_file():font=ImageFont.truetype(path,20);break
                draw.text(points[0],mark.get('text',''),font=font,fill='#9c1265',stroke_width=1,stroke_fill='white')
            else:draw.line(points,fill='#c02d87',width=4)
            if mark['kind']=='line':
                for label,(x,y) in zip(('A','B'),(points[0],points[-1])):
                    draw.ellipse((x-5,y-5,x+5,y+5),fill='#c02d87')
                    draw.text((x+8,y-15),f"{answer['question']['label']} {label}",fill='#9c1265',stroke_width=1)
        target=folder/f'answer-annotation-{index+1}.png'
        image.save(target);outputs.append(str(target))
    return outputs
