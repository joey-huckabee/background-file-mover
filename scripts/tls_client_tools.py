"""Pure argv builders and bounded public-output parsers for disposable TLS clients.

These functions execute nothing. The driver owns process exit-code checks,
subprocess deadlines, bounded capture and a sanitized environment (in particular
no SSLKEYLOGFILE). Parsers raise ValueError without echoing captured output.
"""
import base64
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import ssl

# Pinned curl certs variable (introduced 7.88.0):
# https://github.com/curl/curl/blob/curl-7_88_1/docs/cmdline-opts/write-out.d
MAX_OUTPUT = 131072
_METADATA = b'\nFM_CURL_METADATA_V1\n'
_CERTIFICATES = b'FM_CURL_CERTIFICATES_V1\n'
WRITE_OUT = (_METADATA.decode() + '%{http_code}\n%{ssl_verify_result}\n'
             '%{remote_ip}\n' + _CERTIFICATES.decode() + '%{certs}')
_TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
_PEM = re.compile(rb'-----BEGIN CERTIFICATE-----\n([A-Za-z0-9+/=\n]+)'
                  rb'-----END CERTIFICATE-----')


def _text(value):
    value = str(value)
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid client argument')
    return value


def _endpoint(ip, port, host, tls):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError('invalid client IP') from None
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid client port')
    host = _text(host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                                  for label in host.split('.')):
            raise ValueError('invalid client host') from None
    version = str(tls)
    if version not in ('1.2', '1.3'):
        raise ValueError('unsupported TLS version')
    return str(address), host, version


def _credential(credentials, name, key=False):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name):
        raise ValueError('invalid credential name')
    return str(Path(_text(credentials)) / (name + ('.key.pem' if key else '.pem')))


def curl_args(ip, port, credentials, certificate='client', tls=1.3,
              method='POST', path='/api/v2/jobs', body_path=None,
              host='localhost', ca='ca', headers=()):
    """Return argv; headers is a sequence of literal single-line 'Name: value'."""
    ip, host, version = _endpoint(ip, port, host, tls)
    method, path = _text(method), _text(path)
    if not re.fullmatch(_TOKEN, method) or not path.startswith('/') or path.startswith('//') or '#' in path:
        raise ValueError('invalid HTTP request target')
    if any(c.isspace() for c in path):
        raise ValueError('invalid HTTP request target')
    ip_literal = '[' + ip + ']' if ':' in ip else ip
    host_literal = '[' + host + ']' if ':' in host else host
    # --disable must be first: do not inherit ~/.curlrc retries, logging or trust.
    args = ['/usr/bin/curl', '--disable', '--silent', '--show-error', '--http1.1',
            '--connect-timeout', '3', '--max-time', '10', '--retry', '0',
            '--noproxy', '*', '--proto', '=https', '--globoff', '--path-as-is',
            '--tlsv' + version, '--tls-max', version,
            '--resolve', f'{host_literal}:{port}:{ip_literal}',
            '--cacert', _credential(credentials, ca)]
    if certificate is not None:
        args += ['--cert', _credential(credentials, certificate),
                 '--key', _credential(credentials, certificate, True)]
    args += ['--request', method, '--header', 'Content-Type: application/json']
    for header in headers:
        header = _text(header)
        name, separator, _ = header.partition(':')
        if not separator or not re.fullmatch(_TOKEN, name):
            raise ValueError('invalid HTTP header')
        args += ['--header', header]
    if body_path is not None:
        args += ['--data-binary', '@' + _text(body_path)]
    return args + ['--write-out', WRITE_OUT, '--url', f'https://{host_literal}:{port}{path}']


def openssl_args(ip, port, credentials, certificate='client', tls=1.3,
                 host='localhost', ca='ca'):
    ip, host, version = _endpoint(ip, port, host, tls)
    ip_literal = '[' + ip + ']' if ':' in ip else ip
    args = ['/usr/bin/openssl', 's_client', '-connect', f'{ip_literal}:{port}',
            '-servername', host, '-verify_hostname', host, '-verify_return_error',
            '-CAfile', _credential(credentials, ca)]
    if certificate is not None:
        args += ['-cert', _credential(credentials, certificate),
                 '-key', _credential(credentials, certificate, True)]
    # Never remove quiet: default s_client stdout contains TLS session secrets.
    return args + ['-tls' + version.replace('.', '_'), '-quiet', '-ign_eof', '-no_ticket']


