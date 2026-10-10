"""Read only the public reference URL the user attached; cache source evidence."""
import hashlib
from html.parser import HTMLParser
import ipaddress
from pathlib import Path
import socket
from urllib.parse import urlsplit,urljoin
import httpx
from ..storage import read_json,write_json,now

def validate_public_url(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise ValueError('材質參考只接受公開 HTTP/HTTPS 網址')
    addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('材質參考不可連至本機、內網或保留位址')
    return url

class Text(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.ignore=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.ignore+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.ignore=max(0,self.ignore-1)
    def handle_data(self,data):
        if not self.ignore and data.strip():self.parts.append(data.strip())

def read_reference(url,directory):
    path=Path(directory)/('reference-'+hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists():return read_json(path)
    original=url
    with httpx.Client(timeout=15,follow_redirects=False,trust_env=False) as client:
        for _ in range(5):
            validate_public_url(url)
            with client.stream('GET',url,headers={'User-Agent':'InteriorStudio/0.1 reference-reader'}) as response:
                if response.is_redirect:
                    url=urljoin(url,response.headers['location']);continue
                response.raise_for_status()
                if 'text/html' not in response.headers.get('content-type','') and 'text/plain' not in response.headers.get('content-type',''):
                    raise ValueError('請提供材質介紹頁連結；此入口不下載 ZIP 或貼圖包')
                data=b''
                for chunk in response.iter_bytes():
                    data+=chunk
                    if len(data)>2_000_000:raise ValueError('材質頁超過 2 MB 讀取上限')
                parser=Text();parser.feed(data.decode(response.encoding or 'utf-8',errors='replace'))
                result=dict(source_url=original,resolved_url=url,retrieved_at=now(),sha256=hashlib.sha256(data).hexdigest(),
                    text='\n'.join(parser.parts)[:12000],license_verified=False)
                write_json(path,result);return result
    raise ValueError('材質參考重新導向次數過多')
