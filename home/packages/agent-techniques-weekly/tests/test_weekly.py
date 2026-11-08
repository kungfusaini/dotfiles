import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('weekly', Path(__file__).parents[1] / 'weekly.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = dt.datetime(2026, 11, 8, 10, tzinfo=w.UTC)


def feed(ids=('abc123',), date='2026-11-07T12:00:00Z', comments=False):
    entries = ''.join(f'<entry><id>{"t1_" if comments else "t3_"}{pid}</id><title>Built a workflow {pid}</title>'
                      f'<published>{date}</published><link href="{w.BASE}comments/{pid}/"/>'
                      '<content type="html">&lt;p&gt;A concrete approach&lt;/p&gt;</content></entry>' for pid in ids)
    home = w.BASE + ('comments/' + ids[0] + '/' if comments else '')
    return (f'<feed xmlns="http://www.w3.org/2005/Atom"><link rel="alternate" href="{home}"/>' + entries + '</feed>').encode()


def good(config, packet):
    return {'ideas': [{'title': 'A technique', 'problem': 'A problem', 'approach': 'An approach',
                      'caveats': 'Source report, not tested', 'source_ids': [packet['sources'][0]['id']],
                      'related_id': None}], 'summary': 'One candidate.'}, {'calls': 1, 'session_file': '/synthetic/log.jsonl'}


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.library, self.state = root / 'library', root / 'state'
        (self.library / 'techniques').mkdir(parents=True)
        self.config = {'libraryRoot': str(self.library), 'stateRoot': str(self.state)}
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        if '/comments/' in url:
            return feed((url.split('/comments/')[1].split('/')[0],), comments=True)
        return feed()

    def run_week(self, **kwargs):
        return w.run(self.config, kwargs.pop('now', NOW), kwargs.pop('get', self.get),
                     kwargs.pop('infer', good), lambda _: None)

    def test_publication_and_once_weekly(self):
        result = self.run_week()
        self.assertEqual(result['status'], 'published')
        self.assertEqual(result['week'], '2026-11-08')
        digest = self.library / 'weekly/2026-11-08/digest.md'
        self.assertIn('A technique', digest.read_text())
        self.assertEqual(self.run_week()['status'], 'already_attempted')
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(list((self.library / 'techniques').iterdir()), [])

    def test_monday_catchup_does_not_skip_next_sunday(self):
        result = self.run_week(now=NOW + dt.timedelta(days=1))
        self.assertEqual(result['week'], '2026-11-08')
        self.assertEqual(self.run_week(now=NOW + dt.timedelta(days=7))['week'], '2026-11-15')

    def test_before_nine_belongs_to_previous_sunday(self):
        self.assertEqual(self.run_week(now=NOW.replace(hour=8))['week'], '2026-11-01')

    def test_rate_limited_listing_never_calls_model_or_retries(self):
        def blocked(url):
            raise w.Problem('http_429', '2026-11-20T00:00:00+00:00')
        def forbidden(*args):
            self.fail('model must not run')
        result = self.run_week(get=blocked, infer=forbidden)
        self.assertEqual(result['status'], 'http_429')
        self.assertEqual(self.run_week()['status'], 'already_attempted')
        self.assertEqual(self.run_week(now=NOW + dt.timedelta(days=7))['status'], 'retry_after_wait')

    def test_comment_429_keeps_posts_and_pending(self):
        def partial(url):
            if '/comments/' in url:
                raise w.Problem('http_429')
            return feed(('abc123', 'def456'))
        result = self.run_week(get=partial)
        self.assertEqual(result['status'], 'published')
        state = json.loads((self.state / 'state.json').read_text())
        self.assertEqual(len(state['comment_pending']), 1)  # only attempted failures, not every unrequested thread
        self.assertIn('http_429', (self.library / 'weekly/2026-11-08/digest.md').read_text())

    def test_retry_after_survives_interrupted_model_or_publication(self):
        def partial(url):
            if '/comments/' in url:
                raise w.Problem('http_429', '2026-11-20T00:00:00+00:00')
            return feed()
        def interrupted(*args):
            raise OSError('synthetic interruption')
        with self.assertRaises(OSError):
            self.run_week(get=partial, infer=interrupted)
        state = json.loads((self.state / 'state.json').read_text())
        self.assertEqual(state['not_before'], '2026-11-20T00:00:00+00:00')
        self.assertEqual(self.run_week(now=NOW + dt.timedelta(days=7))['status'], 'retry_after_wait')

    def test_empty_new_posts_costs_no_model(self):
        def forbidden(*args):
            self.fail('no model for an empty interval')
        result = self.run_week(get=lambda _: feed(date='2026-10-01T00:00:00Z'), infer=forbidden)
        self.assertEqual(result['model']['calls'], 0)

    def test_failed_model_does_not_mark_seen_or_advance_cutoff(self):
        def failed(*args):
            raise w.Problem('model_failed')
        result = self.run_week(infer=failed)
        self.assertEqual(result['status'], 'model_failed')
        state = json.loads((self.state / 'state.json').read_text())
        self.assertEqual(state['seen'], [])
        self.assertEqual(w.instant(state['last_success']), NOW - dt.timedelta(days=7))

    def test_source_and_related_reference_validation(self):
        def wrong(config, packet):
            value, evidence = good(config, packet)
            value['ideas'][0]['source_ids'] = ['invented']
            return value, evidence
        self.assertEqual(self.run_week(infer=wrong)['status'], 'invalid_source_reference')
        value, _ = good({}, {'sources': [{'id': 'abc123'}]})
        value['ideas'][0]['source_ids'] = ['abc123']
        value['ideas'][0]['related_id'] = 'made-up'
        with self.assertRaises(w.Problem):
            w.validate(value, {'abc123'}, set())

    def test_html_entities_wrong_subreddit_and_dtd_fail(self):
        for raw in (b'<html>Blocked</html>', feed().replace(w.BASE.encode(), b'https://example.org/'),
                    b'<!DOCTYPE feed><feed/>'):
            with self.assertRaises(w.Problem):
                w.parse_feed(raw)

    def test_no_follow_writes_and_no_overwrite(self):
        target = Path(self.tmp.name) / 'target'
        target.write_text('keep')
        link = Path(self.tmp.name) / 'link'
        link.symlink_to(target)
        with self.assertRaises(w.Problem):
            w.write(link, b'bad', replace=True)
        with self.assertRaises(FileExistsError):
            w.write(target, b'bad')
        self.assertEqual(target.read_text(), 'keep')

    def test_existing_catalogue_and_prior_candidates(self):
        (self.library / 'techniques/example.md').write_text('---\nid: example\ntitle: Existing\n---\n## Problem and when useful\nProblem\n## Approach\nMechanism')
        self.run_week()
        ids = {p['id'] for p in w.catalogue(self.library)}
        self.assertEqual(ids, {'example', 'weekly-2026-11-08-1'})

    def test_input_cap_and_listing_gap_stay_visible(self):
        ids = tuple('a' + str(i) for i in range(55))
        result = self.run_week(get=lambda url: feed(comments=True) if '/comments/' in url else feed(ids))
        self.assertTrue(any('50-post' in item for item in result['gaps']))
        state = json.loads((self.state / 'state.json').read_text())
        self.assertEqual(len(state['seen']), 50)
        self.assertEqual(w.instant(state['last_success']), NOW - dt.timedelta(days=7))

    def test_markdown_escaping(self):
        result, _ = good({}, {'sources': [{'id': 'abc123'}]})
        result['ideas'][0]['title'] = '[evil](https://evil.invalid) <script>'
        sources = {'abc123': {'title': 'Post', 'url': w.BASE + 'comments/abc123/', 'comment_status': 'missing'}}
        rendered = w.render('week', result, sources, [])
        self.assertNotIn('[evil](https://evil.invalid)', rendered)
        self.assertNotIn('<script>', rendered)

    def test_pending_backlog_is_not_discarded(self):
        self.run_week(get=lambda _: feed(date='2026-10-01T00:00:00Z'))
        state = json.loads((self.state / 'state.json').read_text())
        state['comment_pending'] = [dict(w.parse_feed(feed((pid,)))[0], comment_status='pending') for pid in ('old1', 'old2')]
        w.save(self.state / 'state.json', state, replace=True)
        self.run_week(now=NOW + dt.timedelta(days=7), get=self.get)
        state = json.loads((self.state / 'state.json').read_text())
        self.assertEqual([p['id'] for p in state['comment_pending']], ['old2'])

    def test_lock_prevents_overlap(self):
        self.state.mkdir()
        with open(self.state / 'lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_week()['status'], 'already_running')


if __name__ == '__main__':
    unittest.main()
