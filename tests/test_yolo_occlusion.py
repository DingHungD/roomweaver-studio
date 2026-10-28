"""Standalone CPU checks for mask-aware occlusion; optional Torch is not a base dependency."""
import unittest

try:
    import torch
except ImportError:
    torch=None

from interior.object_recognition.training import occlude_batch


@unittest.skipIf(torch is None,'Optional recognition Torch runtime not installed')
class OcclusionTests(unittest.TestCase):
    def batch(self,masks,indices,image_size=10):
        return dict(img=torch.zeros((2,3,image_size,image_size)),masks=masks,
                    batch_idx=torch.tensor(indices,dtype=torch.float32),cls=torch.zeros((len(indices),1)),
                    bboxes=torch.tensor([[.5,.5,1.,1.]]*len(indices)))

    def test_visible_box_and_mask_update_together(self):
        batch=self.batch(torch.ones((1,10,10),dtype=torch.uint8),[0])
        result=occlude_batch(batch,(0,0,5,10),0)
        self.assertEqual(result,dict(changed=1,removed=0))
        self.assertEqual(batch['masks'].sum(),50)
        self.assertTrue(torch.allclose(batch['bboxes'][0],torch.tensor([.75,.5,.5,1.])))
        self.assertTrue((batch['img'][0,:,:,:5]==1).all())

    def test_overlapping_instances_and_other_image_are_handled(self):
        batch=self.batch(torch.ones((3,10,10),dtype=torch.uint8),[0,0,1])
        result=occlude_batch(batch,(0,0,10,10),0)
        self.assertEqual(result,dict(changed=2,removed=2))
        self.assertEqual(len(batch['cls']),1)
        self.assertEqual(batch['batch_idx'].item(),1)
        self.assertEqual(batch['masks'].sum(),100)

    def test_half_resolution_mask_uses_image_rectangle_scale(self):
        batch=self.batch(torch.ones((1,10,10),dtype=torch.uint8),[0],image_size=20)
        occlude_batch(batch,(0,0,10,20),0)
        self.assertEqual(batch['masks'].sum(),50)
        self.assertTrue(torch.allclose(batch['bboxes'][0],torch.tensor([.75,.5,.5,1.])))


if __name__=='__main__':unittest.main()
