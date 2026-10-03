"""Read-only adapters for local Codex records; never export conversation bodies."""
import json
import os
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from response_evidence import communication

HOME = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
EVENTS = {'error', 'stream_error', 'warning', 'turn_aborted', 'request_failed', 'rate_limit', 'retry', 'model_fallback'}


def config(home=HOME):
    path = home / 'config.toml'
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8-sig'))
        return {'model': data.get('model'), 'effort': data.get('model_reasoning_effort'),
                'provider': data.get('model_provider'), 'path': str(path), 'error': None}
    except (OSError, ValueError):
        return {'model': None, 'effort': None, 'provider': None, 'path': str(path),
                'error': '默认配置缺失、不可读或格式不受支持'}


def sessions(home=HOME):
    entries = []
    root = (home / 'sessions').resolve()
    if not root.is_dir():
        return entries
    for path in root.rglob('*.jsonl'):
        try:
            if not path.resolve().is_relative_to(root):
                continue
            stat = path.stat()
            entries.append((stat.st_mtime, path))
        except OSError:
            continue
    return sorted(entries, key=lambda item: item[0], reverse=True)


def catalog(home=HOME):
    result = []
    for modified, path in sessions(home)[:100]:
        try:
            with path.open(encoding='utf-8') as stream:
                first = json.loads(stream.readline())
            meta = first.get('payload', {}) if first.get('type') == 'session_meta' else {}
            result.append({'key': str(path.relative_to(home / 'sessions')).replace('\\', '/'),
                           'id': meta.get('id') or meta.get('session_id') or path.stem,
                           'origin': meta.get('originator', '来源未记录'),
                           'modified': datetime.fromtimestamp(modified, timezone.utc).isoformat()})
        except (OSError, ValueError):
            continue
    return result


def inspect(key, target='', home=HOME):
    root = (home / 'sessions').resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path.suffix != '.jsonl' or not path.is_file():
        raise ValueError('任务记录不存在或路径不允许')
    defaults = config(home)
    target = target.strip() or defaults['model']
    turns, events, meta = [], [], {}
    malformed = 0
    with path.open(encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
                payload = record.get('payload', {})
                if not isinstance(payload, dict):
                    continue
            except (ValueError, AttributeError):
                malformed += 1
                continue
            kind = record.get('type')
            if kind == 'session_meta':
                meta = {k: payload.get(k) for k in ('id', 'session_id', 'originator', 'cli_version', 'model_provider')}
            elif kind == 'turn_context':
                turns.append({'turn_id': payload.get('turn_id'), 'model': payload.get('model'),
                              'effort': payload.get('effort') or payload.get('reasoning_effort'),
                              'timestamp': record.get('timestamp'), 'line': line_no})
            elif kind == 'event_msg' and payload.get('type') in EVENTS:
                # Event names are evidence; free-form messages may contain private prompts or tokens.
                events.append({'type': payload['type'], 'timestamp': record.get('timestamp'), 'line': line_no})
    latest = turns[-1] if turns else {}
    model = latest.get('model')
    status = 'unknown' if not target or not model else ('match' if target == model else 'different')
    missing = sum(not turn.get('model') for turn in turns)
    mismatches = sum(bool(turn.get('model')) and turn['model'] != target for turn in turns) if target else None
    if malformed:
        status = 'unknown'
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'target': target,
            'status': status, 'config': defaults, 'metadata': meta, 'latest': latest,
            'communication': communication(meta.get('id') or meta.get('session_id'), home),
            'turn_count': len(turns), 'missing_models': missing, 'historical_differences': mismatches,
            'turns': turns[-200:], 'events': events[-100:], 'event_count': len(events),
            'malformed_lines': malformed, 'source': str(path),
            'limits': ['结果仅反映本地记录，不能验证服务端实际执行的模型身份。',
                       '历史模型差异可能来自主动切换，不代表降级。',
                       '仅识别明确的结构化异常事件；未发现事件不等于请求从未失败。',
                       '默认配置仅作参考；项目、配置档和任务内覆盖以逐轮记录为准。']}