def _raw(value):
    if isinstance(value, str):
        if len(value) > MAX_OUTPUT:
            raise ValueError('client output exceeds bound')
        try:
            value = value.encode('utf-8')
        except UnicodeError:
            raise ValueError('invalid client output') from None
    if not isinstance(value, bytes) or len(value) > MAX_OUTPUT:
        raise ValueError('invalid or oversized client output')
    # Fail closed instead of retaining default s_client/session/key diagnostics.
    if re.search(rb'PRIVATE KEY|CLIENT_RANDOM|(?:CLIENT|SERVER)_.*TRAFFIC_SECRET|Master-Key:|Resumption PSK:|Session-ID:|SSL-Session:', value):
        raise ValueError('unexpected sensitive client output')
    return value


def _object(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('non-finite JSON value')

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON value')
        return result

    try:
        result = json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                            parse_constant=constant, parse_float=number)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid JSON object') from None
    if not isinstance(result, dict):
        raise ValueError('invalid JSON object')
    return result


def _optional_object(body):
    try:
        return _object(body)
    except ValueError:
        return None


def _certificate_hash(certs):
    if not certs:
        return None
    try:
        text = certs.decode('ascii')
        matches = list(_PEM.finditer(certs))
        if not matches:
            raise ValueError()
        # Only public certificate blocks; malformed/other PEM blocks fail closed.
        remainder = _PEM.sub(b'', certs)
        if b'-----' in remainder or any(ord(c) < 32 and c != '\n' for c in text):
            raise ValueError()
        if any(line.strip() and not re.fullmatch(rb'[ -~]+:[ -~]*', line)
               for line in remainder.splitlines()):
            raise ValueError()
        if certs[matches[-1].end():].strip():
            raise ValueError()
        digest = None
        for match in matches:
            pem = match.group().decode('ascii')
            payload = match.group(1).replace(b'\n', b'')
            decoded = base64.b64decode(payload, validate=True)
            der = ssl.PEM_cert_to_DER_cert(pem)
            if der != decoded or base64.b64encode(decoded) != payload:
                raise ValueError()
            # Parse X.509 using stdlib SSL in memory; no temp files or trust claim.
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cadata=pem)
            if digest is None:
                digest = hashlib.sha256(der).hexdigest()
        return digest
    except (ValueError, UnicodeError, ssl.SSLError):
        raise ValueError('invalid public certificate output') from None


def parse_curl(stdout):
    raw = _raw(stdout)
    if raw.count(_METADATA) != 1 or raw.count(_CERTIFICATES) != 1:
        raise ValueError('invalid curl output framing')
    body, metadata = raw.split(_METADATA)
    fields, certs = metadata.split(_CERTIFICATES)
    lines = fields.split(b'\n')
    if len(lines) != 4 or lines[-1] or not re.fullmatch(rb'[0-9]{3}', lines[0]) or not re.fullmatch(rb'0|[1-9][0-9]{0,9}', lines[1]):
        raise ValueError('invalid curl metadata')
    code, verify_result = int(lines[0]), int(lines[1])
    if code != 0 and not 100 <= code <= 599:
        raise ValueError('invalid curl HTTP status')
    try:
        remote = lines[2].decode('ascii')
        if remote:
            ipaddress.ip_address(remote)
    except (ValueError, UnicodeError):
        raise ValueError('invalid curl peer address') from None
    digest = _certificate_hash(certs)
    if code and (digest is None or not remote):
        raise ValueError('incomplete curl HTTPS evidence')
    if not code and body:
        raise ValueError('unexpected transport-failure body')
    return dict(code=code, verify_result=verify_result, remote_ip=remote,
                body_base64=base64.b64encode(body).decode('ascii'),
                json=_optional_object(body), server_sha256=digest)


def parse_http(raw):
    raw = _raw(raw)
    header, separator, body = raw.partition(b'\r\n\r\n')
    if not separator:
        raise ValueError('invalid HTTP framing')
    lines = header.split(b'\r\n')
    if not re.fullmatch(rb'HTTP/1\.[01] [2-5][0-9]{2} [\x20-\x7e]*', lines[0]):
        raise ValueError('invalid HTTP status')
    headers = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b':')
        if not colon or not re.fullmatch(_TOKEN.encode(), name) or any(c < 32 and c != 9 or c == 127 for c in value):
            raise ValueError('invalid HTTP header')
        name = name.lower()
        if name in headers:
            raise ValueError('duplicate HTTP header')
        headers[name] = value.strip(b' \t')
    length = headers.get(b'content-length', b'')
    if b'transfer-encoding' in headers or not re.fullmatch(rb'0|[1-9][0-9]{0,5}', length):
        raise ValueError('invalid HTTP body framing')
    if len(body) != int(length):
        raise ValueError('HTTP body length mismatch')
    return dict(code=int(lines[0][9:12]), body_base64=base64.b64encode(body).decode('ascii'),
                json=_object(body))
