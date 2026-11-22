"""Offline JS/HTML browser smoke test using an inlined static document.

No live HTTP access is needed. Does not confirm Cloudflare deployment.
Requires playwright + a locally installed Chromium binary.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'


def assembled_html(data_override=None):
    """Embed tested production JS and data into an about:blank page to avoid network."""
    html = (SITE/'index.html').read_text(encoding='utf-8')
    style = (SITE/'styles.css').read_text(encoding='utf-8')
    config = (SITE/'config.js').read_text(encoding='utf-8')
    script = (SITE/'main.js').read_text(encoding='utf-8')
    data = (json.loads((SITE/'data.json').read_text(encoding='utf-8'))
            if data_override is None else data_override)
    fetch_stub = ('window.fetch=async function(){return {ok:true,json:async()=>'
                  + '(' + json.dumps(data, ensure_ascii=False) + ') };};')
    html=html.replace('<link rel="stylesheet" href="styles.css" />','<style>'+style+'</style>')
    html=html.replace('<script src="config.js" defer></script>','<script>'+fetch_stub+'\n'+config+'</script>')
    html=html.replace('<script src="main.js" defer></script>','<script>'+script+'</script>')
    return html


def run():
    with sync_playwright() as p:
        exe = '/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None
        browser = p.chromium.launch(executable_path=exe, headless=True,
                                    args=['--no-sandbox','--disable-dev-shm-usage'])
        failures=[]
        html=assembled_html()
        try:
            for width,height in [(1440,900),(390,844)]:
                page=browser.new_page(viewport={'width':width,'height':height})
                page.on('pageerror',lambda e:failures.append(str(e)))
                page.set_content(html,wait_until='load',timeout=15000)
                page.locator('#recipe-output .metric-big').wait_for(timeout=15000)
                assert '25.05' in page.locator('#recipe-output').inner_text()
                page.locator('#max-temp').select_option('200')
                page.locator('#recipe-form').evaluate('(form) => form.requestSubmit()')
                assert '25.05' in page.locator('#recipe-output').inner_text()
                page.locator('#max-temp').select_option('150')
                page.locator('#recipe-form').evaluate('(form) => form.requestSubmit()')
                assert '실측 레시피가 없습니다' in page.locator('#recipe-output').inner_text()
                page.locator('#max-temp').select_option('275')
                page.locator('#objective').select_option('gpc')
                page.locator('#recipe-form').evaluate('(form) => form.requestSubmit()')
                assert '1.410' in page.locator('#recipe-output').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1
                assert not failures,failures
                print(f'PASS offline mocked browser {width}x{height}: form, refusal, GPC, no horizontal overflow')
                page.close()
            # A corrupted but plausible-looking payload must NOT produce a
            # number on the page, even if the browser fetch itself succeeded.
            corrupted = json.loads((SITE/'data.json').read_text(encoding='utf-8'))
            corrupted['recipes'][0]['gpc_mean_A'] = 999
            page = browser.new_page(viewport={'width':390,'height':844})
            page.set_content(assembled_html(corrupted), wait_until='load', timeout=15000)
            assert page.locator('#model-status').inner_text() == '데이터 오류'
            assert '무결성 검사에 실패' in page.locator('#recipe-output').inner_text()
            assert page.locator('#recipe-output .metric-big').count() == 0
            print('PASS offline mocked browser: tampered data refuses to display a recipe')
            page.close()
        finally:
            browser.close()

if __name__=='__main__':run()
