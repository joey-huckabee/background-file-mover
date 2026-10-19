"""Read-only qualification model. This is NOT a shipping startup guard.

Only kernel mountinfo text and an explicit declaration are inputs. Never resolve,
stat, open, or probe an NFS pathname here. Descriptor/root/enrollment validation
and race exclusion remain separate service obligations.
"""
import hashlib
import json
import re


class Refused(ValueError):
    pass


def path(value):
    if (not isinstance(value, str) or not value.startswith('/') or
            any(c in value for c in '\x00\n\r') or
            (value != '/' and any(p in ('', '.', '..') for p in value[1:].split('/')))):
        raise Refused('noncanonical absolute path')
    return value


def beneath(child, parent):
    return child == parent or child.startswith(parent.rstrip('/') + '/')


def unescape(value):
    if re.search(r'\\(?!040|011|012|134)', value):
        raise Refused('invalid mountinfo escape')
    return re.sub(r'\\(040|011|012|134)', lambda m: chr(int(m[1], 8)), value)


def options(value):
    answer = {}
    for item in value.split(','):
        key, sep, val = item.partition('=')
        if not key or key in answer or (sep and not val):
            raise Refused('duplicate/empty mount option')
        answer[key] = val if sep else None
    return answer


def parse(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1024 * 1024:
        raise Refused('invalid/oversized mount inventory')
    records = []
    for line in text.splitlines():
        fields = line.split()
        try:
            pivot = fields.index('-')
            if pivot < 6 or len(fields) != pivot + 4:
                raise Refused('invalid mountinfo fields')
            mid, parent = int(fields[0]), int(fields[1])
            if mid <= 0 or parent <= 0 or not re.fullmatch(r'\d+:\d+', fields[2]):
                raise Refused('invalid mount identity')
            records.append(dict(id=mid, parent=parent, device=fields[2],
                root=path(unescape(fields[3])), point=path(unescape(fields[4])),
                vfs=options(fields[5]), optional=fields[6:pivot],
                filesystem=fields[pivot+1], source=unescape(fields[pivot+2]),
                super=options(fields[pivot+3])))
        except (ValueError, IndexError) as error:
            raise Refused('malformed mount inventory: ' + str(error)) from error
    if not records or len({r['id'] for r in records}) != len(records):
        raise Refused('empty/duplicate mount inventory')
    return records


def covering(records, target):
    candidates = [r for r in records if beneath(target, r['point'])]
    if not candidates:
        raise Refused('no covering mount')
    depth = max(len(r['point']) for r in candidates)
    selected = [r for r in candidates if len(r['point']) == depth]
    if len(selected) != 1:
        raise Refused('stacked/ambiguous covering mount')
    return selected[0]


# Recognized effective kernel options. Absence of ac/async/cto/lookupcache=all
# denotes Linux defaults; absence is never interpreted as an endpoint identity.
FLAGS = {'rw', 'sync', 'async', 'hard', 'noac', 'ac', 'cto', 'nocto',
         'soft', 'softerr', 'softreval', 'nosoftreval', 'nolock', 'lock',
         'resvport', 'noresvport', 'sharecache', 'nosharecache', 'fsc', 'nofsc'}
VALUES = {'vers', 'rsize', 'wsize', 'namlen', 'acregmin', 'acregmax',
          'acdirmin', 'acdirmax', 'proto', 'timeo', 'retrans', 'sec',
          'clientaddr', 'local_lock', 'addr', 'port', 'lookupcache',
          'nconnect', 'fatal_neterrors'}


def validate(text, declaration, previous=None):
    records = parse(text)
    selected = {}
    roots = [path(declaration[k]['path']) for k in ('source', 'destination')]
    if beneath(roots[0], roots[1]) or beneath(roots[1], roots[0]):
        raise Refused('source/destination roots overlap')
    state = path(declaration['state_path'])
    if any(beneath(state, r) or beneath(r, state) for r in roots):
        raise Refused('state and payload roots overlap')
    for role in ('source', 'destination'):
        expected = declaration[role]
        root = path(expected['path'])
        mount = covering(records, root)
        opts = mount['super']
        if expected['profile'] not in ('NMP-41B', 'NMP-41N'):
            raise Refused('undeclared profile')
        if mount['point'] != path(expected['mountpoint']) or mount['root'] != '/':
            raise Refused('unexpected mountpoint or subtree/bind root')
        if mount['filesystem'] not in ('nfs', 'nfs4'):
            raise Refused('missing NFS mount/local fallback')
        if mount['source'] != expected['source'] or opts.get('addr') != expected['addr']:
            raise Refused('endpoint/export differs from declaration')
        if opts.get('vers') != '4.1' or opts.get('proto') != 'tcp' or opts.get('sec') != 'sys':
            raise Refused('version/transport/security outside candidate profile')
        if 'rw' not in mount['vfs'] or 'ro' in mount['vfs'] or 'rw' not in opts or 'ro' in opts:
            raise Refused('read-only mount')
        if 'hard' not in opts or set(opts) & {'soft', 'softerr', 'softreval', 'nocto', 'nolock', 'nosharecache', 'fsc'}:
            raise Refused('retry/coherence/cache policy outside profile')
        if opts.get('local_lock', 'none') != 'none' or opts.get('lookupcache', 'all') != 'all':
            raise Refused('local locking/lookup cache override')
        if opts.get('nconnect', '1') != '1' or opts.get('port', '2049') != '2049':
            raise Refused('unqualified connection/port override')
        if set(opts) - FLAGS - VALUES:
            raise Refused('unreviewed effective mount option')
        if any((k in FLAGS and v is not None) or (k in VALUES and v is None) for k, v in opts.items()):
            raise Refused('invalid option value shape')
        for key in ('rsize', 'wsize', 'namlen', 'timeo', 'retrans'):
            if key not in opts or not re.fullmatch(r'[1-9]\d*', opts[key]):
                raise Refused('missing/invalid effective numeric option')
        if 'sync' in opts and 'async' in opts or 'ac' in opts and 'noac' in opts:
            raise Refused('conflicting cache/write policy')
        noac = 'noac' in opts
        if expected['profile'] == 'NMP-41B' and (noac or 'sync' in opts):
            raise Refused('buffered candidate requires ac/asynchronous client writes')
        if expected['profile'] == 'NMP-41N' and (not noac or 'sync' not in opts):
            raise Refused('noac diagnostic requires observed synchronous writes')
        if any(r['id'] != mount['id'] and beneath(r['point'], root) for r in records):
            raise Refused('nested or stacked mount in approved root')
        selected[role] = dict(path=root, profile=expected['profile'], mount=mount)
    local = covering(records, state)
    if local['filesystem'] not in ('ext4', 'xfs', 'btrfs', 'overlay', 'tmpfs'):
        raise Refused('state is not on a declared local filesystem')
    if any(beneath(r['point'], state) for r in records if r['id'] != local['id']):
        raise Refused('nested/individual state mount')
    selected['state'] = dict(path=state, mount=local)
    # This is a same-namespace observation pin, not authenticated NAS authority.
    digest = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    if previous is not None and previous != digest:
        raise Refused('observed mount pin changed; no automatic rebind')
    return dict(status='PROFILE_MATCH_ONLY', pin=digest, selected=selected,
                production_authorized=False, source_deletion_authorized=False,
                warnings=['No descriptor, symlink, root inode, permission, marker, RPC settlement or media proof.',
                          'AUTH_SYS requires a trusted network and consistent UID/GID; no server authentication.',
                          'Local state persistence is not proven, including overlay/tmpfs fixture state.',
                          'All effective options are pinned; modern fatal_neterrors is recorded, not old-kernel qualification.'])
