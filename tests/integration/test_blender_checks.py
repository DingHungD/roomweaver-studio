"""Lighting guards and real Blender regressions on synthetic rooms."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from interior.visualization.studio_render_checks import luminance_report
from interior.workbench.studio.engine import blender_executable

class PixelChecks(unittest.TestCase):
    def test_dark_and_tiny_bright_speck_do_not_pass(self):
        self.assertEqual(luminance_report([(0,0,0)]*1000)['status'],'blocked')
        self.assertEqual(luminance_report([(0,0,0)]*999+[(1,1,1)])['status'],'blocked')
    def test_lit_and_mixed_shadow_image_pass(self):
        self.assertEqual(luminance_report([(.15,.1,.1)]*100)['status'],'passed')
        self.assertEqual(luminance_report([(0,0,0)]*70+[(.2,.1,.1)]*30)['status'],'passed')

class BlenderChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.exe=blender_executable();cls.repo=Path(__file__).resolve().parents[2]
        fixture=cls.repo/'tests/fixtures/visualization/studio_lighting/build_scene.py'
        result=subprocess.run([cls.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(fixture),'--',str(cls.root)],capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stdout.decode(errors='replace')[-2000:])
        cls.scene=json.loads((cls.root/'scene.json').read_text(encoding='utf-8'))
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def render(self,name):
        out=self.root/(name+'-run');out.mkdir()
        source=self.root/(name+'.blend');before=hashlib.sha256(source.read_bytes()).hexdigest()
        request=dict(mode='render',source=str(source),output=str(out),scene=self.scene,revision='b'*32,quality='preview',model_id='a'*32)
        (out/'request.json').write_text(json.dumps(request))
        script=self.repo/'src/interior/visualization/studio_blender.py'
        result=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(out/'request.json')],capture_output=True,timeout=180)
        self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())
        return out,result
    def test_no_light_rejected_before_render(self):
        out,result=self.render('dark')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads((out/'render-readiness.json').read_text(encoding='utf-8'))['status'],'blocked')
        self.assertFalse(list(out.glob('*.png')))
    def test_display_only_and_native_pair_import_have_different_readiness(self):
        for kind,source,expected in [('display',self.root/'display.glb','blocked'),('native',self.root/'lit.blend','needs_probe')]:
            with self.subTest(kind=kind):
                out=self.root/('prepare-'+kind);out.mkdir()
                request=dict(mode='prepare',source=str(source),preview=str(self.root/'display.glb'),output=str(out),
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),model_id='c'*32)
                (out/'request.json').write_text(json.dumps(request))
                script=self.repo/'src/interior/visualization/studio_blender.py'
                result=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(out/'request.json')],capture_output=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout.decode(errors='replace')[-2000:])
                metadata=json.loads((out/'model.json').read_text(encoding='utf-8'))
                self.assertEqual(metadata['render_readiness']['status'],expected)
    def test_hidden_light_is_not_usable(self):
        out,result=self.render('hidden')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads((out/'render-readiness.json').read_text(encoding='utf-8'))['light_count'],0)
    def test_present_but_occluded_light_fails_probe(self):
        out,result=self.render('occluded')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads((out/'render-readiness.json').read_text(encoding='utf-8'))['light_count'],1)
        self.assertEqual(json.loads((out/'quality-checks.json').read_text(encoding='utf-8'))['status'],'blocked')
        self.assertFalse((out/'result.json').exists())
        self.assertFalse((out/'one-panorama.png').exists())
    def test_lit_scene_generates_both_images_after_probes(self):
        out,result=self.render('lit')
        self.assertEqual(result.returncode,0,result.stdout.decode(errors='replace')[-2000:])
        quality=json.loads((out/'quality-checks.json').read_text(encoding='utf-8'))
        self.assertEqual(quality['status'],'passed')
        self.assertEqual(len(quality['checks']),2)
        rendered=json.loads((out/'result.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rendered['images']),2)
        self.assertEqual(rendered['visual_review'],'pending')

    def test_automatic_ceiling_proposal_lights_dark_room_and_tracks_group(self):
        from interior.workbench.studio.models import LightingSetup
        import copy
        out=self.root/'automatic-plan';out.mkdir()
        request=dict(mode='lighting',job_id='d'*32,source=str(self.root/'dark.blend'),output=str(out),scene=self.scene,revision='b'*32,model_id='a'*32)
        script=self.repo/'src/interior/visualization/studio_blender.py'
        def invoke(payload):
            path=Path(payload['output'])/'request.json';path.write_text(json.dumps(payload))
            run=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(path)],capture_output=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout.decode(errors='replace')[-2500:])
        invoke(request)
        plan=json.loads((out/'result.json').read_text(encoding='utf-8'))
        setup=LightingSetup.model_validate(plan['lighting_setup']).model_dump(mode='json')
        self.assertEqual(len(setup['lights']),1)
        self.assertAlmostEqual(setup['lights'][0]['position'][2],2.85,places=3)
        design=copy.deepcopy(self.scene)
        design['groups']=[dict(id='table-group',children=['table'],translation=[.3,0,0],deleted=False)]
        setup['lights'][0]['group_id']='table-group'
        design['lighting_setup']=setup
        rendered=self.root/'automatic-render';rendered.mkdir()
        request.update(mode='render',output=str(rendered),scene=design,quality='preview',probe_only=True)
        invoke(request)
        applied=json.loads((rendered/'lighting-applied.json').read_text(encoding='utf-8'))
        self.assertAlmostEqual(applied['lights'][0]['position'][0],.3,places=3)
        self.assertEqual(json.loads((rendered/'quality-checks.json').read_text(encoding='utf-8'))['status'],'passed')
        design['groups'][0]['deleted']=True
        removed=self.root/'automatic-deleted';removed.mkdir()
        request.update(output=str(removed))
        path=removed/'request.json';path.write_text(json.dumps(request))
        run=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(path)],capture_output=True,timeout=120)
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(json.loads((removed/'lighting-applied.json').read_text(encoding='utf-8'))['lights'],[])

    def test_restored_lights_retain_evaluated_world_position(self):
        out=self.root/'restored-plan';out.mkdir()
        request=dict(mode='lighting',job_id='e'*32,source=str(self.root/'dark.blend'),output=str(out),scene=self.scene,
            revision='b'*32,model_id='a'*32,lighting_source=dict(path=str(self.root/'lit.blend')))
        path=out/'request.json';path.write_text(json.dumps(request))
        script=self.repo/'src/interior/visualization/studio_blender.py'
        run=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(path)],capture_output=True,timeout=90)
        self.assertEqual(run.returncode,0,run.stdout.decode(errors='replace')[-2000:])
        lights=json.loads((out/'result.json').read_text(encoding='utf-8'))['lighting_setup']['lights']
        self.assertEqual(len(lights),1)
        self.assertAlmostEqual(lights[0]['position'][2],2.8,places=3)
        self.assertEqual(lights[0]['origin'],'restored')

    def test_custom_light_shader_not_silently_replaced(self):
        out=self.root/'custom-plan';out.mkdir()
        request=dict(mode='lighting',job_id='f'*32,source=str(self.root/'custom-light.blend'),output=str(out),scene=self.scene,revision='b'*32,model_id='a'*32)
        path=out/'request.json';path.write_text(json.dumps(request))
        script=self.repo/'src/interior/visualization/studio_blender.py'
        run=subprocess.run([self.exe,'--background','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(path)],capture_output=True,timeout=90)
        self.assertNotEqual(run.returncode,0)
        self.assertFalse((out/'result.json').exists())

if __name__=='__main__':unittest.main()
