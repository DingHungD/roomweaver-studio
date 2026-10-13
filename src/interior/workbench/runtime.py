"""Local machine settings stored in the selected workspace, never in design revisions."""
import os
from pathlib import Path
from .storage import read_json, write_json


def configure_blender(workspace, explicit=None):
    path=Path(workspace).resolve()/'artifacts/workbench/local/runtime.json'
    settings=read_json(path) if path.exists() else {}
    chosen=explicit or os.environ.get('INTERIOR_BLENDER') or settings.get('blender')
    if not chosen:
        return
    executable=Path(chosen).expanduser().resolve()
    if not executable.is_file():
        raise ValueError(f'Blender 路徑不存在：{executable}。請以 --blender 指定新的執行檔路徑')
    os.environ['INTERIOR_BLENDER']=str(executable)
    if explicit:
        write_json(path,dict(settings,blender=str(executable)))
