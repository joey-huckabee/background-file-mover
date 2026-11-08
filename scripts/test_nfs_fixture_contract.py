"""Offline checks of current fixtures and strict separation from historical evidence."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import unittest
from nfs_fixture_contract import (RECORDING_ID, SECOND_RECORDING_ID,
    producer_request, request_digest, manifest_size, validate_v2,
    validate_writer_bytes, evidence_component, validate_evidence_manifest, validate_producer_response)
from nfs_manifest_capability import manifest_data
from test_nfs_manifest_capability import fixture as historical_fixture


def fixture():
    request = producer_request('/fixture/current', {'nested/data.bin': 2097169})
    manifest = dict(version=2, instance_id='a'*32, job_id='1', generator_id='fixture',
        recording_id=RECORDING_ID,
        request_identity=dict(version=1, algorithm='sha256', sha256=request_digest(request)),
        files=[dict(file_id='0', path='nested/data.bin', size_bytes='2097169',
            algorithm='sha256', sha256=hashlib.sha256(bytes(2097152)+b'0123456789abcdefg').hexdigest())])
    return request, manifest


class FixtureContract(unittest.TestCase):
    def test_identity_matches_all_retained_vectors(self):
        path = Path(__file__).resolve().parents[1]/'docs/api/request-identity-v1.candidate.vectors.json'
        for vector in json.loads(path.read_text())['vectors']:
            with self.subTest(vector=vector['id']):
                self.assertEqual(request_digest(vector['request']), vector['sha256'])

    def test_current_wire_and_complete_zero_size_map(self):
        request = producer_request('/fixture/current', {'empty': 0, 'nested/data.bin': 2097169})
        self.assertEqual(set(request), {'generator_id', 'recording_id', 'source_directory', 'files', 'expected_sizes_bytes'})
        self.assertEqual(request['files'], ['empty', 'nested/data.bin'])
        self.assertEqual(request['expected_sizes_bytes'], {'empty': '0', 'nested/data.bin': '2097169'})
        self.assertNotEqual(RECORDING_ID, SECOND_RECORDING_ID)
        request['expected_sizes_bytes'].pop('empty')
        with self.assertRaises(AssertionError): request_digest(request)

    def test_uuid_receipt_and_nonrelease_error_shape(self):
        request, _ = fixture()
        accepted = dict(job_id='1', recording_id=RECORDING_ID, accepted=True, source_paths_released=True)
        self.assertEqual(validate_producer_response(202, accepted, request), (202, accepted))
        accepted['recording_id'] = SECOND_RECORDING_ID
        with self.assertRaises(AssertionError): validate_producer_response(202, accepted, request)
        for code, error in ((409, 'source_file_missing'), (503, 'handoff_pending')):
            response = dict(recording_id=RECORDING_ID, error=error, retryable=True,
                            retry_after_seconds=None, source_paths_released=False)
            validate_producer_response(code, response, request)
            response['job_id'] = '1'
            with self.assertRaises(AssertionError): validate_producer_response(code, response, request)

    def test_exact_v2_bytes_and_manifest_rpc_payload(self):
        request, manifest = fixture()
        data = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(validate_writer_bytes(data, request), manifest)
        obj = dict(base64=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest(),
                   identity='1:112:1:'+str(len(data)))
        self.assertEqual(manifest_data(obj, request), data)
        with self.assertRaises(AssertionError): manifest_data(obj, 'old-label')
        for bad in (data+b'\n', json.dumps(manifest).encode(), data.replace(b'"2097169"', b'2097169')):
            with self.subTest(bad=bad), self.assertRaises(AssertionError): validate_writer_bytes(bad, request)

    def test_v2_rejects_bad_size_identity_mapping_and_fields(self):
        request, manifest = fixture()
        for mode in ('boolean_identity_version', 'numeric_size', 'leading_zero', 'overflow', 'wrong_uuid', 'wrong_digest', 'wrong_id', 'extra', 'wrong_path'):
            value = copy.deepcopy(manifest)
            if mode == 'boolean_identity_version': value['request_identity']['version'] = True
            elif mode == 'numeric_size': value['files'][0]['size_bytes'] = 2097169
            elif mode == 'leading_zero': value['files'][0]['size_bytes'] = '02097169'
            elif mode == 'overflow': value['files'][0]['size_bytes'] = str(2**64)
            elif mode == 'wrong_uuid': value['recording_id'] = SECOND_RECORDING_ID
            elif mode == 'wrong_digest': value['request_identity']['sha256'] = 'b'*64
            elif mode == 'wrong_id': value['files'][0]['file_id'] = '1'
            elif mode == 'extra': value['submission_id'] = 'old-label'
            else: value['files'][0]['path'] = 'other'
            with self.subTest(mode=mode), self.assertRaises(AssertionError): validate_v2(value, request)

    def test_boolean_integer_aliases_cannot_validate_writer_or_receipt(self):
        request, manifest = fixture()
        manifest['request_identity']['version'] = True
        raw = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode()
        with self.assertRaises(AssertionError): validate_writer_bytes(raw, request)
        accepted = dict(job_id='1', recording_id=RECORDING_ID, accepted=True, source_paths_released=True)
        for key in ('accepted', 'source_paths_released'):
            bad = dict(accepted); bad[key] = 1
            with self.subTest(key=key), self.assertRaises(AssertionError): validate_producer_response(202, bad, request)
        error = dict(recording_id=RECORDING_ID, error='handoff_pending', retryable=True,
                     retry_after_seconds=True, source_paths_released=False)
        with self.assertRaises(AssertionError): validate_producer_response(503, error, request)

    def test_v1_stays_historical_and_uses_numeric_directory_and_sizes(self):
        obj, _, _, _ = historical_fixture()
        self.assertEqual(manifest_data(obj, 'submission'), base64.b64decode(obj['base64']))
        manifest = json.loads(base64.b64decode(obj['base64']))
        case = dict(manifest=manifest, config=dict(source_binding=dict(root_id='submission')))
        self.assertEqual(evidence_component(case), '1')
        self.assertEqual(validate_evidence_manifest(case), manifest)
        self.assertEqual(manifest_size(manifest['files'][0], manifest), 2097169)
        case['submission'] = fixture()[0]
        with self.assertRaises(AssertionError): evidence_component(case)
        manifest['files'][0]['size_bytes'] = '2097169'
        with self.assertRaises(AssertionError): manifest_size(manifest['files'][0], manifest)

    def test_v2_evidence_requires_original_request_and_uuid_directory(self):
        request, manifest = fixture()
        case = dict(submission=request, manifest=manifest)
        self.assertEqual(evidence_component(case), RECORDING_ID)
        self.assertEqual(validate_evidence_manifest(case), manifest)
        case.pop('submission')
        with self.assertRaises(AssertionError): evidence_component(case)


if __name__ == '__main__': unittest.main()
