"""HTTP utilities (pure helpers)."""

from urllib.parse import parse_qs, urlencode


def parse_cookies(header):
    cookies = {}
    if not header:
        return cookies
    for part in header.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            cookies[k] = v
    return cookies


def parse_multi_post(raw):
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: v if len(v) > 1 else v[0] for k, v in parsed.items()}


def as_list(data, key):
    v = data.get(key, [])
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip() != '']
    return [str(v)] if str(v).strip() != '' else []


def build_query_string(params):
    pairs = []
    for k, values in (params or {}).items():
        if not isinstance(values, list):
            values = [values]
        for v in values:
            if str(v).strip() != '':
                pairs.append((k, v))
    return urlencode(pairs)
