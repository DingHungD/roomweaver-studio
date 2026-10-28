"""Local pixel-only segmentation CLI, usable by an Agent or the Studio host."""
import argparse
import json
from pathlib import Path

from .tiled import infer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--options',help='JSON file containing inference options only')
    args=parser.parse_args()
    options=json.loads(Path(args.options).read_text(encoding='utf-8')) if args.options else None
    print(json.dumps(infer(args.image,args.checkpoint,args.output,options),ensure_ascii=False))


if __name__=='__main__':
    main()
