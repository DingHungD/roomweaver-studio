"""Local DWG conversion; originals and conversion evidence remain in the project."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from uuid import uuid4

from ..storage import now, read_json, write_json
from .service import digest


_converter_lock = threading.Lock()
TIMEOUT = 120


def converter_executable(state_dir):
    """Resolve explicit local settings before standard installations, never a case path."""
    runtime = Path(state_dir)/'runtime.json'
    settings = read_json(runtime) if runtime.exists() else {}
    explicit = os.environ.get('ODA_FILE_CONVERTER') or settings.get('oda')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ValueError('ODA File Converter 路徑不存在，請修正 ODA_FILE_CONVERTER 或工作區 runtime.json 的 oda 設定')
        return path.resolve()
    found = shutil.which('ODAFileConverter')
    if found:
        return Path(found).resolve()
    for variable, suffix in (('LOCALAPPDATA','Programs/ODA'),('ProgramFiles','ODA'),('ProgramFiles(x86)','ODA')):
        parent = os.environ.get(variable)
        if parent:
            paths = sorted((Path(parent)/suffix).glob('*/ODAFileConverter.exe'))
            if paths:
                return paths[-1].resolve()
    raise ValueError('找不到 ODA File Converter。請先安裝，或設定 ODA_FILE_CONVERTER 指向執行檔，再重新匯入 DWG；原始檔已保留')


def convert_dwg(studio, project, original):
    root = studio.root(project)
    source = root/original['path']
    folder = root/'runs/plan-conversion'/uuid4().hex
    output = folder/'output'
    output.mkdir(parents=True, exist_ok=False)
    readme=folder.parent/'README.md'
    if not readme.exists():
        readme.write_text('# DWG 轉檔執行\n\n所有者：本案。每次轉換保留 ODA 紀錄、輸出 DXF 與日誌；原始 DWG 在 sources/workbench。平面不可變修訂引用本處的 DXF 與其雜湊。可由原始 DWG 與相容轉檔工具重建，但不能在仍有修訂引用時當作暫存清理。轉檔不是平面確認或工程驗收。\n',encoding='utf-8')
    record = dict(status='running',created_at=now(),original=original,tool='ODA File Converter',
                  output_version='ACAD2018',output_type='DXF',audit=False,recursive=False)
    manifest = folder/'conversion.json'
    write_json(manifest,record)
    try:
        header = source.read_bytes()[:6]
        if len(header)!=6 or header[:2]!=b'AC' or not header[2:].isdigit():
            raise ValueError('DWG 檔頭無效，請選擇真正的 DWG 檔案，不能只修改副檔名')
        executable = converter_executable(studio.store.state_dir)
        record['tool_sha256'] = digest(executable)
        # The converter accepts a directory, so give it exactly one staged input.
        # Audit is disabled: this step converts formats without repairing design.
        with _converter_lock, tempfile.TemporaryDirectory(prefix='roomweaver-dwg-') as temp:
            staged = Path(temp)/'plan.dwg'
            shutil.copyfile(source,staged)
            options = {}
            if os.name=='nt':
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                options = dict(startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            result = subprocess.run([str(executable),temp,str(output),'ACAD2018','DXF','0','0','*.dwg'],
                                    capture_output=True,timeout=TIMEOUT,**options)
        (folder/'stdout.txt').write_bytes(result.stdout)
        (folder/'stderr.txt').write_bytes(result.stderr)
        record['returncode'] = result.returncode
        converted = output/'plan.dxf'
        if result.returncode or not converted.is_file() or not converted.stat().st_size:
            raise ValueError('ODA 未能產生 DXF，檔案可能損壞、受保護或含無法轉換的內容；請檢查原始 DWG')
        if converted.stat().st_size>10_000_000:
            raise ValueError('轉出的 DXF 超過目前 10 MB 上限，請先簡化圖面或拆分樓層')
        if digest(source)!=original['sha256']:
            raise ValueError('原始 DWG 在轉換期間變動，請重新匯入')
        derived = dict(name=Path(original['name']).stem+'.dxf',path=converted.relative_to(root).as_posix(),sha256=digest(converted))
        record.update(status='completed',completed_at=now(),derived=derived)
        write_json(manifest,record)
        return dict(derived,original=original,conversion=dict(tool=record['tool'],record=manifest.relative_to(root).as_posix(),output_version='ACAD2018'))
    except Exception as exc:
        if isinstance(exc,subprocess.TimeoutExpired):
            message=f'DWG 轉換超過 {TIMEOUT} 秒，已停止轉檔；請簡化圖面後重試'
        elif isinstance(exc,OSError):
            message='無法執行 ODA File Converter，請檢查安裝、執行權限與磁碟空間'
        else:
            message=str(exc)
        record.update(status='failed',error=message,completed_at=now())
        write_json(manifest,record)
        raise ValueError(message+'；原始 DWG 與轉換紀錄已保留，未更新現行平面') from exc
