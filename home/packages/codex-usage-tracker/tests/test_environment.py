"""Offline scenario reporting tests, synthetic usage only; no live APIs."""
import contextlib
import importlib.util
import io
import math
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest import mock
import test_tracker as fixtures
from test_tracker import t, header, change, response

spec = importlib.util.spec_from_file_location(
    'codex_environment', Path(__file__).parents[1] / 'codex_environment.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def record(key, model='gpt-6.1-sol', output=1000, concrete=None):
    return dict(key=key, model=model, response_model=concrete, output=output)


class EnergyTests(unittest.TestCase):
    def test_pinned_upstream_golden(self):
        # Independently evaluated the seven original operational-energy functions
        # in pinned llm.py, with 1000 output, 375B total, 38..112B active,
        # TPS57/TTFT4.07, PUE1.2 and no measured-latency cap. Units converted kWh->Wh.
        lo, hi = e.energy(e.catalog()['gpt-6.1-sol'], 1000)
        self.assertAlmostEqual(lo, 1.4637798217957254, places=12)
        self.assertAlmostEqual(hi, 2.272803072549629, places=12)

    def test_entire_catalog_and_aliases(self):
        models = e.catalog()
        self.assertGreater(len(models), 80)
        for name, model in models.items():
            with self.subTest(name=name):
                lo, hi = e.energy(model, 1000)
                self.assertTrue(math.isfinite(lo) and math.isfinite(hi))
                self.assertTrue(0 < lo <= hi)
        self.assertNotIn('gpt-6.1-sol-guessed-alias', models)

    def test_linear_token_plus_per_request_overhead_and_missing(self):
        model = e.catalog()['gpt-6.1-sol']
        a, b = e.energy(model, 1000), e.energy(model, 2000)
        self.assertTrue(all(x < y < 2*x for x, y in zip(a, b)))
        self.assertIsNone(e.energy(model, None))
        self.assertIsNone(e.energy(model, 0))
        self.assertIsNone(e.energy(model, -1))

    def test_mixed_model_scope_rollups_and_concrete_precedence(self):
        records = [record('a'), record('b', 'gpt-6-sol'),
                   record('c', concrete='unknown-concrete'),
                   record('d', 'unknown-request', concrete='gpt-6.1-sol'),
                   record('e', output=None), record('f', output=0)]
        scopes = {'a': ('project', 'stream'), 'b': ('project', None),
                  'c': ('ambiguous', None), 'd': ('project', 'stream')}
        groups, total, unknown, warnings = e.summarize(records, scopes, e.catalog())
        self.assertEqual((total['calls'], total['covered'], total['missing'], total['zero']), (6, 3, 1, 1))
        self.assertEqual((total['output'], total['covered_output']), (4000, 3000))
        self.assertEqual(unknown, {'unknown-concrete': 1})
        self.assertEqual(groups[('project', 'stream')]['covered'], 2)
        self.assertEqual(groups[('ambiguous', None)]['covered'], 0)
        self.assertEqual(groups[('unmatched', None)]['calls'], 2)
        self.assertAlmostEqual(total['lo'], sum(g['lo'] for g in groups.values()))
        self.assertIn('model-arch-not-released', warnings)
        self.assertIn('unknown', e.cells(groups[('ambiguous', None)], 400))
        self.assertIn('0–0', e.cells(total, 0))

    def test_empty_not_zero_and_conditional_carbon(self):
        _, total, unsupported, warnings = e.summarize([], {}, e.catalog())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            e.introduction(total, unsupported, warnings, 400)
        self.assertIn('unknown | unknown | 0/0', out.getvalue())
        self.assertIn('N/A', out.getvalue())
        self.assertIn('NOT confidence', out.getvalue())


class EnvironmentReportTests(unittest.TestCase):
    setUp = fixtures.TrackerTests.setUp
    tearDown = fixtures.TrackerTests.tearDown
    write = fixtures.TrackerTests.write

    def module(self):
        return mock.patch.dict(sys.modules, {'codex_environment': e})

    def test_report_readonly_offline_and_reasoning_not_doubled(self):
        self.write([header(), change(modelId='gpt-6.1-sol'),
                    response(model='gpt-6.1-sol', responseId='a',
                             usage={'input': 999999, 'cacheRead': 99999999,
                                    'output': 1000, 'reasoning': 500})])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
        before = (self.directory / 'usage.sqlite').read_bytes()
        with t.database(self.directory, readonly=True) as db, self.module(), \
                mock.patch.object(t, 'fetch_quota', side_effect=AssertionError('network')):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                t.report(db, '2026-11-02', environment=True)
            text = out.getvalue()
            self.assertIn('1.5–2.3 | 0.59–0.91 | 1/1', text)
            self.assertIn('100.0% of recorded output', text)
            self.assertIn('Source warnings:', text)
            self.assertNotIn('PRIVATE', text)
        self.assertEqual((self.directory / 'usage.sqlite').read_bytes(), before)

    def test_frozen_environment_records_and_writer_unblocked(self):
        self.write([header(), change(), response(model='gpt-6.1-sol', responseId='first')])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
        original = t.report_attribution
        def scan(db, since, until, all_streams=False, snapshot=None, **kwargs):
            self.assertFalse(db.in_transaction)
            with t.database(self.directory) as writer:
                self.write([response('new', model='gpt-6-sol', responseId='later')], mode='a')
                t.ingest(writer, [self.log])
                writer.commit()
            self.assertEqual(len(kwargs['environment_records']), 1)
            return original(db, since, until, all_streams, snapshot=snapshot, **kwargs)
        with t.database(self.directory, readonly=True) as db, self.module(), \
                mock.patch.object(t, 'report_attribution', side_effect=scan), \
                contextlib.redirect_stdout(io.StringIO()):
            t.report(db, '2026-11-02', environment=True)

    def test_cli_flag_positions_and_grid_validation(self):
        with t.database(t.state_dir()):
            pass
        for argv in (["--environment"], ["--environment", "status"],
                     ["week", "--start", "2026-11-02", "--environment"],
                     ["refresh", "--environment"],
                     ["--environment", "--grid-carbon", "100", "status"]):
            with mock.patch.object(sys, 'argv', ['codex-usage'] + argv), \
                    mock.patch.object(t, 'report') as report, mock.patch.object(t, 'collect', return_value=0):
                self.assertEqual(t.main(), 0)
                self.assertTrue(report.call_args.kwargs['environment'])
                self.assertEqual(report.call_args.kwargs['grid_carbon'], 100 if '100' in argv else 400)
        for argv in (['--grid-carbon', '100'], ['--environment', '--grid-carbon', 'nan'],
                     ['--environment', '--grid-carbon', '-1'], ['--environment', '--grid-carbon', 'inf'],
                     ['--environment', 'history'], ['--environment', 'collect']):
            with mock.patch.object(sys, 'argv', ['codex-usage'] + argv), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                t.main()
            self.assertEqual(exc.exception.code, 2)

    def test_scope_remainder_and_mixed_unknown_coverage(self):
        scopes = {str(i): ('project', str(i)) for i in range(15)}
        records = [record(str(i), output=1000) for i in range(14)] + [record('14', 'unsupported')]
        result = {'groups': {scope: [1, 1000, 0] for scope in scopes.values()},
                  'scopes': scopes, 'calls': 15, 'output': 15000,
                  'matched_calls': 15, 'matched_output': 15000, 'issues': 0, 'limited': False}
        with self.module(), mock.patch.object(t, 'attribution', return_value=result), \
                mock.patch.object(t, 'scope_names', return_value=({'project': 'Project'}, {}, 0)):
            for all_streams in (False, True):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    t.report_attribution(None, 0, 1, all_streams, environment_records=records)
                text = out.getvalue()
                self.assertIn('14/15 calls', text)
                self.assertIn('unsupported: 1 calls', text)
                self.assertEqual('Remaining 3' in text, not all_streams)
                self.assertIn('Project | 15 | 15,000 | 100.00% | ', text)


if __name__ == '__main__':
    unittest.main()
