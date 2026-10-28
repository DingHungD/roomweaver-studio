"""Bounded local converter process shared by UI jobs and the CLI."""
import os
from pathlib import Path
import subprocess
import sys

from ..storage import read_json,write_json
from .service import digest

TIMEOUT=1800


def convert_skp(source,folder):
    source,folder=Path(source).resolve(),Path(folder).resolve()
    if folder.exists(): raise ValueError('轉檔輸出目錄已存在，請使用新的執行目錄')
    original=digest(source)
    log=folder.parent/(folder.name+'.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('xb') as stream:
        try:
            result=subprocess.run([sys.executable,'-u','-m','interior.visualization.sketchup',str(source),str(folder)],
                                  stdout=stream,stderr=subprocess.STDOUT,timeout=TIMEOUT,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as exc:
            path=folder/'conversion.json'
            record=read_json(path) if path.exists() else {}
            record.update(status='failed',error=f'SKP 轉換超過 {TIMEOUT} 秒，已停止；原件保留')
            write_json(path,record)
            raise ValueError(record['error']) from exc
    path=folder/'conversion.json'
    report=read_json(path) if path.exists() else {}
    if result.returncode or report.get('status')!='completed':
        raise ValueError('SKP 轉檔失敗：'+report.get('error','請查看轉檔日誌')+'；原始檔與轉換紀錄已保留')
    if report['source']['sha256']!=original or digest(source)!=original:
        raise ValueError('原始 SKP 在轉檔期間變動')
    if digest(folder/'model.glb')!=report['derived']['sha256']: raise ValueError('轉檔 GLB 雜湊不符')
    return report
