"""Offline fixture identities and version-aware evidence checks, never a wire adapter.

Fixed UUIDs may repeat across cases because each case owns separate state/roots.
Historical v1 evidence remains v1 evidence; it cannot qualify a UUID runtime.
"""
import hashlib
import json
import re
import uuid

RECORDING_ID = '11111111-1111-4111-8111-111111111111'
SECOND_RECORDING_ID = '22222222-2222-4222-8222-222222222222'
THIRD_RECORDING_ID = '33333333-3333-4333-8333-333333333333'


def producer_request(source_directory, sizes, recording_id=RECORDING_ID, generator_id='fixture'):
    assert str(uuid.UUID(recording_id)) == recording_id
    assert sizes and all(type(n) is int and 0 <= n <= 2**64-1 for n in sizes.values())
    return dict(generator_id=generator_id, recording_id=recording_id,
                source_directory=source_directory, files=list(sizes),
                expected_sizes_bytes={path: str(size) for path, size in sizes.items()})


def validate_producer_response(code, response, request):
    if code == 202:
        assert type(response['job_id']) is str and re.fullmatch(r'[1-9][0-9]*', response['job_id'])
        assert response == dict(job_id=response['job_id'], recording_id=request['recording_id'],
                                accepted=True, source_paths_released=True)
    else:
        assert set(response) == {'recording_id', 'error', 'retryable', 'retry_after_seconds', 'source_paths_released'}
        assert response['recording_id'] in (None, request['recording_id'])
        assert response['source_paths_released'] is False and type(response['retryable']) is bool
    return code, response


def request_digest(request):
    def string(value):
        data = value.encode('utf-8')
        return len(data).to_bytes(4, 'big') + data
    paths = sorted(request['files'], key=lambda p: p.encode('utf-8'))
    assert len(set(paths)) == len(paths)
    frame = b'BFM-REQUEST-IDENTITY\0v1\0'
    for value in (request['generator_id'], str(uuid.UUID(request['recording_id'])), request['source_directory']):
        frame += string(value)
    frame += len(paths).to_bytes(4, 'big') + b''.join(string(p) for p in paths)
    sizes = request.get('expected_sizes_bytes')
    frame += b'\0' if sizes is None else b'\1'
    if sizes is not None:
        assert set(sizes) == set(paths)
        for path in paths:
            value = sizes[path]
            assert type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value)
            frame += int(value).to_bytes(8, 'big')
    return hashlib.sha256(frame).hexdigest()


def manifest_size(entry, manifest):
    value = entry['size_bytes']
    if manifest['version'] == 1:
        assert type(value) is int and 0 <= value <= 2**64-1
    else:
        assert manifest['version'] == 2 and type(value) is str
        assert re.fullmatch(r'0|[1-9][0-9]*', value) and int(value) <= 2**64-1
    return int(value)


def validate_v2(manifest, request):
    assert set(manifest) == {'version', 'instance_id', 'job_id', 'generator_id', 'recording_id', 'request_identity', 'files'}
    assert type(manifest['version']) is int and manifest['version'] == 2
    assert re.fullmatch(r'[0-9a-f]{32}', manifest['instance_id'])
    assert re.fullmatch(r'[1-9][0-9]*', manifest['job_id']) and int(manifest['job_id']) <= 2**63-1
    assert manifest['recording_id'] == str(uuid.UUID(request['recording_id']))
    assert manifest['generator_id'] == request['generator_id']
    assert manifest['request_identity'] == dict(version=1, algorithm='sha256', sha256=request_digest(request))
    assert len(manifest['files']) == len(request['files'])
    for index, entry in enumerate(manifest['files']):
        assert set(entry) == {'file_id', 'path', 'size_bytes', 'algorithm', 'sha256'}
        assert entry['file_id'] == str(index) and entry['path'] == request['files'][index]
        manifest_size(entry, manifest)
        assert entry['algorithm'] == 'sha256' and re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])
    return manifest


def validate_writer_bytes(data, request):
    manifest = validate_v2(json.loads(data), request)
    ordered = {k: manifest[k] for k in ('version', 'instance_id', 'job_id', 'generator_id', 'recording_id', 'request_identity', 'files')}
    ordered['request_identity'] = {k: manifest['request_identity'][k] for k in ('version', 'algorithm', 'sha256')}
    ordered['files'] = [{k: f[k] for k in ('file_id', 'path', 'size_bytes', 'algorithm', 'sha256')} for f in manifest['files']]
    assert data == json.dumps(ordered, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return manifest


def evidence_component(case):
    """Choose paths from recorded identity, never relabel historical reports."""
    manifest = case.get('manifest')
    request = case.get('submission')
    if manifest is not None and manifest['version'] == 1:
        assert not (request and 'recording_id' in request)
        return manifest['job_id']
    assert request and 'recording_id' in request, 'v2 evidence requires the original producer request'
    if manifest is not None:
        validate_v2(manifest, request)
    return str(uuid.UUID(request['recording_id']))


def validate_evidence_manifest(case):
    manifest = case['manifest']
    component = evidence_component(case)
    if manifest['version'] == 1:
        assert manifest['submission_id'] == case['config']['source_binding']['root_id']
    else:
        assert manifest['recording_id'] == component
    return manifest
