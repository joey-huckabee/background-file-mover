"""Finite independent OpenSSL checks of disposable TLS proof fixtures; no Rust."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

import tls_proof_fixture as fixture


@unittest.skipUnless(shutil.which('openssl'), 'local OpenSSL unavailable')
class Certificates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='test-tls-proof-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.output, cls.archive = cls.base/'der', cls.base/'proof.tar'
        cls.inventory = fixture.generate(cls.output, cls.archive)
        # Public-only conversion for independent OpenSSL verify invocations.
        for name in fixture.CERTIFICATES:
            result = subprocess.run(['openssl', 'x509', '-inform', 'DER', '-in', str(cls.output/(name+'.der')),
                                     '-out', str(cls.base/(name+'.pem'))], capture_output=True, timeout=10)
            if result.returncode:
                raise AssertionError('independent certificate conversion failed')

    def command(self, *arguments, data=None):
        return subprocess.run(['openssl', *map(str, arguments)], input=data, capture_output=True, timeout=10,
                              env=dict(os.environ, LC_ALL='C'))

    def text(self, name, *options):
        result = self.command('x509', '-inform', 'DER', '-in', self.output/(name+'.der'), '-noout', *options)
        self.assertEqual(result.returncode, 0)
        return result.stdout.decode()

    def test_inventory_is_only_public_hashes_dates_and_openssl_version(self):
        inventory = self.inventory
        self.assertEqual(set(inventory), {'openssl_version', 'archive_root', 'certificates'})
        self.assertEqual(inventory['openssl_version'], self.command('version').stdout.decode().strip())
        self.assertEqual(set(inventory['certificates']), {name+'.der' for name in fixture.CERTIFICATES})
        for name, item in inventory['certificates'].items():
            data = (self.output/name).read_bytes()
            self.assertEqual(set(item), {'sha256', 'size_bytes', 'not_before', 'not_after'})
            self.assertEqual(item['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(item['size_bytes'], len(data))
            self.assertIsNotNone(datetime.fromisoformat(item['not_after']).tzinfo)
        public_json = json.dumps(inventory)
        self.assertNotIn('PRIVATE KEY', public_json)
        self.assertNotIn('.key.der', public_json)
        self.assertNotIn('BEGIN ', public_json)

    def test_expired_certificates_have_real_past_not_after(self):
        for name in fixture.CERTIFICATES:
            with self.subTest(name=name):
                after = self.text(name, '-enddate').strip().split('=', 1)[1]
                timestamp = ssl.cert_time_to_seconds(after)
                check = self.command('x509', '-inform', 'DER', '-in', self.output/(name+'.der'), '-noout', '-checkend', '0')
                if name.startswith('expired-'):
                    self.assertLess(timestamp, time.time())
                    self.assertNotEqual(check.returncode, 0)
                else:
                    self.assertGreater(timestamp, time.time())
                    self.assertEqual(check.returncode, 0)

    def test_ca_and_leaf_constraints_and_exact_eku(self):
        for name in fixture.CERTIFICATES:
            text = self.text(name, '-text')
            with self.subTest(name=name):
                if name in ('ca', 'other-ca'):
                    self.assertIn('CA:TRUE', text)
                    self.assertIn('Certificate Sign, CRL Sign', text)
                else:
                    self.assertIn('CA:FALSE', text)
                    self.assertIn('Digital Signature', text)
                    self.assertNotIn('Certificate Sign', text)
                    usage = self.text(name, '-ext', 'extendedKeyUsage')
                    if name in ('server', 'expired-server', 'replacement-server', 'wrong-usage-client'):
                        self.assertIn('TLS Web Server Authentication', usage)
                        self.assertNotIn('TLS Web Client Authentication', usage)
                    else:
                        self.assertIn('TLS Web Client Authentication', usage)
                        self.assertNotIn('TLS Web Server Authentication', usage)

    def test_chain_purpose_hostname_ip_and_negative_certificates(self):
        def verify(name, purpose, ca='ca', *options):
            return self.command('verify', '-CAfile', self.base/(ca+'.pem'), '-purpose', purpose,
                                *options, self.base/(name+'.pem'))
        self.assertEqual(verify('client', 'sslclient').returncode, 0)
        self.assertEqual(verify('unapproved-client', 'sslclient').returncode, 0)
        self.assertEqual(verify('server', 'sslserver', 'ca', '-verify_hostname', 'localhost').returncode, 0)
        self.assertEqual(verify('server', 'sslserver', 'ca', '-verify_ip', '127.0.0.1').returncode, 0)
        self.assertNotEqual(verify('server', 'sslserver', 'ca', '-verify_hostname', 'other.invalid').returncode, 0)
        self.assertNotEqual(verify('untrusted-client', 'sslclient').returncode, 0)
        self.assertEqual(verify('untrusted-client', 'sslclient', 'other-ca').returncode, 0)
        wrong = verify('wrong-usage-client', 'sslclient')
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn(b'unsuitable certificate purpose', wrong.stdout+wrong.stderr)
        for name, purpose in (('expired-client', 'sslclient'), ('expired-server', 'sslserver')):
            result = verify(name, purpose)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'certificate has expired', result.stdout+result.stderr)
        for name in ('server', 'expired-server'):
            san = self.text(name, '-ext', 'subjectAltName')
            self.assertIn('DNS:localhost', san)
            self.assertIn('IP Address:127.0.0.1', san)

    def test_private_keys_are_pkcs8_p256_and_match_certificate_public_keys(self):
        for name in fixture.LEAVES:
            with self.subTest(name=name):
                key = self.output/(name+'.key.der')
                # PKCS8 parser rejects a bare SEC1 ECPrivateKey. Never request key text.
                check = self.command('pkcs8', '-inform', 'DER', '-in', key, '-nocrypt', '-out', os.devnull)
                self.assertEqual(check.returncode, 0)
                public = self.command('pkey', '-inform', 'DER', '-in', key, '-pubout', '-outform', 'DER')
                self.assertEqual(public.returncode, 0)
                cert_pem = self.command('x509', '-inform', 'DER', '-in', self.output/(name+'.der'), '-pubkey', '-noout')
                cert_public = self.command('pkey', '-pubin', '-outform', 'DER', data=cert_pem.stdout)
                self.assertEqual(cert_public.returncode, 0)
                self.assertTrue(public.stdout == cert_public.stdout, 'certificate public key mismatch')
                self.assertIn('ASN1 OID: prime256v1', self.text(name, '-text'))
        for name in ('ca', 'other-ca'):
            self.assertIn('ASN1 OID: prime256v1', self.text(name, '-text'))

    def test_archive_exact_members_numeric_ids_and_private_modes(self):
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o600)
        self.assertEqual({p.name for p in self.output.iterdir()}, set(fixture.FILES))
        with tarfile.open(self.archive) as tar:
            members = tar.getmembers()
            self.assertEqual(len(members), 1+len(fixture.FILES))
            self.assertEqual(members[0].name, 'file-mover-tls-proof')
            self.assertTrue(members[0].isdir())
            self.assertEqual(members[0].mode, 0o700)
            for member in members:
                self.assertEqual((member.uid, member.gid), (1000, 1000))
                self.assertEqual((member.uname, member.gname), ('', ''))
            for member in members[1:]:
                self.assertTrue(member.isfile())
                name = member.name.removeprefix('file-mover-tls-proof/')
                self.assertIn(name, fixture.FILES)
                mode = 0o600 if name.endswith('.key.der') else 0o444
                self.assertEqual(member.mode, mode)
                path = self.output/name
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                self.assertTrue(tar.extractfile(member).read() == path.read_bytes())

    def test_mid_generation_error_cleans_partial_private_exports(self):
        output, archive = self.base/'failed-der', self.base/'failed.tar'
        original = fixture.openssl
        observed = []
        def fail_second_key(*arguments, **kwargs):
            if arguments[0] == 'pkcs8' and (output/'server.key.der').exists():
                observed.append(True)
                raise RuntimeError('deliberate second key conversion failure')
            return original(*arguments, **kwargs)
        with patch.object(fixture, 'openssl', side_effect=fail_second_key):
            with self.assertRaises(RuntimeError): fixture.generate(output, archive)
        self.assertTrue(observed)
        self.assertFalse(output.exists())
        self.assertFalse(archive.exists())

    def test_cli_generates_fresh_certificates_without_private_stdout(self):
        output, archive = self.base/'fresh', self.base/'fresh.tar'
        result = subprocess.run([sys.executable, fixture.__file__, '--output', str(output), '--archive', str(archive)],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        inventory = json.loads(result.stdout)
        self.assertEqual(set(inventory), set(self.inventory))
        self.assertNotEqual(inventory['certificates']['ca.der']['sha256'], self.inventory['certificates']['ca.der']['sha256'])
        self.assertNotIn(b'.key.der', result.stdout)
        self.assertNotIn(b'PRIVATE KEY', result.stdout)
        # The CLI may place its tar inside the new private output, without self-inclusion.
        nested = self.base/'nested'
        fixture.generate(nested, nested/'proof.tar')
        with tarfile.open(nested/'proof.tar') as tar:
            self.assertEqual(len(tar.getmembers()), 1+len(fixture.FILES))


class OutputSafety(unittest.TestCase):
    def test_existing_directory_archive_and_dangling_symlinks_refuse_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output, archive = base/'der', base/'proof.tar'
            archive.write_bytes(b'sentinel')
            with self.assertRaises(FileExistsError): fixture.generate(output, archive)
            self.assertFalse(output.exists())
            self.assertEqual(archive.read_bytes(), b'sentinel')
            archive.unlink()
            output.mkdir()
            (output/'sentinel').write_bytes(b'preserve')
            with self.assertRaises(FileExistsError): fixture.generate(output, archive)
            self.assertFalse(archive.exists())
            self.assertEqual((output/'sentinel').read_bytes(), b'preserve')
            for name in ('directory-link', 'archive-link'):
                link = base/name
                link.symlink_to(base/'missing')
                args = (link, base/'new.tar') if name == 'directory-link' else (base/'new', link)
                with self.assertRaises(FileExistsError): fixture.generate(*args)
                self.assertTrue(link.is_symlink())
            self.assertFalse((base/'new').exists())
            self.assertFalse((base/'new.tar').exists())

    def test_path_collisions_and_missing_parents_refuse_without_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for output, archive in ((base/'new', base/'new'), (base/'new', base/'new/ca.der'),
                                    (base/'missing/new', base/'new.tar'), (base/'new', base/'missing/new.tar')):
                with self.subTest(output=output, archive=archive), self.assertRaises(ValueError):
                    fixture.generate(output, archive)
                self.assertFalse(output.exists())
                self.assertFalse(archive.exists())

    def test_failure_cleans_signing_directory_and_owned_outputs_without_private_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output, archive = base/'der', base/'proof.tar'
            signing = []
            original = tempfile.TemporaryDirectory
            def temporary_directory(**kwargs):
                value = original(dir=base, **kwargs)
                signing.append(Path(value.name))
                return value
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(fixture.tempfile, 'TemporaryDirectory', side_effect=temporary_directory), \
                    patch.object(fixture, 'openssl', side_effect=RuntimeError('PRIVATE KEY secret sentinel')), \
                    patch.object(sys, 'argv', ['fixture', '--output', str(output), '--archive', str(archive)]), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(fixture.main(), 1)
            self.assertFalse(output.exists())
            self.assertFalse(archive.exists())
            self.assertTrue(signing)
            self.assertTrue(all(not path.exists() for path in signing))
            self.assertEqual(stdout.getvalue(), '')
            self.assertNotIn('PRIVATE', stderr.getvalue())
            self.assertNotIn('sentinel', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
