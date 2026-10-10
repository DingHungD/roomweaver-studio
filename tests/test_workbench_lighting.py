"""Bounded lighting edits, locked fixtures, retries and stale proposals."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from interior.workbench.studio.models import LightingSetup, StudioLight
from interior.workbench.studio.lighting import validate_adjustments,optimize
from interior.workbench.storage import write_json,read_json

class LightingTests(unittest.TestCase):
    def setup_data(self):
        return LightingSetup(enabled=True,agent_review=True,lights=[StudioLight(id='lamp',name='Lamp',position=(0,0,2.5),power=100)]).model_dump(mode='json')

    def test_agent_cannot_change_locked_unknown_or_out_of_bounds_light(self):
        setup=self.setup_data();setup['lights'][0]['locked']=True
        for patch_data in [dict(id='lamp',power=150),dict(id='unknown',power=100)]:
            with self.assertRaises(ValueError):validate_adjustments(setup,dict(decision='adjust',adjustments=[patch_data]))
        setup['lights'][0]['locked']=False
        for patch_data in [dict(id='lamp',power=300),dict(id='lamp',position=[1,2,3]),dict(id='lamp',color=[-1,1,1]),dict(id='lamp',power=float('nan'))]:
            with self.assertRaises(ValueError):validate_adjustments(setup,dict(decision='adjust',adjustments=[patch_data]))

    def test_retries_use_effective_lighting_and_do_not_mutate_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup=self.setup_data();original=copy.deepcopy(setup)
            req=dict(scene=dict(lighting_setup=setup),revision='a'*32)
            powers=[]
            def render(payload,folder):
                powers.append(payload['scene']['lighting_setup']['lights'][0]['power'])
                write_json(folder/'quality-checks.json',dict(status='blocked' if len(powers)==1 else 'passed',checks=[]))
                return int(len(powers)==1)
            replies=[dict(decision='adjust',reason='dark',adjustments=[dict(id='lamp',power=150)]),dict(decision='ready',reason='okay',adjustments=[])]
            with patch('interior.workbench.studio.lighting.review',side_effect=replies):optimize(req,root,render)
            self.assertEqual(powers,[100,150]);self.assertEqual(setup,original)
            self.assertEqual(req['scene']['lighting_setup']['lights'][0]['power'],150)
            self.assertEqual(read_json(root/'effective-lighting.json')['attempts'],2)

    def test_three_attempt_limit_and_locked_local_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup=self.setup_data();setup['agent_review']=False
            calls=[]
            def render(payload,folder):
                calls.append(payload['scene']['lighting_setup']['lights'][0]['power'])
                write_json(folder/'quality-checks.json',dict(status='blocked',checks=[]));return 1
            with self.assertRaisesRegex(ValueError,'三輪'):optimize(dict(scene=dict(lighting_setup=setup),revision='a'*32),root,render)
            self.assertEqual(calls,[100,200,400])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup['lights'][0]['locked']=True;calls.clear()
            with self.assertRaisesRegex(ValueError,'需要確認'):optimize(dict(scene=dict(lighting_setup=setup),revision='a'*32),root,render)
            self.assertEqual(calls,[100])

    def test_stop_and_failed_agent_do_not_silently_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write_json(root/'stop-requested.json',{})
            with self.assertRaisesRegex(ValueError,'停止'):optimize(dict(scene=dict(lighting_setup=self.setup_data()),revision='a'*32),root,lambda *_:self.fail('must not render'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def render(payload,folder):write_json(folder/'quality-checks.json',dict(status='passed'));return 0
            with patch('interior.workbench.studio.lighting.review',side_effect=ValueError('login failed')):
                with self.assertRaisesRegex(ValueError,'login failed'):optimize(dict(scene=dict(lighting_setup=self.setup_data()),revision='a'*32),root,render)
            self.assertFalse((root/'effective-lighting.json').exists())
