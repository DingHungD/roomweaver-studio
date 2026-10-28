import copy,itertools
import pytest
from interior.workbench.studio.framing_fit import fit_issue,project

@pytest.mark.parametrize('aspect',['4:3','16:9'])
def test_fit_keeps_top_bottom_all_subjects_and_eye(aspect):
    shot=dict(id='photo',yaw=90,pitch=-20,lens=24,aspect=aspect,shift_y=0,eye=[0,0,1.6])
    scene=dict(groups=[dict(id='tall'),dict(id='low')],viewpoints=[dict(id='view',eye=[0,0,1.6],shots=[shot])])
    original=copy.deepcopy(scene)
    bounds=[dict(id='tall',bounds=[[-.3,2,0],[.3,2.7,2.2]]),dict(id='low',bounds=[[.3,1.2,0],[.7,1.9,.8]])]
    issue=dict(category='viewpoint',action='shot',target_id='view',shot_id='photo',framing_group_ids=['tall','low'],values={'lens':20})
    fitted,proof=fit_issue(scene,scene,issue,dict(measurements=bounds))
    assert scene==original and proof['eye']==shot['eye']
    pose=dict(shot,**fitted['values']);height=10.125 if aspect=='16:9' else 13.5
    for b in bounds:
        for corner in itertools.product(*zip(*b['bounds'])):
            x,y=project(corner,shot['eye'],pose)
            assert abs(x*pose['lens'])<=18*.94 and abs(y*pose['lens'])<=height*.94
    with pytest.raises(ValueError):fit_issue(scene,scene,dict(issue,framing_group_ids=['unknown']),dict(measurements=bounds))

def test_missing_subject_list_does_not_guess_or_reframe():
    issue={'values':{'lens':20}}
    assert fit_issue({}, {}, issue, {})==(issue,None)


def test_behind_camera_is_rejected_instead_of_dropping_subject():
    scene=dict(groups=[dict(id='behind')],viewpoints=[dict(id='v',eye=[0,0,1.6],shots=[dict(id='s',yaw=90,pitch=0,lens=24)])])
    issue=dict(category='viewpoint',action='shot',target_id='v',shot_id='s',framing_group_ids=['behind'])
    with pytest.raises(ValueError,match='無法完整'):
        fit_issue(scene,scene,issue,dict(measurements=[dict(id='behind',bounds=[[-1,-4,0],[1,-3,2]])]))
