"""Optional local Cloudflare Pages preview QA; requires playwright + Chromium.

Run: python -m http.server 8791 -d site & python scripts/browser_smoke.py
This script uses local HTTP only and does not confirm online public deployment.
"""
from __future__ import annotations
from playwright.sync_api import sync_playwright
from pathlib import Path
import json
import os

URL=os.environ.get('ALD_SITE_LOCAL_URL','http://127.0.0.1:8791/')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'local_browser_qa'
OUT.mkdir(exist_ok=True,parents=True)

def run():
    with sync_playwright() as play:
        chromium='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None
        browser=play.chromium.launch(executable_path=chromium,headless=True,args=['--no-sandbox'])
        desktop=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
        errors=[]
        desktop.on('pageerror',lambda e:errors.append(str(e)))
        desktop.route('**/data.json',lambda route:route.fulfill(status=200,content_type='application/json',body=(ROOT/'site'/'data.json').read_text()))
        desktop.goto(URL,wait_until='load',timeout=20000)
        desktop.wait_for_selector('#recipe-output .metric-big',timeout=15000)
        base=desktop.locator('#recipe-output').inner_text()
        assert '25.05' in base,base
        desktop.locator('#max-temp').select_option('200')
        desktop.locator('#recipe-form').evaluate('(f)=>f.requestSubmit()')
        lower=desktop.locator('#recipe-output').inner_text()
        assert '25.05' in lower,lower
        desktop.locator('#max-temp').select_option('150')
        desktop.locator('#recipe-form').evaluate('(f)=>f.requestSubmit()')
        refused=desktop.locator('#recipe-output').inner_text()
        assert '추천하지' in refused or '미측정' in refused or '없습니다' in refused,refused
        desktop.locator('#max-temp').select_option('275')
        desktop.locator('#objective').select_option('gpc')
        desktop.locator('#recipe-form').evaluate('(f)=>f.requestSubmit()')
        highest=desktop.locator('#recipe-output').inner_text()
        assert '1.410' in highest,highest
        desktop.screenshot(path=str(OUT/'desktop.png'),full_page=True)
        mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
        mobile.route('**/data.json',lambda route:route.fulfill(status=200,content_type='application/json',body=(ROOT/'site'/'data.json').read_text()))
        mobile.goto(URL,wait_until='load',timeout=20000)
        mobile.wait_for_selector('#recipe-output .metric-big',timeout=15000)
        scroll=mobile.evaluate('document.documentElement.scrollWidth')
        assert scroll<=391,f'Mobile horizontal overflow: {scroll}'
        mobile.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        assert not errors,errors
        print(json.dumps({'local_html':'PASS','default_10nm':'25.05 min',
                         'max_150C':'refused','gpc_priority':'1.410 Å/cycle',
                         'mobile_width':scroll,'page_errors':errors},ensure_ascii=False))
        browser.close()

if __name__=='__main__':run()
