"""Exercise the offline reviewer with invented data and a real Chromium browser."""
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conversation_archive.review_html import render
from conversation_archive.snapshot_review import PROTOCOL, CORE_TABLES, queue_from_records, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--memory', action='store_true', help='Load synthetic HTML in memory when file navigation is restricted.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = {table: [] for table in CORE_TABLES}
    for number, text in enumerate(('Invented quantity: 4.\n', 'Invented quantity: 7.\n'), 1):
        records['entries'].append(dict(entry_id=f'E{number:04}', title=f'Invented source {number}',
                                       raw_markdown=text))
    evidence = [dict(entry_id=e['entry_id'], start=0, end=len(e['raw_markdown']), quote=e['raw_markdown'])
                for e in records['entries']]
    cases = [dict(kind='conflict', title=f'Invented case {i}', prompt='Do these source passages disagree?',
                  reason='Synthetic interface example, not a medical record.', evidence=evidence, depends_on=[])
             for i in range(17)]
    cases[0]['title'] = '</script><img src="https://invalid.example/x" onerror="window.injected=true">'
    queue, blocked, history = queue_from_records(records, cases)
    body = dict(protocol=PROTOCOL, basis_snapshot_id='AS-invented', basis_fingerprint='invented', batch_size=15,
                questions=queue, blocked=blocked, history=history, entries=records['entries'], metadata=[],
                source_references=[], coverage={'snapshot_entries': 2, 'conflict_cases': 17})
    session = dict(body, session_id='RS-'+digest(body))
    html = args.output/'review.html'; html.write_text(render(session), encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 920}, accept_downloads=True)
        remote = []
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: remote.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        if args.memory:
            page.set_content(html.read_text(encoding="utf-8"))
        else:
            page.goto(html.resolve().as_uri())
        assert page.locator('#cards article').count() == 15
        assert 'of 17' in page.locator('#page-status').inner_text()
        page.locator('#next').click(); assert page.locator('#cards article').count() == 2
        page.locator('#previous').click()
        first = page.locator('#cards article').first
        first.locator('select').select_option('disagree')
        first.locator('textarea').fill('Invented review note, not a diagnosis.')
        page.locator('#actor').fill('Synthetic reviewer')
        with page.expect_download() as download:
            page.locator('#save').click()
        draft = args.output/'draft.json'; download.value.save_as(draft)
        if args.memory:
            page.goto('about:blank')
            page.set_content(html.read_text(encoding='utf-8'))
        else:
            page.reload()
        assert '0 explicit' in page.locator('#draft-count').inner_text()
        page.locator('#restore').set_input_files(draft)
        page.wait_for_function("document.getElementById('draft-count').textContent.startsWith('1 explicit')")
        with page.expect_download() as download:
            page.locator('#export').click()
        answers = args.output/'answers.json'; download.value.save_as(answers)
        result = json.loads(answers.read_text())
        assert result['session_id'] == session['session_id']
        assert result['answers'][0]['choice'] == 'disagree'
        assert result['answers'][0]['previous_rule_id'] is None
        page.locator('#search').fill('no matching case')
        assert page.locator('#cards article').count() == 0
        page.locator('#search').fill('')
        assert page.locator('img').count() == 0
        assert page.evaluate('window.injected === undefined')
        page.screenshot(path=str(args.output/'review-desktop.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(args.output/'review-mobile.png'))
        assert not remote, remote
        assert not errors, errors
        browser.close()
    print(json.dumps({'status': 'passed', 'remote_requests': len(remote), 'page_errors': len(errors),
                      'pagination': True, 'draft_round_trip': True, 'answer_export': True,
                      'hostile_text_inert': True, 'mobile_overflow': False, 'file_navigation_tested': not args.memory}))


if __name__ == '__main__':
    main()
