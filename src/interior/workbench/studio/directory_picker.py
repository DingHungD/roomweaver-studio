"""A native folder dialog in its own GUI process, outside HTTP worker threads."""
import json
import os
import subprocess
import sys

def choose_directory():
    try:
        result=subprocess.run([sys.executable,'-X','utf8','-m',__name__],capture_output=True,text=True,encoding='utf-8',timeout=180,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise ValueError('資料夾選擇已逾時，請重新選擇') from None
    if result.returncode:raise ValueError('無法開啟本機資料夾視窗；請確認桌面環境與 Python Tk 元件可用')
    return json.loads(result.stdout).get('path')

if __name__=='__main__':
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk();root.withdraw()
    if os.name=='nt':root.attributes('-topmost',True)
    try:
        selected=filedialog.askdirectory(parent=root,title='選擇空白資料夾作為專案目錄',mustexist=True)
        print(json.dumps(dict(path=selected or None),ensure_ascii=False))
    finally:root.destroy()
