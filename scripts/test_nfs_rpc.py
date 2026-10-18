"""Fixture evidence decoder rejection tests; no Rust build or application test."""
import io
import struct
import unittest
from nfs_rpc import LIMIT, call, reply, read_record


def u(*values):
    return struct.pack('!' + 'I' * len(values), *values)


def opaque(value):
    return u(len(value)) + value + bytes((-len(value)) % 4)


CALL = (u(123, 0, 2, 100003, 4, 1, 0, 0, 0, 0) + opaque(b'') + u(1, 4, 53)
        + bytes(32) + u(22) + opaque(b'file handle') + u(28) + opaque(b'1.part') + u(9, 1, 2))
REPLY = (u(123, 1, 0, 0, 0, 0, 0) + opaque(b'') + u(4, 53, 0) + bytes(36)
         + u(22, 0, 28, 0, 1) + bytes(16) + u(9, 0, 1, 2) + opaque(b'attributes'))


class Stream:
    def __init__(self, value):
        self.data = io.BytesIO(value)

    def recv(self, size):
        return self.data.read(min(size, 2))


class EvidenceDecoder(unittest.TestCase):
    def test_matching_remove_and_success(self):
        request, result = call(CALL), reply(REPLY)
        self.assertEqual(request['xid'], result['xid'])
        self.assertEqual(request['operations'][2], dict(op=28, name='1.part'))
        self.assertEqual(request['operations'][0]['sequence_hex'], bytes(32).hex())
        self.assertEqual(result['operations'][2], dict(op=28, status=0))
        self.assertEqual(result['status'], 0)

    def test_every_truncation_and_trailing_bytes_refused(self):
        for decoder, value in ((call, CALL), (reply, REPLY)):
            for end in range(len(value)):
                with self.subTest(decoder=decoder.__name__, end=end), self.assertRaises(ValueError):
                    decoder(value[:end])
            with self.assertRaises(ValueError):
                decoder(value + bytes(4))

    def test_unknown_opcode_and_opcode_inside_handle_are_not_evidence(self):
        prefix = u(1, 0, 2, 100003, 4, 1, 0, 0, 0, 0) + opaque(b'') + u(1, 1)
        with self.assertRaises(ValueError):
            call(prefix + u(999) + opaque(u(28) + opaque(b'1.part')))
        value = call(prefix + u(22) + opaque(u(28) + opaque(b'1.part')))
        self.assertFalse(any(op.get('op') == 28 for op in value['operations']))

    def test_wrong_protocol_auth_lengths_minor_and_counts_refused(self):
        for offset, value in ((4, 1), (8, 3), (12, 17), (16, 3), (20, 0),
                              (28, LIMIT), (44, 2), (48, 0), (48, 129)):
            data = CALL[:offset] + u(value) + CALL[offset + 4:]
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                call(data)

    def test_fragmented_records_preserved_exactly(self):
        wire = u(7) + CALL[:7] + u(0x80000000 | (len(CALL) - 7)) + CALL[7:]
        stream = Stream(wire)
        self.assertEqual(read_record(stream), (wire, CALL))
        self.assertIsNone(read_record(stream))

    def test_record_bounds_and_truncation(self):
        for wire in (u(0x80000000 | (LIMIT + 1)), u(0x80000004) + b'a', bytes(4096)):
            with self.assertRaises(ValueError):
                read_record(Stream(wire))


if __name__ == '__main__':
    unittest.main()
