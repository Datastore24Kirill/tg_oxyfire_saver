"""Read public release metadata only; never execute or install remote code."""
import json
import re
import ssl
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    return tuple(map(int, match.groups())) if match else None


def select_release(items, repo, current, allow_preview=False):
    current_version = version(current)
    if current_version is None:
        raise ValueError('Invalid current version')
    candidates = []
    for item in items:
        tag = item.get('tag_name', '')
        number = version(tag)
        if not number or number <= current_version or item.get('draft'):
            continue
        if item.get('prerelease') and not allow_preview:
            continue
        url = str(item.get('html_url', ''))
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or not parsed.path.startswith('/' + repo + '/releases/tag/'):
            continue
        # Do not advertise a release until downloadable applications exist.
        assets = [a for a in item.get('assets', []) if a.get('name', '').endswith(('.zip', '.exe', '.dmg')) and a.get('size', 0) > 0]
        if assets:
            candidates.append((number, {'latest': tag.lstrip('v'), 'url': url, 'preview': bool(item.get('prerelease')), 'assets': assets}))
    return max(candidates, key=lambda c: c[0])[1] if candidates else None


def check_release(repo, current, allow_preview=False):
    request = Request('https://api.github.com/repos/' + repo + '/releases?per_page=30',
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Oxyfire-Update-Check'})
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    with urlopen(request, timeout=8, context=context) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Release metadata is too large')
        items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError('Invalid release metadata')
    return select_release(items, repo, current, allow_preview)
