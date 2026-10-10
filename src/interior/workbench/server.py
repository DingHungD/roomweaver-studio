"""Loopback-only standalone Studio HTTP service."""
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .storage import Store, Conflict
from .jobs import Jobs

def error(code,message,status=422,details=None):
    return JSONResponse(status_code=status,content=dict(error=dict(code=code,message=message,details=details)))

def create_app(workspace:Path,state_dir:Path|None=None):
    workspace=Path(workspace).resolve()
    store=Store(workspace,state_dir or workspace/'artifacts/workbench/local')
    from .studio.lease import Lease
    lease=Lease(store.state_dir)
    readme=store.state_dir/'README.md'
    if not readme.exists():
        readme.write_text('# 本機工作台執行資料\n\n所有者：系統應用。jobs.sqlite3 與 jobs/ 保存工作佇列、請求、結果與失敗日誌；settings.json 僅保存非敏感模型設定。它們不是案件設計權威資料，但含可追溯執行歷史，不可在執行期間清理或任意丟棄。服務可重建索引，不能重建已清除的執行歷史。\n',encoding='utf-8')
    jobs=Jobs(store)
    token=secrets.token_urlsafe(32)
    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()
    app=FastAPI(title='Roomweaver Studio',version='0.1.0',lifespan=lifespan)
    app.state.store=store
    app.state.jobs=jobs
    app.state.session_token=token

    @app.middleware('http')
    async def local_boundary(request:Request,call_next):
        host=request.headers.get('host','')
        try:
            parsed=urlsplit('//'+host)
            allowed=parsed.hostname in ('127.0.0.1','localhost','::1') and parsed.username is None and parsed.password is None
        except ValueError:
            allowed=False
        if not allowed:
            return error('host_rejected','只接受本機工作台主機',403)
        origin=request.headers.get('origin')
        viewer='/view/' in request.url.path and request.url.path.startswith('/api/projects/') and request.method in ('GET','HEAD')
        if origin and not (viewer and origin=='null'):
            if origin not in ('http://'+host,'https://'+host):
                return error('origin_rejected','請從本機工作台頁面操作',403)
        if request.headers.get('sec-fetch-site')=='cross-site' and not viewer:
            return error('origin_rejected','不接受跨站請求',403)
        try:
            if int(request.headers.get('content-length','0'))>90_000_000:
                return error('request_too_large','請求內容超過上限',413)
        except ValueError:
            return error('invalid_length','請求長度無效')
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-workbench-token',''),token):
                return error('session_required','工作台連線已失效，請重新整理',403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request,exc):
        return error('validation_error','輸入欄位不完整或格式錯誤',422,[dict(location=list(e['loc']),message=e['msg']) for e in exc.errors()])

    @app.exception_handler(Exception)
    async def all_errors(request,exc):
        if isinstance(exc,Conflict): return error('revision_conflict',str(exc),409)
        if isinstance(exc,FileNotFoundError): return error('not_found',str(exc),404)
        if isinstance(exc,PermissionError): return error('not_allowed',str(exc),403)
        if isinstance(exc,(ValueError,TypeError,KeyError)): return error('invalid_input',str(exc),422)
        return error('internal_error','本機服務發生錯誤；請檢查執行日誌',500)

    # Register concrete types so exceptions are handled inside Starlette's normal
    # exception middleware rather than its outer server-error layer.
    for cls in (Conflict,FileNotFoundError,PermissionError,ValueError,TypeError,KeyError):
        app.add_exception_handler(cls,all_errors)

    @app.get('/api/health')
    def health(): return dict(status='ok',version='0.1.0')

    @app.get('/api/session')
    def session(): return dict(token=token)

    from .studio.api import install
    try:
        install(app,store,jobs)
    except Exception:
        jobs.close();lease.close();raise
    jobs.close_callbacks.append(lease.close)
    dist=Path(__file__).resolve().parents[1]/'workbench_web/dist'
    if dist.is_dir():
        app.mount('/',StaticFiles(directory=dist,html=True),name='studio-ui')
    else:
        @app.get('/')
        def no_ui(): return dict(status='frontend_not_built',message='Run npm ci && npm run build in frontend first.')
    return app
