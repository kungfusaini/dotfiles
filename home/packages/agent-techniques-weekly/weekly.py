#!/usr/bin/env python3
"""Bounded weekly Reddit discovery; model output has no execution authority."""
import argparse
import datetime as dt
import email.utils
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ATOM = '{http://www.w3.org/2005/Atom}'
BASE = 'https://www.reddit.com/r/PiCodingAgent/'
MAX_HTTP = 750_000
MAX_PACKET = 150_000


class Problem(Exception):
    def __init__(self, code, retry_at=None):
        self.code, self.retry_at = code, retry_at
        super().__init__(code)


def stamp(now):
    return now.astimezone(UTC).isoformat()


def instant(text):
    value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timezone required')
    return value.astimezone(UTC)


def directory(path, create=False):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Problem('unsafe_path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        if os.fstat(fd).st_uid != os.getuid():
            raise Problem('foreign_directory')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read(path, limit=2_000_000):
    parent = directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise Problem('unsafe_file')
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise Problem('file_too_large')
            return data
    finally:
        os.close(parent)


def write(path, data, replace=False):
    """Atomic, no-follow, private writes. New digests never overwrite human work."""
    path = Path(path)
    parent = directory(path.parent, create=True)
    temp = '.weekly-' + uuid.uuid4().hex
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            try:
                info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                    raise Problem('unsafe_destination')
            except FileNotFoundError:
                pass
            os.rename(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.link(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temp, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def save(path, value, replace=False):
    write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode(), replace)


def plain(text, limit):
    # Render text, not source HTML/remote media. Keep a bounded excerpt, not an archive.
    text = re.sub(r'<[^>]*>', ' ', text or '')
    text = html.unescape(text)
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    return re.sub(r'\s+', ' ', text).strip()[:limit]


def parse_feed(raw, comments=False, thread_id=None):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise Problem('unsafe_xml')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise Problem('invalid_feed') from None
    if root.tag != ATOM + 'feed':
        raise Problem('not_atom_feed')
    home = root.find(ATOM + 'link[@rel="alternate"]')
    if home is None or not home.get('href', '').startswith(BASE):
        raise Problem('wrong_subreddit')
    if comments and thread_id and not home.get('href', '').startswith(BASE + 'comments/' + thread_id + '/'):
        raise Problem('wrong_comment_thread')
    result, seen = [], set()
    for entry in root.findall(ATOM + 'entry')[:100]:
        identity = entry.findtext(ATOM + 'id', '')
        if comments:
            if identity.startswith('t1_'):
                result.append({'id': identity, 'text': plain(entry.findtext(ATOM + 'content', ''), 1500)})
            continue
        if not re.fullmatch(r't3_[a-z0-9]+', identity):
            raise Problem('invalid_post_id')
        pid = identity[3:]
        if pid in seen:
            raise Problem('duplicate_feed_id')
        seen.add(pid)
        link = entry.find(ATOM + 'link')
        if link is None or not link.get('href', '').startswith(BASE + 'comments/' + pid + '/'):
            raise Problem('invalid_post_link')
        try:
            published = stamp(instant(entry.findtext(ATOM + 'published', '')))
        except ValueError:
            raise Problem('invalid_post_date') from None
        body = entry.findtext(ATOM + 'content', '')
        result.append({'id': pid, 'url': BASE + 'comments/' + pid + '/', 'published': published,
                       'title': plain(entry.findtext(ATOM + 'title', ''), 250),
                       'excerpt': plain(body, 2000), 'comments': [], 'comment_status': 'not_fetched',
                       'excerpt_may_be_truncated': True})
    if not comments and not result:
        raise Problem('empty_listing_unknown')
    return result


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith(BASE):
            raise Problem('redirect_refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not url.startswith(BASE):
        raise Problem('url_refused')
    opener = urllib.request.build_opener(Redirects())
    req = urllib.request.Request(url, headers={'User-Agent': 'agent-techniques-weekly/0.1 (personal RSS reader)',
                                             'Accept': 'application/atom+xml, application/xml'})
    try:
        with opener.open(req, timeout=20) as response:
            data = response.read(MAX_HTTP + 1)
            if len(data) > MAX_HTTP:
                raise Problem('feed_too_large')
            return data
    except urllib.error.HTTPError as error:
        retry_at = None
        if error.code == 429:
            value = error.headers.get('Retry-After', '')
            try:
                retry_at = stamp(dt.datetime.now(UTC) + dt.timedelta(seconds=max(0, int(value))))
            except (ValueError, OverflowError):
                try:
                    retry_at = stamp(email.utils.parsedate_to_datetime(value))
                except (ValueError, TypeError, OverflowError):
                    pass
        raise Problem('http_' + str(error.code), retry_at) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Problem('network_unavailable') from None


def catalogue(library):
    result = []
    for path in sorted((library / 'techniques').glob('*.md')):
        text = read(path, 20_000).decode()
        identity = re.search(r'^id: ([a-z0-9-]+)$', text, re.M)
        title = re.search(r'^title: (.+)$', text, re.M)
        if not identity or not title:
            raise Problem('invalid_library_entry')
        problem = text.split('## Problem and when useful', 1)[-1].split('## Approach', 1)[0]
        result.append({'id': identity[1], 'title': title[1], 'problem': problem.strip()[:700]})
    # Include previous machine candidates for cross-week deduplication, without reading full transcripts.
    for path in sorted((library / 'weekly').glob('*/ideas.json'))[-26:]:
        data = json.loads(read(path))
        for number, item in enumerate(data['ideas']):
            result.append({'id': f'weekly-{path.parent.name}-{number + 1}', 'title': item['title'],
                           'problem': item['problem'][:700]})
    if len(json.dumps(result).encode()) > 50_000:
        raise Problem('catalogue_requires_review')
    return result


def validate(value, sources, known):
    if not isinstance(value, dict) or set(value) != {'ideas', 'summary'}:
        raise Problem('invalid_model_schema')
    if not isinstance(value['summary'], str) or len(value['summary']) > 1500:
        raise Problem('invalid_model_summary')
    if not isinstance(value['ideas'], list) or len(value['ideas']) > 5:
        raise Problem('invalid_ideas')
    for idea in value['ideas']:
        if not isinstance(idea, dict) or set(idea) != {'title', 'problem', 'approach', 'caveats', 'source_ids', 'related_id'}:
            raise Problem('invalid_idea_schema')
        for field in ('title', 'problem', 'approach', 'caveats'):
            if not isinstance(idea[field], str) or not 1 <= len(idea[field]) <= (200 if field == 'title' else 2000):
                raise Problem('invalid_idea_text')
        refs = idea['source_ids']
        if not isinstance(refs, list) or not 1 <= len(refs) <= 5 or any(not isinstance(s, str) or s not in sources for s in refs):
            raise Problem('invalid_source_reference')
        if idea['related_id'] is not None and (not isinstance(idea['related_id'], str) or idea['related_id'] not in known):
            raise Problem('invalid_related_reference')
    return value


def escape(text):
    return re.sub(r'([\\`*_{}\[\]()<>#!|])', r'\\\1', text).replace('\n', ' ')


def render(week, result, sources, gaps):
    lines = [f'# Weekly agent techniques — {week}', '',
             'Machine-selected candidates, not verified recommendations or implementation tasks.', '',
             escape(result['summary']), '']
    for n, idea in enumerate(result['ideas'], 1):
        lines += [f'## {n}. {escape(idea["title"])}', '', '**Problem:** ' + escape(idea['problem']), '',
                  '**Approach:** ' + escape(idea['approach']), '', '**Caveats:** ' + escape(idea['caveats']), '',
                  '**Existing/related entry:** ' + escape(idea['related_id'] or 'new candidate'), '', '**Sources:**']
        for pid in dict.fromkeys(idea['source_ids']):
            lines.append(f'- [{escape(sources[pid]["title"])}]({sources[pid]["url"]}) — comments: {sources[pid]["comment_status"]}')
        lines.append('')
    if not result['ideas']:
        lines += ['No worthwhile new technique candidates selected.', '']
    lines += ['## Coverage limits', '', *['- ' + escape(gap) for gap in gaps], '',
              'Only bounded Reddit excerpts were supplied. Linked implementations were not inspected.', '']
    return '\n'.join(lines)


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))


def model(config, packet):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PROJECT_OBJECT_')
           and k not in ('PI_SESSION_ID', 'PI_SESSION_FILE', 'PI_CODING_AGENT_SESSION_DIR', 'OPENAI_API_KEY')}
    env.update(PI_CODING_AGENT_DIR=config['agentDir'], PI_OFFLINE='1', PI_TELEMETRY='0')
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            proc = subprocess.run([config['nodeBin'], str(Path(__file__).with_name('model.mjs')), config['_path']],
                                  input=json.dumps(packet).encode(), stdout=output, stderr=errors,
                                  cwd=config['stateRoot'], env=env, timeout=240, preexec_fn=limits, check=False)
        except (subprocess.TimeoutExpired, OSError):
            raise Problem('model_unavailable') from None
        output.seek(0)
        raw = output.read(100_001)
    if proc.returncode or len(raw) > 100_000:
        raise Problem('model_failed')
    try:
        answer = json.loads(raw)
        value = json.loads(answer['text'])
    except (ValueError, KeyError, TypeError):
        raise Problem('invalid_model_json') from None
    return value, {key: answer.get(key) for key in ('usage', 'session_file', 'calls')}


