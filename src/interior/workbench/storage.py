"""Workspace registration and immutable upload storage for the standalone Studio."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import os
import re
import threading
from interior.projects import Project


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


class Store:
    def __init__(self, workspace, state_dir):
        self.workspace = Path(workspace).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def projects(self):
        items = []
        for path in sorted((self.workspace/'projects').glob('*/project.json')):
            if not path.resolve().is_relative_to((self.workspace/'projects').resolve()):
                continue
            data = read_json(path)
            items.append({k: data.get(k) for k in ('id', 'name', 'kind')})
        return items

    def project(self, identifier):
        roots = []
        for path in (self.workspace/'projects').glob('*/project.json'):
            if path.resolve().is_relative_to((self.workspace/'projects').resolve()) and read_json(path).get('id') == identifier:
                roots.append(path.parent)
        if len(roots) != 1:
            raise FileNotFoundError('找不到唯一的已登記案件')
        return Project.open(roots[0])

    def create_project(self, data):
        identifier = data['id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', identifier):
            raise ValueError('案件 ID 只允許英文、數字、底線與連字號')
        # Also reject Windows device names for portable workspaces.
        if re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])', identifier):
            raise ValueError('案件 ID 是保留名稱')
        with self.lock:
            if any(p['id'].casefold() == identifier.casefold() for p in self.projects()):
                raise Conflict('案件 ID 已存在')
            root = self.workspace/'projects'/identifier.lower()
            root.mkdir(parents=True, exist_ok=False)
            metadata = dict(id=identifier, name=data['name'], kind=data.get('kind','user'), entries={})
            write_json(root/'project.json', metadata)
            (root/'README.md').write_text(f"# {data['name']}\n\nOwner: {identifier}. Awaiting GLB import.\n\nOriginal uploads: sources/workbench/. Immutable scene revisions: workflows/interior-studio/.\nBlender jobs and images: runs/interior-studio/. Keep these together with the workspace databases.\n", encoding='utf-8')
            return metadata

    def upload(self, identifier, name, content):
        name = Path(name.replace('\\','/')).name
        if not name or name in ('.','..') or ':' in name:
            raise ValueError('收件檔名無效')
        project = self.project(identifier)
        path = project.path('sources/workbench/'+uuid4().hex+'/'+name)
        path.parent.mkdir(parents=True, exist_ok=False)
        path.write_bytes(content)
        return dict(name=name,path=path.relative_to(project.root).as_posix())
