#!/usr/bin/env python3
"""Create disposable TLS proof certificates with existing Python/OpenSSL only.

Public certificate metadata is the only stdout JSON. Signing material stays in
an automatically removed private temporary directory. Exported PKCS8 keys and
its tar are private. Existing output names, including symlinks, always refuse.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ARCHIVE_ROOT = 'file-mover-tls-proof'
CERTIFICATES = ('ca', 'other-ca', 'server', 'client', 'untrusted-client',
                'expired-client', 'wrong-usage-client', 'expired-server', 'unapproved-client')
LEAVES = CERTIFICATES[2:]
FILES = tuple(name+'.der' for name in CERTIFICATES) + tuple(name+'.key.der' for name in LEAVES)


def openssl(*arguments, data=None):
    """Never relay subprocess output on failure: a key must not become a log."""
    result = subprocess.run(['openssl', *map(str, arguments)], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=dict(os.environ, LC_ALL='C'), timeout=20)
    if result.returncode:
        raise RuntimeError('OpenSSL '+str(arguments[0])+' failed (exit '+str(result.returncode)+')')
    return result.stdout


def validity(path):
    dates = openssl('x509', '-inform', 'DER', '-in', path, '-noout', '-startdate', '-enddate').decode('ascii')
    parsed = {}
    for line in dates.splitlines():
        key, value = line.split('=', 1)
        if key not in ('notBefore', 'notAfter') or key in parsed:
            raise ValueError('unexpected certificate date output')
        parsed[key] = datetime.strptime(value, '%b %d %H:%M:%S %Y GMT').replace(tzinfo=timezone.utc)
    if set(parsed) != {'notBefore', 'notAfter'}:
        raise ValueError('missing certificate dates')
    return parsed['notBefore'], parsed['notAfter']


def identity(path):
    stat = path.lstat()
    return stat.st_dev, stat.st_ino


class Outputs:
    """Reserve names exclusively; on failure remove only files we created."""
    def __init__(self, output, archive):
        self.output = Path(os.path.abspath(output))
        self.archive = Path(os.path.abspath(archive))
        self.owned = {}
        self.directory_identity = None
        self.archive_file = None

    def __enter__(self):
        if os.path.lexists(self.output) or os.path.lexists(self.archive):
            raise FileExistsError('output directory or archive already exists')
        if self.output == self.archive or self.archive in (self.output/name for name in FILES):
            raise ValueError('output directory/archive paths collide')
        if not self.output.parent.is_dir():
            raise ValueError('output parent must already be a directory')
        if self.archive.parent != self.output and not self.archive.parent.is_dir():
            raise ValueError('archive parent must already be a directory or the new output directory')
        try:
            self.output.mkdir(mode=0o700)
            self.directory_identity = identity(self.output)
            self.output.chmod(0o700)
            descriptor = os.open(self.archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = os.fstat(descriptor)
            self.owned[self.archive] = created.st_dev, created.st_ino
            self.archive_file = os.fdopen(descriptor, 'wb')
            os.fchmod(self.archive_file.fileno(), 0o600)
            return self
        except BaseException:
            self.cleanup()
            raise

    def write(self, name, data):
        if name not in FILES:
            raise ValueError('unlisted DER export')
        path = self.output/name
        mode = 0o600 if name.endswith('.key.der') else 0o444
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        created = os.fstat(descriptor)
        self.owned[path] = created.st_dev, created.st_ino
        with os.fdopen(descriptor, 'wb') as file:
            os.fchmod(file.fileno(), mode)
            file.write(data)
        return path

    def cleanup(self):
        if self.archive_file is not None:
            try:
                self.archive_file.close()
            except OSError:
                pass
        for path, original in reversed(list(self.owned.items())):
            try:
                if identity(path) == original:
                    path.unlink()
            except OSError:
                pass
        if self.directory_identity is not None:
            try:
                if identity(self.output) == self.directory_identity:
                    self.output.rmdir()
            except OSError:
                pass

    def __exit__(self, kind, value, traceback):
        if kind is not None:
            self.cleanup()
        elif self.archive_file is not None:
            try:
                self.archive_file.close()
            except BaseException:
                self.cleanup()
                raise


def generate(output, archive):
    with Outputs(output, archive) as exports:
        with tempfile.TemporaryDirectory(prefix='file-mover-tls-signing-') as temporary:
            work = Path(temporary)

            def key(name):
                path = work/(name+'.key.pem')
                openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', path)
                return path

            for name in CERTIFICATES[:2]:
                openssl('req', '-new', '-x509', '-key', key(name), '-out', work/(name+'.pem'),
                        '-days', '2', '-sha256', '-subj', '/CN=file-mover-tls-proof-'+name,
                        '-addext', 'basicConstraints=critical,CA:true',
                        '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
            for serial, name in enumerate(LEAVES, 10):
                ca = 'other-ca' if name == 'untrusted-client' else 'ca'
                server = name in ('server', 'expired-server')
                usage = 'serverAuth' if server or name == 'wrong-usage-client' else 'clientAuth'
                subject = '/CN=localhost' if server else '/CN=file-mover-tls-proof-'+name
                private = key(name)
                csr, pem = work/(name+'.csr'), work/(name+'.pem')
                openssl('req', '-new', '-key', private, '-out', csr, '-subj', subject)
                extensions = work/(name+'.ext')
                text = ('basicConstraints=critical,CA:false\nkeyUsage=critical,digitalSignature\n'
                        'extendedKeyUsage='+usage+'\n')
                if server:
                    text += 'subjectAltName=DNS:localhost,IP:127.0.0.1\n'
                extensions.write_text(text, encoding='ascii')
                openssl('x509', '-req', '-in', csr, '-CA', work/(ca+'.pem'), '-CAkey', work/(ca+'.key.pem'),
                        '-set_serial', str(serial), '-days', '-1' if name.startswith('expired-') else '2',
                        '-sha256', '-extfile', extensions, '-out', pem)
            inventory = {}
            now = datetime.now(timezone.utc)
            for name in CERTIFICATES:
                data = openssl('x509', '-in', work/(name+'.pem'), '-outform', 'DER')
                path = exports.write(name+'.der', data)
                before, after = validity(path)
                expired = name.startswith('expired-')
                if (expired and after >= now) or (not expired and not before <= now < after):
                    raise ValueError('generated certificate has unexpected validity')
                inventory[path.name] = dict(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                                           not_before=before.isoformat(), not_after=after.isoformat())
                if name in LEAVES:
                    private = openssl('pkcs8', '-topk8', '-nocrypt', '-in', work/(name+'.key.pem'), '-outform', 'DER')
                    exports.write(name+'.key.der', private)
            version = openssl('version').decode('ascii').strip()
            # Only explicit DER members: never include signing keys/CSRs or the tar itself.
            with tarfile.open(fileobj=exports.archive_file, mode='w', format=tarfile.USTAR_FORMAT) as tar:
                directory = tarfile.TarInfo(ARCHIVE_ROOT)
                directory.type, directory.mode = tarfile.DIRTYPE, 0o700
                directory.uid = directory.gid = 1000
                tar.addfile(directory)
                for name in FILES:
                    data = (exports.output/name).read_bytes()
                    member = tarfile.TarInfo(ARCHIVE_ROOT+'/'+name)
                    member.uid = member.gid = 1000
                    member.mode = 0o600 if name.endswith('.key.der') else 0o444
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
    return dict(openssl_version=version, archive_root=ARCHIVE_ROOT, certificates=inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new private DER output directory')
    parser.add_argument('--archive', type=Path, required=True, help='new private tar path; never overwritten')
    args = parser.parse_args()
    try:
        result = generate(args.output, args.archive)
    except Exception as error:
        # No subprocess stdout/stderr or key material is included in the error.
        print('TLS fixture generation refused/failed: '+type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
