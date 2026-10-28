"""HTTP asset verification, explicitly separate from browser interaction and FPS."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from urllib.parse import urljoin,urlsplit
from urllib.request import urlopen


def verify_http(base):
    base=base.rstrip('/')+'/'
    def fetch(name):
        url=urljoin(base,name)
        parsed=urlsplit(url);origin=urlsplit(base)
        if (parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc) or not parsed.path.startswith(origin.path):raise ValueError('網站檔案超出檢查範圍')
        with urlopen(url,timeout=30) as response:return response.read()
    release=json.loads(fetch('release.json'));files=release['fileSha256']
    def check(item):
        name,sha=item;data=fetch(name)
        if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('HTTP 檔案雜湊不符：'+name)
        return dict(file=name,bytes=len(data),sha256=sha)
    with ThreadPoolExecutor(max_workers=4) as executor:rows=list(executor.map(check,files.items()))
    manifest=json.loads(fetch('renders/gallery.json'));navigation=json.loads(fetch('tour-navigation.json'))
    cameras={s['cameraId'] for s in manifest['scenes']}
    if cameras!=set(navigation['nodes']):raise ValueError('網站導航與拍攝點不一致')
    routes=sum(len(n.get('links',[])) for n in navigation['nodes'].values())
    class References(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            for name,value in attrs:
                if name in ('href','src') and value and not value.startswith(('#','data:','https:','http:')):self.links.append(value)
    references=References()
    for name in ('index.html','gallery.html',manifest.get('comparison')):
        if name:references.feed(fetch(name).decode('utf-8'))
    for reference in set(references.links):fetch(reference)
    return dict(passed=True,scope='HTTP content hashes and static references only',base_url=base,
                content_hash=release['contentHash'],scene_count=len(manifest['scenes']),camera_count=len(cameras),
                routes=routes,verified_files=rows,browser_interaction_checked=False,fps_measured=False)