def run(config, now, get=fetch, infer=model, pause=time.sleep):
    state_root, library = Path(config['stateRoot']), Path(config['libraryRoot'])
    directory_fd = directory(state_root, create=True)
    try:
        lock = os.open('lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    with os.fdopen(lock, 'w'):
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise Problem('unsafe_lock')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'already_running'}
        state_path = state_root / 'state.json'
        try:
            state = json.loads(read(state_path))
        except FileNotFoundError:
            state = {'seen': [], 'last_success': stamp(now - dt.timedelta(days=7)), 'comment_pending': []}
        local = now.astimezone(ZoneInfo('Europe/London'))
        scheduled = (local - dt.timedelta(days=(local.weekday() + 1) % 7)).replace(hour=9, minute=0, second=0, microsecond=0)
        if local < scheduled:
            scheduled -= dt.timedelta(days=7)
        week = scheduled.date().isoformat()
        if state.get('attempt_week') == week:
            return {'status': 'already_attempted', 'week': week}
        if state.get('not_before') and instant(state['not_before']) > now:
            return {'status': 'retry_after_wait'}
        # Checkpoint before network/model work: crashes and manual invocations cannot start a retry loop.
        state['attempt_week'] = week
        save(state_path, state, replace=True)
        manifest = {'week': week, 'started_at': stamp(now), 'status': 'started', 'gaps': [], 'sources': []}
        run_root = state_root / 'runs' / week
        try:
            posts = parse_feed(get(BASE + 'new/.rss?limit=100'))
            cutoff = instant(state['last_success'])
            if instant(posts[-1]['published']) > cutoff:
                manifest['gaps'].append('Listing does not reach last successful cutoff; older unseen posts may be missing.')
            eligible = [p for p in posts if cutoff < instant(p['published']) <= now and p['id'] not in state['seen']]
            selected = eligible[:50]
            if len(eligible) > 50:
                manifest['gaps'].append('50-post input cap reached; unprocessed IDs: ' + ', '.join(p['id'] for p in eligible[50:]))
            # Retry up to one previously missing thread, alongside new candidates; never re-fetch everything.
            pending = state.get('comment_pending', [])
            if pending and pending[0]['id'] not in {p['id'] for p in selected}:
                selected.append(pending[0])
            targets = sorted(selected, key=lambda p: (p['comment_status'] != 'pending',
                             -sum(word in p['title'].lower() for word in ('extension', 'built', 'workflow', 'setup', 'tool'))))[:2]
            for post in targets:
                pause(3)
                try:
                    comments = parse_feed(get(BASE + 'comments/' + post['id'] + '/.rss'), comments=True, thread_id=post['id'])
                    post['comments'] = comments[:8]
                    post['comment_status'] = 'available_excerpt_not_complete'
                except Problem as error:
                    post['comment_status'] = error.code
                    manifest['gaps'].append(f'Comments {post["id"]}: {error.code}; other comments may be missing.')
                    if error.retry_at:
                        state['not_before'] = error.retry_at
                        save(state_path, state, replace=True)
                    if error.code in ('http_429', 'http_403'):
                        break
            known = catalogue(library)
            packet = {'week': week, 'sources': selected, 'catalogue': known}
            if len(json.dumps(packet).encode()) > MAX_PACKET:
                raise Problem('packet_requires_review')
            sources = {p['id']: p for p in selected}
            manifest['sources'] = [{k: p[k] for k in ('id', 'url', 'published', 'title', 'comment_status')} for p in selected]
            manifest['gaps'].append('At most two thread feeds and eight comment excerpts per thread; not complete comment coverage.')
            if selected:
                result, evidence = infer(config, packet)
                result = validate(result, sources, {item['id'] for item in known})
                manifest['model'] = evidence
            else:
                result = {'ideas': [], 'summary': 'No unseen eligible posts in the accessible listing.'}
                manifest['model'] = {'calls': 0}
            # Save originals for analysis and a readable digest; never rewrite curated technique files.
            save(run_root / 'ideas.json', result)
            save(library / 'weekly' / week / 'ideas.json', result)
            write(library / 'weekly' / week / 'digest.md', render(week, result, sources, manifest['gaps']).encode())
            manifest['status'] = 'published'
            manifest['digest'] = str(library / 'weekly' / week / 'digest.md')
            state['seen'] = sorted(set(state['seen']) | set(sources))[-5000:]
            waiting = {p['id']: p for p in pending if p['id'] not in sources}
            waiting.update({p['id']: dict(p, comment_status='pending', comments=[]) for p in selected
                            if p['comment_status'] not in ('available_excerpt_not_complete', 'not_fetched')})
            state['comment_pending'] = list(waiting.values())
            if len(waiting) > 100:
                manifest['gaps'].append('Comment backlog exceeds 100 threads; review needed. Backlog retained, not silently discarded.')
            # Only advance a time cutoff if both listing and model-input limits covered it.
            if not any('Listing does not' in g or '50-post' in g for g in manifest['gaps']):
                state['last_success'] = stamp(now)
        except Problem as error:
            manifest['status'] = error.code
            if error.retry_at:
                state['not_before'] = error.retry_at
                save(state_path, state, replace=True)
        manifest['finished_at'] = stamp(dt.datetime.now(UTC))
        save(run_root / 'manifest.json', manifest, replace=True)
        state['last_run'] = manifest
        save(state_path, state, replace=True)
        return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'status'))
    parser.add_argument('--config', default=os.path.expanduser('~/.config/agent-techniques/weekly.json'))
    args = parser.parse_args()
    try:
        config_path = Path(args.config)
        resolved = config_path.resolve(strict=True)
        if str(resolved).startswith('/nix/store/'):
            raw_config = resolved.read_bytes()
            if len(raw_config) > 16_000:
                raise Problem('config_too_large')
        else:
            raw_config = read(config_path, 16_000)
        config = json.loads(raw_config)
        config['_path'] = args.config
        if args.action == 'status':
            state = json.loads(read(Path(config['stateRoot']) / 'state.json'))
            report = {k: state.get(k) for k in ('attempt_week', 'not_before', 'last_success')}
            report['last_run'] = {k: v for k, v in state.get('last_run', {}).items() if k != 'sources'}
            report['last_run']['source_count'] = len(state.get('last_run', {}).get('sources', []))
            print(json.dumps(report, indent=2))
            return
        result = run(config, dt.datetime.now(UTC))
        print(json.dumps({k: v for k, v in result.items() if k != 'sources'}, ensure_ascii=False))
        if result['status'] not in ('published', 'already_running', 'already_attempted', 'retry_after_wait'):
            raise SystemExit(1)
    except (Problem, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': error.code if isinstance(error, Problem) else 'local_state_error'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
