"""Configure an explicitly selected local segmentation runtime; no model downloads."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--python',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--enable',action='store_true')
    args=parser.parse_args()
    if not args.workspace.is_dir() or not args.python.is_file() or not args.checkpoint.is_file():
        raise ValueError('Workspace, local Python and checkpoint must already exist')
    path=args.workspace/'object-recognition.json'
    config=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if path.exists():shutil.copy2(path,path.with_name('object-recognition.backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'))
    config.update(enabled=args.enable,workflow='agent_native_v1',python=str(args.python.resolve()),
        checkpoint=str(args.checkpoint.resolve()),checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        options=dict(imgsz=1536,tile_size=640,overlap=.25,pyramid_scales=[1.,.5],merge_policy='structural_v2'))
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(configured=str(path.resolve()),enabled=args.enable,workflow=config['workflow'])))


if __name__=='__main__':main()
