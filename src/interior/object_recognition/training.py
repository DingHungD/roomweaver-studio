"""Audited CAD fine-tuning with mask-aware occlusion and fixed final checkpoint."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .tiled import sha,write


def occlude_batch(batch,rectangle,image_index):
    """Erase image AND instance masks; recompute visible boxes and drop empty targets."""
    import torch
    x,y,r,b=rectangle;batch['img'][image_index,:,y:b,x:r]=1.
    masks=batch['masks'];mh,mw=masks.shape[-2:];ih,iw=batch['img'].shape[-2:]
    mx,my,mr,mb=int(x*mw/iw),int(y*mh/ih),int(r*mw/iw),int(b*mh/ih)
    selected=batch['batch_idx'].view(-1)==image_index;changed=0
    for i in torch.where(selected)[0].tolist():
        if masks[i,my:mb,mx:mr].any():changed+=1
        masks[i,my:mb,mx:mr]=0
        yy,xx=torch.where(masks[i]>0)
        if xx.numel():
            x0,x1=xx.min().float()/mw,(xx.max().float()+1)/mw
            y0,y1=yy.min().float()/mh,(yy.max().float()+1)/mh
            batch['bboxes'][i]=torch.stack(((x0+x1)/2,(y0+y1)/2,x1-x0,y1-y0))
    keep=masks.flatten(1).sum(1)>0;removed=int((~keep).sum().item())
    for key in ('masks','bboxes','cls','batch_idx'):batch[key]=batch[key][keep]
    return dict(changed=changed,removed=removed)


def train(dataset,checkpoint,artifact,epochs=80):
    artifact=Path(artifact).resolve();dataset=Path(dataset).resolve();checkpoint=Path(checkpoint).resolve()
    if artifact.exists():raise FileExistsError('Preserve prior training artifact')
    artifact.mkdir(parents=True);started=time.time();os.environ['YOLO_CONFIG_DIR']=str(artifact/'settings')
    os.chdir(artifact)
    os.environ['YOLO_AUTOINSTALL']='false'
    import torch,ultralytics
    from ultralytics import YOLO,settings as ultra_settings
    from ultralytics.models.yolo.segment.train import SegmentationTrainer
    from ultralytics.data.augment import RandomPerspective
    ultra_settings.update({k:False for k in ('sync','clearml','comet','dvc','mlflow','raytune','tensorboard','wandb')})
    if not torch.cuda.is_available():raise ValueError('Explicit local CUDA training expected')
    original_filter=RandomPerspective.box_candidates
    def thin_filter(box1,box2,wh_thr=2,ar_thr=100,area_thr=.1,eps=1e-16):
        return original_filter(box1,box2,wh_thr=.01,ar_thr=1e6,area_thr=area_thr,eps=eps)
    RandomPerspective.box_candidates=staticmethod(thin_filter)
    audit=dict(occlusion_applied_batches=0,occlusion_changed_instances=0,removed_empty_targets=0,batches=0)
    class CadTrainer(SegmentationTrainer):
        def preprocess_batch(self,batch):
            batch=super().preprocess_batch(batch)
            if self.model.training:
                audit['batches']+=1
                if torch.rand(()).item()<.10:
                    h,w=batch['img'].shape[-2:];rw=max(2,int(w*(.04+.06*torch.rand(()).item())));rh=max(2,int(h*(.04+.06*torch.rand(()).item())))
                    x=int(torch.randint(0,w-rw+1,()).item());y=int(torch.randint(0,h-rh+1,()).item())
                    stats=occlude_batch(batch,(x,y,x+rw,y+rh),int(torch.randint(0,len(batch['img']),()).item()))
                    audit['occlusion_applied_batches']+=1;audit['occlusion_changed_instances']+=stats['changed'];audit['removed_empty_targets']+=stats['removed']
                else:
                    keep=batch['masks'].flatten(1).sum(1)>0;audit['removed_empty_targets']+=int((~keep).sum().item())
                    for key in ('masks','bboxes','cls','batch_idx'):batch[key]=batch[key][keep]
            return batch
    config=dict(data=str(dataset/'data.yaml'),epochs=epochs,imgsz=640,batch=4,nbs=4,device=0,workers=0,
       project=str(artifact),name='fit',exist_ok=False,optimizer='AdamW',lr0=.0003,lrf=.1,cos_lr=True,
       warmup_epochs=3,weight_decay=.0005,patience=0,seed=0,deterministic=True,amp=True,
       val=False,save=True,save_period=20,plots=True,mask_ratio=2,overlap_mask=False,
       mosaic=.35,close_mosaic=15,mixup=.05,copy_paste=0.,cutmix=0.,degrees=5.,translate=.05,
       scale=.25,shear=0.,perspective=0.,fliplr=.5,flipud=.5,hsv_h=0.,hsv_s=0.,hsv_v=.1)
    source_hashes={str(p):sha(p) for p in [dataset/'manifest.json',dataset/'data.yaml',checkpoint]}
    write(artifact/'training-config.json',dict(initial_checkpoint=str(checkpoint),source_hashes=source_hashes,settings=config,
        quarter_turn_rotations=[0,90,180,270],mask_aware_occlusion=dict(probability=.10,side_fraction=[.04,.10],image_and_masks_updated=True),
        selection='fixed_final_epoch_last.pt',independent_validation=False,project08_used_for_training=False))
    write(artifact/'environment.json',dict(python=sys.version,torch=torch.__version__,ultralytics=ultralytics.__version__,gpu=torch.cuda.get_device_name(0)))
    (artifact/'requirements-freeze.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf-8')
    write(artifact/'status.json',dict(status='training',epochs=epochs))
    try:
        model=YOLO(str(checkpoint))
        def progress(trainer):
            losses=trainer.loss_items
            losses={k:float(v.detach().cpu().mean()) for k,v in losses.items()} if isinstance(losses,dict) else [float(v) for v in losses.detach().cpu().tolist()]
            value=dict(status='training',epoch=trainer.epoch+1,total_epochs=epochs,losses=losses,elapsed_seconds=time.time()-started,augmentation=audit.copy())
            write(artifact/'progress.json',value)
            if (trainer.epoch+1)%5==0:print(json.dumps(value),flush=True)
        model.add_callback('on_train_epoch_end',progress)
        model.train(trainer=CadTrainer,**config)
        last=artifact/'fit/weights/last.pt'
        if not all(sha(p)==h for p,h in source_hashes.items()):raise ValueError('Training source changed')
        result=dict(status='trained',epochs=epochs,checkpoint='fit/weights/last.pt',checkpoint_sha256=sha(last),
                    elapsed_seconds=time.time()-started,source_inputs_unchanged=True,independent_validation=False,model_deployed=False,augmentation=audit)
        write(artifact/'status.json',result);return result
    except Exception as exc:
        write(artifact/'status.json',dict(status='failed',error=str(exc),augmentation=audit,elapsed_seconds=time.time()-started));raise
    finally:RandomPerspective.box_candidates=staticmethod(original_filter)
