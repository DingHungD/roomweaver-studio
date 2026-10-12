"""Quiesced SQLite backups plus authoritative revisions; no cross-database transaction."""
from datetime import datetime, timezone
import shutil
import sqlite3
from pathlib import Path
from ..storage import write_json,read_json
from .service import digest

def create_backup(studio,coordinator):
    with coordinator.lock,studio.store.lock,studio.jobs.lock:
        if any(j['status'] in ('queued','running') for j in studio.jobs.list()):
            raise ValueError('請先等待工作完成，再備份兩個資料庫')
        root=studio.store.state_dir/'backups'
        output=root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output.mkdir(parents=True)
        for name in ('jobs.sqlite3','agent-checkpoints.sqlite3'):
            source=sqlite3.connect(studio.store.state_dir/name)
            target=sqlite3.connect(output/name)
            try:
                source.backup(target)
            finally:
                source.close();target.close()
        projects=[]
        for project in studio.store.projects():
            folder=studio.folder(project['id'])
            parts=[]
            for name in ('interior-studio','plan-import'):
                source=folder.parent/name
                if source.exists():
                    shutil.copytree(source,output/'projects'/project['id']/name)
                    parts.append(name)
            if parts:projects.append(dict(id=project['id'],revision=studio.current(project['id'])['revision'],parts=parts))
        hashes={p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file()}
        write_json(output/'manifest.json',dict(projects=projects,sha256=hashes,large_files='Case runs and sources require separate backup',format=2))
        # Only timestamp folders created here are eligible, never upgrade snapshots.
        snapshots=sorted(p for p in root.iterdir() if p.is_dir() and len(p.name)==22 and p.name.endswith('Z'))
        for old in snapshots[:-7]:
            resolved=old.resolve()
            if resolved.parent==root.resolve():
                shutil.rmtree(resolved)
        return dict(path=str(output),projects=projects)

def restore_backup(store,backup):
    """Restore with service stopped, preserving current DB/config files in a recovery snapshot."""
    from .lease import Lease
    lease=Lease(store.state_dir)
    try:
        root=Path(backup).resolve()
        manifest=read_json(root/'manifest.json')
        if manifest.get('format') not in (1,2) or not manifest.get('sha256'):
            raise ValueError('備份格式不符或缺少完整性清單')
        for name,expected in manifest['sha256'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or digest(path)!=expected:
                raise ValueError('備份完整性核對失敗：'+name)
        for name in ('jobs.sqlite3','agent-checkpoints.sqlite3'):
            if name not in manifest['sha256']:raise ValueError('備份缺少資料庫')
            db=sqlite3.connect(root/name)
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite 完整性檢查失敗')
            finally:db.close()
        targets=[]
        for item in manifest['projects']:
            # Resolve through registered cases; backup input cannot choose arbitrary destinations.
            project=store.project(item['id'])
            parts=item.get('parts',[]) if manifest['format']==2 else ['interior-studio']
            if not parts or any(part not in ('interior-studio','plan-import') for part in parts):raise ValueError('案件備份種類無效')
            for part in parts:
                source=root/'projects'/item['id']
                if manifest['format']==2:source=source/part
                if not source.resolve().is_relative_to(root) or not source.is_dir():raise ValueError('案件備份缺失')
                targets.append((source,project.root/'workflows'/part))
        safety=store.state_dir/'backups'/('pre-restore-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        safety.mkdir(parents=True)
        for name in ('jobs.sqlite3','agent-checkpoints.sqlite3'):
            destination=store.state_dir/name
            if destination.exists():
                old=sqlite3.connect(destination);saved=sqlite3.connect(safety/name)
                try:old.backup(saved)
                finally:old.close();saved.close()
            # SQLite backup updates the DB safely, including existing WAL state.
            source=sqlite3.connect(root/name);target=sqlite3.connect(destination)
            try:source.backup(target)
            finally:source.close();target.close()
        for source,target in targets:
            if target.exists():shutil.copytree(target,safety/'projects'/target.parents[1].name/target.name)
            # Keep newer immutable revisions; only restore the selected current pointer and settings.
            shutil.copytree(source,target,dirs_exist_ok=True)
        return dict(status='restored',safety_snapshot=str(safety),automatic_jobs_submitted=0)
    finally:lease.close()

if __name__=='__main__':
    import argparse
    from ..storage import Store
    parser=argparse.ArgumentParser(description='Restore Studio backup while the service is stopped')
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--restore',type=Path,required=True)
    args=parser.parse_args()
    print(restore_backup(Store(args.workspace,args.workspace/'artifacts/workbench/local'),args.restore))
