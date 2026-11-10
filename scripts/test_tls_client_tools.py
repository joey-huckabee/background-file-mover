"""Portable public-only tests; no processes, network, containers or state."""
import base64
import hashlib
import json
import ssl
import unittest

import tls_client_tools as tools

# Public X.509 certificate only, used to test parsing, not certificate trust.
PUBLIC_PEM = b'''-----BEGIN CERTIFICATE-----
MIIBtjCCAVugAwIBAgITBmyf1XSXNmY/Owua2eiedgPySjAKBggqhkjOPQQDAjA5
MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6b24g
Um9vdCBDQSAzMB4XDTE1MDUyNjAwMDAwMFoXDTQwMDUyNjAwMDAwMFowOTELMAkG
A1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJvb3Qg
Q0EgMzBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABCmXp8ZBf8ANm+gBG1bG8lKl
ui2yEujSLtf6ycXYqm0fc4E7O5hrOXwzpcVOho6AF2hiRVd9RFgdszflZwjrZt6j
QjBAMA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgGGMB0GA1UdDgQWBBSr
ttvXBp43rDCGB5Fwx5zEGbF4wDAKBggqhkjOPQQDAgNJADBGAiEA4IWSoxe3jfkr
BqWTrBqYaGFy+uGh0PsceGCmQ5nFuMQCIQCcAu/xlJyzlvnrxir4tiz+OpAUFteM
YyRIHN8wfdVoOw==
-----END CERTIFICATE-----
'''


def curl_output(body=b'{"accepted":true}', code=b'202', verify=b'0', ip=b'127.0.0.1', certs=None):
    if certs is None:
        certs = b'Subject: public fixture\nCert:' + PUBLIC_PEM
    return body + tools._METADATA + code + b'\n' + verify + b'\n' + ip + b'\n' + tools._CERTIFICATES + certs


def http_output(body=b'{"accepted":true}', headers=b'', code=b'202 Accepted'):
    return b'HTTP/1.1 ' + code + b'\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n' + headers + b'\r\n' + body


class Arguments(unittest.TestCase):
    def test_curl_exact_tls_and_protected_defaults(self):
        for version in ('1.2', '1.3'):
            with self.subTest(version=version):
                args = tools.curl_args('127.0.0.1', 8443, '/tmp/credentials', tls=version, body_path='/tmp/body.json')
                self.assertEqual(args[:2], ['/usr/bin/curl', '--disable'])
                for flag in ('--silent', '--show-error', '--http1.1', '--tlsv'+version):
                    self.assertIn(flag, args)
                for flag, value in {'--connect-timeout':'3', '--max-time':'10', '--retry':'0',
                                    '--noproxy':'*', '--proto':'=https', '--tls-max':version, '--resolve':'localhost:8443:127.0.0.1',
                                    '--cacert':'/tmp/credentials/ca.pem', '--cert':'/tmp/credentials/client.pem',
                                    '--key':'/tmp/credentials/client.key.pem', '--request':'POST',
                                    '--data-binary':'@/tmp/body.json', '--url':'https://localhost:8443/api/v2/jobs',
                                    '--write-out':tools.WRITE_OUT}.items():
                    self.assertEqual(args[args.index(flag)+1], value)
                self.assertIn('Content-Type: application/json', args)
                self.assertNotIn('--insecure', args)
                self.assertNotIn('--location', args)
                self.assertEqual(args.count('--proto'), 1)
                self.assertNotIn('--proto=https', args)
                self.assertNotIn('https', args)

    def test_override_without_certificate_and_literal_headers(self):
        args = tools.curl_args('::1', 443, '/c', certificate=None, host='wrong.example', ca='other-ca',
                               method='GET', path='/denied?x=1', headers=('Host: localhost', 'X-Test: a;b'))
        self.assertNotIn('--cert', args)
        self.assertNotIn('--key', args)
        self.assertNotIn('--data-binary', args)
        self.assertIn('wrong.example:443:[::1]', args)
        self.assertIn('/c/other-ca.pem', args)
        self.assertIn('X-Test: a;b', args)
        self.assertIn('https://wrong.example:443/denied?x=1', args)

    def test_openssl_verification_quiet_and_exact_protocol(self):
        for version in (1.2, 1.3):
            args = tools.openssl_args('::1', 443, '/c', tls=version)
            self.assertEqual(args[:2], ['/usr/bin/openssl', 's_client'])
            for flag in ('-quiet', '-ign_eof', '-no_ticket', '-verify_return_error', '-tls'+str(version).replace('.', '_')):
                self.assertEqual(args.count(flag), 1)
            for flag, value in {'-connect':'[::1]:443', '-servername':'localhost', '-verify_hostname':'localhost',
                                '-CAfile':'/c/ca.pem', '-cert':'/c/client.pem', '-key':'/c/client.key.pem'}.items():
                self.assertEqual(args[args.index(flag)+1], value)
        args = tools.openssl_args('127.0.0.1', 443, '/c', certificate=None)
        self.assertNotIn('-cert', args)
        self.assertNotIn('-key', args)

    def test_reject_unsafe_arguments_without_echo(self):
        for overrides in ({'tls':'1.1'}, {'port':True}, {'port':0}, {'ip':'--bad'}, {'host':'x/evil'},
                          {'certificate':'../key'}, {'ca':'../ca'}, {'credentials':'/tmp/\nsecret'},
                          {'path':'https://evil/'}, {'path':'//evil'}, {'path':'/a\r\nHost:x'},
                          {'method':'POST\n'}, {'headers':('X: a\nsecret',)}, {'headers':('--bad',)}):
            options = dict(ip='127.0.0.1', port=443, credentials='/c')
            options.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError) as raised:
                tools.curl_args(**options)
            self.assertNotIn('secret', str(raised.exception))


