"""Exercise a disposable CI deployment through its public frontend."""
import http.cookiejar
import json
import secrets
import sys
import urllib.request


def main(origin):
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = None

    def api(path, payload=None):
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': origin}
        with client.open(urllib.request.Request(origin + path, data, headers), timeout=15) as response:
            return json.load(response)

    csrf = api('/api/me')['csrf_token']
    username = 'ci_' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    api('/api/signup', {'username': username, 'email': username + '@example.com', 'password': password})
    csrf = api('/api/login', {'identifier': username.upper(), 'password': password})['csrf_token']
    dataset = api('/api/datasets', {'name': 'Pipeline sample', 'text': '1,2,3'})['dataset']
    analysis = api('/api/analyses', {
        'name': 'Pipeline check', 'dataset_id': dataset['id'], 'dataset_revision': dataset['revision'],
    })['analysis']
    saved = api('/api/analyses/' + str(analysis['id']))['analysis']
    if saved['calculation']['results']['mean'] != 2 or len(api('/api/datasets?search=sample')['datasets']) != 1:
        raise RuntimeError('Saved data or calculated result did not match')
    print('Frontend, API, authentication and database checks passed.')


if __name__ == '__main__':
    main(sys.argv[1].rstrip('/'))
