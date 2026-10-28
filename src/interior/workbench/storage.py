"""Workspace registration and immutable upload storage for the standalone Studio."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import os
import re
import threading
import time
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
    try:
        for attempt in range(6):
            try:
                os.replace(temp, path)
                break
            except PermissionError as exc:
                # Windows readers/virus scanners can briefly deny atomic rename.
                # Keep atomicity and never reinterpret permanent failures as success.
                if getattr(exc,'winerror',None) not in (5,32) or attempt==5:raise
                time.sleep(.01*2**attempt)
    finally:
        if temp.exists():temp.unlink()


class Store:
    def __init__(self, workspace, state_dir):
        self.workspace = Path(workspace).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def projects(self, include_archived=False):
        items = []
        for identifier,root in self.project_roots().items():
            path=root/'project.json'
            if not path.is_file():continue
            data = read_json(path)
            if data.get('id')!=identifier:raise Conflict('專案登記與資料夾內的 ID 不符')
            if data.get('studio_archived') and not include_archived:
                continue
            items.append({k: data.get(k) for k in ('id', 'name', 'kind')})
        return items

    def project(self, identifier):
        roots=self.project_roots()
        if identifier not in roots:raise FileNotFoundError('找不到唯一的已登記案件')
        root=roots[identifier]
        if root.resolve()!=root:raise ValueError('專案目錄已重新導向，請重新核對專案資料夾')
        project=Project.open(root)
        if project.metadata.get('id')!=identifier:raise Conflict('專案登記與資料夾內的 ID 不符')
        return project

    def project_roots(self):
        roots={}
        for path in (self.workspace/'projects').glob('*/project.json'):
            if path.resolve().is_relative_to((self.workspace/'projects').resolve()):
                identifier=read_json(path).get('id')
                if identifier in roots:raise Conflict('專案 ID 重複')
                roots[identifier]=path.parent.resolve()
        registry=self.state_dir/'project-library/registry.json'
        for item in read_json(registry).get('projects',[]) if registry.exists() else []:
            root=Path(item['root'])
            if not root.is_absolute():raise ValueError('專案目錄已重新導向或格式無效')
            identifier=item['id']
            if identifier in roots and roots[identifier]!=root:raise Conflict('專案 ID 對應多個資料夾')
            roots[identifier]=root
        return roots

    @staticmethod
    def initialize_project(root,metadata):
        write_json(root/'project.json',metadata)
        (root/'README.md').write_text(f"# {metadata['name']}\n\nOwner: {metadata['id']}. This directory is the project root.\n\n- project.json: portable identity and relative entry points.\n- sources/workbench/: immutable input batches; sources/example/: copied teaching assets.\n- workflows/: plan interpretation, scene revisions, settings and saved navigation.\n- runs/interior-studio/: working BLEND/GLB pairs, renders, thumbnails and verification.\n- deliverables/: explicitly packaged final delivery, when requested; ordinary render output remains in runs/.\n\nFolders are created when used. Keep sources, workflows and runs together. The application workspace holds the shared job/checkpoint databases and the local project registry; back up both the project directory and application state. This README and project.json cannot reconstruct deleted sources or models.\n",encoding='utf-8')

    def create_project(self, data):
        identifier = data['id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', identifier):
            raise ValueError('案件 ID 只允許英文、數字、底線與連字號')
        # Also reject Windows device names for portable workspaces.
        if re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])', identifier):
            raise ValueError('案件 ID 是保留名稱')
        with self.lock:
            if any(key.casefold() == identifier.casefold() for key in self.project_roots()):
                raise Conflict('案件 ID 已存在')
            root = self.workspace/'projects'/identifier.lower()
            root.mkdir(parents=True, exist_ok=False)
            metadata = dict(id=identifier, name=data['name'], kind=data.get('kind','user'), entries={})
            self.initialize_project(root,metadata)
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