class CurlOutput(unittest.TestCase):
    def test_public_leaf_hash_and_exact_body(self):
        body = '{"message":"café"}'.encode()
        output = tools.parse_curl(curl_output(body=body))
        self.assertEqual(output, dict(code=202, verify_result=0, remote_ip='127.0.0.1',
                                     body_base64=base64.b64encode(body).decode(), json={'message':'café'},
                                     server_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(PUBLIC_PEM.decode())).hexdigest()))
        self.assertNotIn('BEGIN CERTIFICATE', json.dumps(output))
        self.assertEqual(tools.parse_curl(curl_output(certs=b'Cert:'+PUBLIC_PEM+b'\nCert:'+PUBLIC_PEM))['server_sha256'], output['server_sha256'])

    def test_transport_failure_can_lack_certificate_and_peer(self):
        result = tools.parse_curl(curl_output(body=b'', code=b'000', verify=b'20', ip=b'', certs=b''))
        self.assertEqual((result['code'], result['verify_result'], result['server_sha256'], result['json']), (0, 20, None, None))
        self.assertEqual(tools.parse_curl(curl_output(body=b'not JSON'))['json'], None)

    def test_exact_output_bound(self):
        overhead = len(curl_output(body=b''))
        raw = curl_output(body=b'x' * (tools.MAX_OUTPUT - overhead))
        self.assertEqual(len(raw), tools.MAX_OUTPUT)
        self.assertEqual(tools.parse_curl(raw)['code'], 202)
        with self.assertRaises(ValueError):
            tools.parse_curl(raw + b'x')

    def test_reject_bad_metadata_certificates_and_secret_diagnostics(self):
        bad = [b'', curl_output()+tools._METADATA, curl_output()+tools._CERTIFICATES,
               curl_output(code=b'20'), curl_output(code=b'600'), curl_output(verify=b'-1'),
               curl_output(ip=b'hostname'), curl_output(certs=b''), curl_output(code=b'000'),
               curl_output(certs=PUBLIC_PEM+b'trailing'), curl_output(certs=b'not a certificate'),
               curl_output(certs=b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n'),
               curl_output(certs=PUBLIC_PEM.replace(b'CERTIFICATE',b'PRIVATE KEY')),
               curl_output(certs=PUBLIC_PEM+b'\nSSL-Session:\nMaster-Key: secret'),
               b'x'*(tools.MAX_OUTPUT+1), curl_output(verify=b'1\n0'),
               curl_output(certs=b'garbage\n'+PUBLIC_PEM)]
        for raw in bad:
            with self.subTest(index=bad.index(raw)), self.assertRaises(ValueError) as raised:
                tools.parse_curl(raw)
            self.assertNotIn('secret', str(raised.exception))


class HttpOutput(unittest.TestCase):
    def test_one_json_response_and_binary_safe_body(self):
        body = '{"message":"café"}'.encode()
        result = tools.parse_http(http_output(body, b'Content-Type: application/json\r\n'))
        self.assertEqual(result, dict(code=202, body_base64=base64.b64encode(body).decode(), json={'message':'café'}))

    def test_exact_http_output_bound(self):
        # A six-digit length keeps header size stable while finding the boundary.
        body_length = tools.MAX_OUTPUT - len(http_output(b' ' * 100000)) + 100000
        body = b'{"x":"' + b'x' * (body_length - 8) + b'"}'
        raw = http_output(body)
        self.assertEqual(len(raw), tools.MAX_OUTPUT)
        self.assertEqual(tools.parse_http(raw)['code'], 202)
        with self.assertRaises(ValueError):
            tools.parse_http(raw + b'x')

    def test_strict_single_response_and_lengths(self):
        good = http_output()
        bad = [b'', good+good, good+b'x', good[:-1], good.replace(b'\r\n',b'\n'),
               good.replace(b'Content-Length:',b'Transfer-Encoding:'),
               http_output(headers=b'Transfer-Encoding: chunked\r\n'),
               http_output(headers=b'content-length: 17\r\n'),
               http_output(headers=b' Fold: value\r\n'), http_output(headers=b'X: bad\x00\r\n'),
               good.replace(b'Content-Length: 17',b'Content-Length: 017'),
               http_output(body=b'[]'), http_output(body=b'{"a":1,"a":2}'),
               http_output(body=b'{"x":NaN}'), http_output(body=b'{"x":1e999}'), http_output(body=b'{"x":\xff}'),
               http_output(code=b'100 Continue'), http_output(code=b'100 Continue')+good, b'x'*(tools.MAX_OUTPUT+1),
               http_output(body=b'{"Master-Key:":"secret"}')]
        for i, raw in enumerate(bad):
            with self.subTest(index=i), self.assertRaises(ValueError) as raised:
                tools.parse_http(raw)
            self.assertNotIn('secret', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
