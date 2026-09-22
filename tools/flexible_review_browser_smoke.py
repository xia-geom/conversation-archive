"""Real-browser checks on synthetic flexible forms; no archive or network data."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conversation_archive import snapshot_review as r
from conversation_archive.review_html import render
from conversation_archive.review_controls import validate_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--memory', action='store_true', help='Use in-memory HTML when local file navigation is restricted.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('invented_controls', Path(__file__).resolve().parents[1] / 'tests/test_review_controls.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    rows = fixture.fixture()
    case = fixture.form_case()
    case['title'] = 'Synthetic form <img src="https://invalid.example/x" onerror="window.injected=true">'
    queue, blocked, history = r.queue_from_records(rows, [case])
    for q in queue:
        q['controls'] = r._control_spec(q['case'], rows)
    body = dict(protocol=r.PROTOCOL, basis_snapshot_id='AS-invented', basis_fingerprint='invented',
        batch_size=15, questions=queue, blocked=blocked, history=history, entries=rows['entries'],
        metadata=[], source_references=[], coverage={'snapshot_entries': 4, 'conflict_cases': 0})
    session = dict(body, session_id='RS-' + r.digest(body))
    source = args.output / 'review.html'; source.write_text(render(session), encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 920}, accept_downloads=True)
        requests, errors = [], []
        page.on('request', lambda req: requests.append(req.url) if req.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        def load():
            if args.memory:
                page.goto('about:blank'); page.set_content(source.read_text(encoding='utf-8'))
            else:
                page.goto(source.resolve().as_uri())
        load()
        assert page.locator('#cards article').count() == 1
        card = page.locator('#cards article').first
        assert not card.locator('[data-field-id=date_text]').is_visible()
        card.locator('[data-field-id=outcome] select').select_option('date')
        card.locator('[data-field-id=date_text] textarea').fill('03/04/2020?')
        card.locator('[data-field-id=sources] input').first.check()
        # Save unfinished work before selecting an answer; restore must retain it.
        with page.expect_download() as pending:
            page.locator('#save').click()
        draft = args.output / 'unfinished.json'; pending.value.save_as(draft)
        saved = json.loads(draft.read_text())
        assert saved['reply']['answers'] == []
        load(); page.locator('#restore').set_input_files(draft)
        page.wait_for_function("document.getElementById('message').textContent.startsWith('Draft restored')")
        card = page.locator('#cards article').first
        assert card.locator('[data-field-id=date_text] textarea').input_value() == '03/04/2020?'
        card.locator('[aria-label^="Decision for"]').select_option('record')
        page.locator('#actor').fill('Synthetic reviewer')
        with page.expect_download() as pending:
            page.locator('#export').click()
        answer_path = args.output / 'form-answers.json'; pending.value.save_as(answer_path)
        reply = json.loads(answer_path.read_text())
        q = next(q for q in queue if q['case']['kind'] == 'form')
        validate_values(q['controls']['form'], reply['answers'][0]['values'])
        assert reply['answers'][0]['values']['date_text'] == '03/04/2020?'
        # Hiding a field removes it from submission, not from the resumable draft.
        card.locator('[data-field-id=outcome] select').select_option('unknown')
        with page.expect_download() as pending:
            page.locator('#export').click()
        hidden = args.output / 'hidden-answers.json'; pending.value.save_as(hidden)
        assert 'date_text' not in json.loads(hidden.read_text())['answers'][0]['values']
        page.locator('#kind').select_option('identity')
        card = page.locator('#cards article').first
        card.get_by_role('button', name='Add group', exact=True).click()
        card.get_by_label('Label for group 1', exact=True).fill('First Alex')
        card.get_by_label('Group for M1', exact=True).select_option('g0')
        card.get_by_label('Group for M2', exact=True).select_option('g0')
        card.get_by_role('button', name='Mark remaining references unknown', exact=True).click()
        card.locator('[aria-label^="Decision for"]').select_option('group')
        with page.expect_download() as pending:
            page.locator('#export').click()
        answers = args.output / 'group-answers.json'; pending.value.save_as(answers)
        reply = json.loads(answers.read_text())
        aq = next(a for a in reply['answers'] if a['choice'] == 'group')
        q = next(q for q in queue if q['case']['kind'] == 'identity')
        validate_values(q['controls']['form'], aq['values'])
        assert aq['values']['identity']['groups'][0]['items'] == ['M1', 'M2']
        assert aq['values']['identity']['unknown'] == ['M3', 'M4']
        with page.expect_download() as pending:
            page.locator('#save').click()
        final_draft = args.output / 'complete-draft.json'; pending.value.save_as(final_draft)
        load(); page.locator('#restore').set_input_files(final_draft)
        page.wait_for_function("document.getElementById('message').textContent.startsWith('Draft restored')")
        page.locator('#kind').select_option('identity')
        assert page.get_by_label('Group for M2', exact=True).input_value() == 'g0'
        assert page.locator('img').count() == 0 and page.evaluate('window.injected === undefined')
        page.screenshot(path=str(args.output / 'identity-desktop.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(args.output / 'identity-mobile.png'))
        assert not requests, requests
        assert not errors, errors
        browser.close()
    print(json.dumps({'status': 'passed', 'file_navigation_tested': not args.memory,
        'unfinished_draft_retained': True, 'conditional_values_checked': True,
        'group_answer_checked': True, 'remote_requests': len(requests), 'page_errors': len(errors)}))


if __name__ == '__main__':
    main()
