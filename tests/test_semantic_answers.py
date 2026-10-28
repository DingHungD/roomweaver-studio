"""Source-registered answers generalize without editing a case or calling a model."""
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image,ImageChops

from test_plan_semantics import system,candidate
from interior.workbench.storage import Conflict
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,SaveSemanticAnswers,AnswerAnnotation,prompt
from interior.workbench.studio.semantic_answers import validate_annotations,draw_answer_annotations


def test_annotations_are_saved_reopened_and_sent_as_image_and_coordinates(system):
    studio,plans,packet,_=system
    class Agents:
        def start(self,kind,model,payload,identifier):
            self.payload=payload;self.result=dict(status='passed',candidate=candidate(payload['site']))
            self.result['candidate']['questions']=[dict(id='opening',title='Opening',ask='Which endpoints?',reason='Two possible openings',source_ids=[payload['site']['geometry'][1]['id']],box=None)]
        def get(self,identifier):return self.result
    agents=Agents();service=PlanSemantics(studio,agents)
    def start():return service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,mode='review'))
    run=start();source=Path(agents.payload['image']);before=source.read_bytes()
    marks={'opening':[dict(id='ab',kind='line',points=[[1,0],[2,0]]),dict(id='circle',kind='freehand',points=[[1,1],[2,1],[2,2],[1,1]])]}
    body=SaveSemanticAnswers(base_revision=packet['revision'],answers={'opening':'A to B is the doorway'},annotations=marks)
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],body)
    assert saved['answers']['annotations']==marks
    assert service.get('UNRELATED',packet['id'],run['id'])['answers']==saved['answers']
    with pytest.raises(Conflict):service.save_answers('UNRELATED',packet['id'],run['id'],body)
    body.answers_revision=saved['answers']['revision'];body.annotations={'invented':[]}
    with pytest.raises(ValueError,match='不存在'):service.save_answers('UNRELATED',packet['id'],run['id'],body)
    fresh=start();answer=fresh['site']['confirmed_answers'][0]
    assert answer['annotations']==marks['opening'] and answer['answer']=='A to B is the doorway'
    assert fresh['answers']['answers']=={'opening':'A to B is the doorway'}
    assert fresh['answers']['annotations']==marks
    assert fresh['answers']['revision'] is None
    images=[Path(p) for p in agents.payload['source_images'] if 'answer-annotation' in p]
    assert len(images)==1 and ImageChops.difference(Image.open(images[0]),Image.open(agents.payload['image'])).getbbox()
    assert source.read_bytes()==before
    assert plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
    assert 'annotations' in prompt(fresh['site'])
    # Resolved questions disappear from the next report, but their confirmations
    # must still be available on later review rounds for this same source revision.
    agents.result['candidate']['questions']=[]
    third=start()
    assert third['site']['confirmed_answers'][0]['annotations']==marks['opening']
    agents.result['candidate']['questions']=[]
    resolved=service.get('UNRELATED',packet['id'],third['id'])
    assert resolved['answers']['answers']=={} and resolved['answers']['annotations']=={}


def test_question_box_text_edits_and_deletion_reopen_without_changing_source(system,tmp_path):
    studio,plans,packet,_=system
    class Agents:
        def start(self,kind,model,payload,identifier):
            self.result=dict(status='passed',candidate=candidate(payload['site']))
            self.result['candidate']['questions']=[dict(id='q',title='Opening',ask='Confirm doorway',reason='Unclear',source_ids=[payload['site']['geometry'][1]['id']],box=None)]
        def get(self,identifier):return self.result
    service=PlanSemantics(studio,Agents());run=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    original=plans.current('UNRELATED',packet['id']);source=Path(studio.root('UNRELATED')/packet['source']['path']).read_bytes()
    marks=[dict(id='box',kind='box',points=[[1,1],[3,2]]),dict(id='text',kind='text',points=[[1,3]],text='門在這裡')]
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={'q':'框選處請核對'},annotations={'q':marks}))
    assert saved['answers']['annotations']['q']==marks
    changed=[dict(id='text',kind='text',points=[[2,3]],text='入口在這裡')]
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers_revision=saved['answers']['revision'],answers={'q':'保留尺寸'},annotations={'q':changed}))
    assert service.get('UNRELATED',packet['id'],run['id'])['answers']['annotations']['q']==changed
    image=tmp_path/'source.png';Image.new('RGB',(1000,800),'white').save(image)
    outputs=draw_answer_annotations(image,dict(width=1000,height=800,bounds=[0,0,10,8],pad=0,scale=100),[dict(question={'label':'Q1'},annotations=marks)],tmp_path)
    assert ImageChops.difference(Image.open(outputs[0]),Image.open(image)).getbbox()
    assert plans.current('UNRELATED',packet['id'])==original and Path(studio.root('UNRELATED')/packet['source']['path']).read_bytes()==source


@pytest.mark.parametrize('kind,points,text', [('box',[[1,1],[1,2]],None),('text',[[1,1]],''),('text',[[1,1],[2,2]],'A'),('freehand',[[1,1]],None)])
def test_new_question_mark_shape_validation(kind,points,text):
    view=dict(width=1000,height=800,bounds=[0,0,10,8],pad=0,scale=100)
    with pytest.raises(ValueError):validate_annotations({'q':[AnswerAnnotation(id='a',kind=kind,points=points,text=text)]},view)


@pytest.mark.parametrize('points,kind',[
    ([[1,1],[1,1]],'line'),([[1,1],[2,1],[3,1]],'line'),([[-300,1],[2,1]],'line')])
def test_invalid_annotations_do_not_enter_answer_history(points,kind):
    view=dict(width=1000,height=800,bounds=[-1,-2,9,6],scale=90,pad=40)
    with pytest.raises(ValueError):validate_annotations({'q':[AnswerAnnotation(id='a',kind=kind,points=points)]},view)


def test_annotation_limits_and_finite_coordinates():
    view=dict(width=1000,height=800,bounds=[-1,-2,9,6],scale=90,pad=40)
    with pytest.raises(ValueError):AnswerAnnotation(id='a',points=[[float('nan'),1],[2,1]])
    mark=AnswerAnnotation(id='a',points=[[1,1],[2,1]])
    with pytest.raises(ValueError,match='重複'):validate_annotations({'q':[mark,mark]},view)
    with pytest.raises(ValueError,match='100'):validate_annotations({'q':[mark]*101},view)


@pytest.mark.parametrize('bounds',[[-10,-20,0,-12],[100,200,110,208]])
def test_negative_and_offset_coordinates_remain_registered(tmp_path,bounds):
    view=dict(width=1000,height=800,bounds=bounds,scale=90,pad=40)
    marks=[dict(id='a',kind='line',points=[[bounds[0]+1,bounds[1]+2],[bounds[0]+2,bounds[1]+3]])]
    valid=validate_annotations({'q':[AnswerAnnotation(**m) for m in marks]},view)
    source=tmp_path/'source.png';Image.new('RGB',(1000,800),'white').save(source)
    paths=draw_answer_annotations(source,view,[dict(question={'label':'Q2'},annotations=valid['q'])],tmp_path)
    assert Image.open(paths[0]).getpixel((130,580))!=(255,255,255)
