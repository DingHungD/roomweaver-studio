"""Project registration, explicit path ownership and portable entry points."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Project:
    root: Path
    metadata: dict

    @classmethod
    def open(cls, directory):
        root = Path(directory).resolve()
        metadata = json.loads((root / 'project.json').read_text(encoding='utf-8'))
        if not metadata.get('id'):
            raise ValueError('Project registration requires id')
        return cls(root, metadata)

    @property
    def workspace(self):
        return self.root.parent.parent

    def path(self, value, *, shared=False):
        """Relative paths are project-relative; other projects are never accepted."""
        path = (self.root / value).resolve()
        allowed = [self.root]
        if shared:
            allowed.append(self.workspace / 'shared')
        if not any(path.is_relative_to(p.resolve()) for p in allowed):
            raise ValueError('Path does not belong to project or allowed shared resources: ' + str(path))
        return path

    def entry(self, name):
        return self.path(self.metadata['entries'][name])


def list_projects(workspace):
    result = []
    for entry in sorted((Path(workspace).resolve() / 'projects').glob('*/project.json')):
        project = Project.open(entry.parent)
        result.append({**project.metadata, 'root': str(project.root)})
    return result
