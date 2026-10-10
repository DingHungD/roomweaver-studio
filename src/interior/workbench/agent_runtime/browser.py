"""Dedicated, non-persistent Playwright browser with a bounded synthetic test surface."""
from pathlib import Path
from playwright.async_api import async_playwright

PAGE = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>Studio capability test</title>
<style>body{font:24px sans-serif;padding:60px;background:#f1efe8;color:#224b42}button{font:24px sans-serif;padding:20px;margin-top:30px}</style>
<h1>室內工作室 · 工具測試</h1><p>僅供驗證瀏覽器操作的合成頁</p>
<button id="confirm" onclick="document.querySelector('#status').textContent='已確認材質';this.disabled=true">確認材質</button>
<p id="status">尚未確認</p></html>'''

class BrowserExecutor:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.page=None
        self.counter=0

    async def start(self):
        if self.page is None:
            self.playwright=await async_playwright().start()
            self.browser=await self.playwright.chromium.launch(headless=True)
            self.context=await self.browser.new_context(viewport={'width':1000,'height':700},accept_downloads=False)
            # First release exposes only this fixture. No network or personal browser profile.
            await self.context.route('**/*',lambda route:route.abort())
            self.page=await self.context.new_page()
            self.page.set_default_timeout(10000)
            await self.page.set_content(PAGE)

    async def snapshot(self):
        await self.start()
        self.counter+=1
        path=self.directory/f'browser-{self.counter:03d}.png'
        await self.page.screenshot(path=str(path))
        return dict(screenshot=str(path),status=await self.page.locator('#status').inner_text(),
            button=await self.page.locator('button').bounding_box(),disabled=await self.page.locator('button').is_disabled())

    async def click(self,x,y):
        await self.start()
        if not 0<=x<=1000 or not 0<=y<=700:
            raise ValueError('點選位置超出視窗')
        await self.page.mouse.click(x,y)
        return await self.snapshot()

    async def close(self):
        if self.page is not None:
            await self.context.close()
            await self.browser.close()
            await self.playwright.stop()
