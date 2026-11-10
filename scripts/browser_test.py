"""Real Chromium end-to-end checks against an isolated, temporary Waitress server."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from waitress import create_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results'
OUT.mkdir(exist_ok=True)
if os.name == 'nt' and 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.runtime' / 'browsers')


def main():
    checks = []
    errors = []
    with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as folder:
        app = create_app({'DATABASE':str(Path(folder)/'browser.sqlite3'), 'SECRET_KEY':'browser-test-only'})
        server = create_server(app, host='127.0.0.1', port=0, threads=4)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.effective_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, channel=os.environ.get('BROWSER_CHANNEL'))
                context = browser.new_context(viewport={'width':1440,'height':1050}, accept_downloads=True)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: errors.append(message.text) if message.type=='error' else None)
                page.on('dialog', lambda dialog: dialog.accept())
                try:
                    page.goto(url)
                    expect(page.get_by_role('heading',name='Welcome back.')).to_be_visible()
                    page.get_by_role('link',name='Create an account').click()
                    page.get_by_label('Username',exact=True).fill('Browser_User')
                    page.get_by_label('Email address',exact=True).fill('browser@example.com')
                    page.get_by_label('Password',exact=True).fill('browser-password-123')
                    page.get_by_label('Confirm password',exact=True).fill('browser-password-123')
                    page.get_by_role('button',name='Create account',exact=True).click()
                    expect(page.get_by_role('heading',name='Welcome back.')).to_be_visible()
                    page.get_by_label('Username or email').fill('Browser_User')
                    page.get_by_label('Password',exact=True).fill('browser-password-123')
                    page.get_by_label('Remember me for 30 days').check()
                    page.get_by_role('button',name='Sign in',exact=True).click()
                    expect(page.get_by_role('heading',name='Hello, Browser_User .')).to_be_visible()
                    checks.append('Registration, login, and dashboard')
                    page.get_by_role('link',name='New dataset',exact=True).click()
                    page.get_by_label('Dataset name').fill('Experiment 01')
                    page.get_by_label('Short description').fill('Reference experiment')
                    page.get_by_label('Numerical observations').fill('10, 20, 30, 40, 50')
                    expect(page.locator('#livePreview')).to_contain_text('30')
                    page.get_by_role('button',name='Save & analyze').click()
                    expect(page.locator('[data-result="mean"]').first).to_have_text('30')
                    expect(page.locator('[data-result="population_variance"]')).to_have_text('200')
                    expect(page.locator('[data-result="sample_variance"]')).to_have_text('250')
                    expect(page.locator('[data-result="population_std"]').first).to_have_text('14.1421')
                    checks.append('Dataset entry, live preview, reference statistics')
                    expect(page.locator('#resultChart .main-svg').first).to_be_visible()
                    for chart in ('box','line','bar','frequency','cumulative','histogram'):
                        page.get_by_label('Chart type').select_option(chart)
                        expect(page.locator('#resultChart .main-svg').first).to_be_visible()
                    page.screenshot(path=str(OUT/'results-desktop.png'),full_page=True)
                    checks.append('Histogram, box, line, bar, frequency, cumulative charts')
                    page.get_by_role('button',name='Save analysis',exact=True).click()
                    page.get_by_label('Analysis name',exact=True).fill('Experiment 01 report')
                    page.locator('#modal').get_by_role('button',name='Save analysis',exact=True).click()
                    expect(page.get_by_role('link',name='PDF report')).to_be_visible()
                    analysis_hash = page.url.split('#')[1]
                    page.get_by_role('button',name='Add custom parameter').click()
                    page.get_by_label('Parameter name').fill('Experimental Error')
                    page.get_by_label('Value',exact=True).fill('2.5')
                    page.get_by_label('Unit (optional)').fill('%')
                    page.get_by_role('button',name='Save parameter',exact=True).click()
                    expect(page.locator('#parameterList')).to_contain_text('2.5')
                    page.get_by_role('button',name='Edit Experimental Error').click()
                    page.get_by_label('Value',exact=True).fill('3.5')
                    page.get_by_role('button',name='Save parameter',exact=True).click()
                    expect(page.locator('#parameterList')).to_contain_text('3.5')
                    checks.append('Saved analysis and custom parameter create/edit')
                    page.get_by_role('button',name='Sign out').first.click()
                    expect(page.get_by_role('heading',name='Welcome back.')).to_be_visible()
                    page.get_by_label('Username or email').fill('Browser_User')
                    page.get_by_label('Password',exact=True).fill('browser-password-123')
                    page.get_by_role('button',name='Sign in',exact=True).click()
                    expect(page.get_by_role('heading',name='Hello, Browser_User .')).to_be_visible()
                    page.goto(url+'/#'+analysis_hash)
                    expect(page.locator('#parameterList')).to_contain_text('3.5')
                    page.reload()
                    expect(page.locator('[data-result="mean"]').first).to_have_text('30')
                    checks.append('Logout, login, and reload recover saved work')
                    page.get_by_role('link',name='New calculation').click()
                    page.get_by_role('link',name='Edit data').click()
                    page.locator('input[data-row="4"][data-col="0"]').fill('100')
                    page.get_by_role('button',name='Save & analyze').click()
                    expect(page.locator('[data-result="mean"]').first).to_have_text('40')
                    expect(page.locator('#parameterList')).to_contain_text('3.5')
                    page.goto(url+'/#'+analysis_hash)
                    expect(page.locator('.notice')).to_contain_text('Historical analysis')
                    expect(page.locator('[data-result="mean"]').first).to_have_text('30')
                    checks.append('Recalculation preserves manual values and historical results')
                    for name, filename in [('PDF report','report.pdf'),('Statistics CSV','statistics.csv')]:
                        with page.expect_download() as download:
                            page.get_by_role('link',name=name,exact=True).click()
                        download.value.save_as(str(OUT/filename))
                    checks.append('PDF and CSV report downloads')
                    page.goto(url+'/#new')
                    page.get_by_role('button',name='CSV import',exact=True).click()
                    page.get_by_label('Choose CSV file').set_input_files({'name':'paired.csv','mimeType':'text/csv','buffer':b'X,Y\n1,3\n2,5\n3,7\n4,9\n'})
                    page.get_by_role('button',name='Preview CSV',exact=True).click()
                    expect(page.locator('.sheet')).to_be_visible()
                    page.get_by_role('button',name='Save dataset',exact=True).click()
                    expect(page.get_by_role('heading',name='My datasets',exact=True)).to_be_visible()
                    page.get_by_role('link',name='Analyze dataset').filter(has_text='Analyze').nth(0).click()
                    page.get_by_text('Paired & weighted analysis',exact=True).click()
                    page.get_by_label('Second numerical column (Y)').select_option('1')
                    page.get_by_role('button',name='Calculate statistics').click()
                    expect(page.locator('[data-result="pearson"]')).to_have_text('1')
                    page.get_by_label('Chart type').select_option('scatter')
                    expect(page.locator('#resultChart .main-svg').first).to_be_visible()
                    checks.append('CSV import, column selection, paired correlation and scatter chart')
                    page.goto(url+'/#compare')
                    page.locator('[name=compare]').nth(0).check()
                    page.locator('[name=compare]').nth(1).check()
                    page.get_by_role('button',name='Compare datasets',exact=True).click()
                    expect(page.get_by_role('heading',name='Comparison results')).to_be_visible()
                    checks.append('Multiple-dataset comparison')
                    page.goto(url+'/#dashboard')
                    expect(page.get_by_role('heading',name='Hello, Browser_User .')).to_be_visible()
                    page.screenshot(path=str(OUT/'dashboard-desktop.png'),full_page=True)
                    page.get_by_role('button',name='Toggle light or dark theme').click()
                    page.screenshot(path=str(OUT/'dashboard-dark.png'),full_page=True)
                    page.get_by_role('button',name='Toggle light or dark theme').click()
                    mobile = browser.new_context(viewport={'width':390,'height':844},storage_state=context.storage_state())
                    mobile_page=mobile.new_page()
                    mobile_page.goto(url+'/#dashboard')
                    expect(mobile_page.get_by_role('heading',name='Hello, Browser_User .')).to_be_visible()
                    assert mobile_page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflows horizontally'
                    mobile_page.screenshot(path=str(OUT/'dashboard-mobile.png'),full_page=True)
                    mobile_page.goto(url+'/#'+analysis_hash)
                    expect(mobile_page.locator('[data-result="mean"]').first).to_have_text('30')
                    assert mobile_page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile results overflow horizontally'
                    mobile_page.screenshot(path=str(OUT/'results-mobile.png'),full_page=True)
                    mobile.close()
                    checks.append('Desktop, dark theme, mobile dashboard and results without overflow')
                    if errors:
                        raise AssertionError('Browser errors: '+str(errors))
                except Exception:
                    page.screenshot(path=str(OUT/'failure.png'),full_page=True)
                    raise
                finally:
                    browser.close()
        finally:
            server.task_dispatcher.shutdown()
            server.close()
        report={'passed':len(checks),'checks':checks,'browser_errors':errors}
        (OUT/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
