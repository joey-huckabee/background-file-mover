"""Bounded, fixture-only RPC/NFSv4.1 observation, never a production decoder.

RFC 5531 sections 9/11 and RFC 8881 operation/XDR definitions. Unsupported
compounds cannot provide positive evidence. Never search arbitrary bytes for opcodes.
"""
import hashlib
import struct

LIMIT = 8 * 1024 * 1024


class Xdr:
    def __init__(self, data):
        if len(data) > LIMIT:
            raise ValueError('oversize XDR')
        self.data, self.offset = data, 0

    def take(self, size):
        if size < 0 or self.offset + size > len(self.data):
            raise ValueError('truncated XDR')
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def uint(self):
        return struct.unpack('!I', self.take(4))[0]

    def opaque(self):
        size = self.uint()
        value = self.take(size)
        if any(self.take((-size) % 4)):
            raise ValueError('nonzero XDR padding')
        return value

    def bitmap(self):
        size = self.uint()
        if size > 64:
            raise ValueError('oversize bitmap')
        self.take(4 * size)

    def done(self):
        if self.offset != len(self.data):
            raise ValueError('trailing XDR')


def call(data):
    x = Xdr(data)
    xid = x.uint()
    if [x.uint() for _ in range(5)] != [0, 2, 100003, 4, 1]:
        raise ValueError('not an NFS COMPOUND call')
    for _ in range(2):
        x.uint()  # auth flavor
        x.opaque()
    x.opaque()  # tag
    if x.uint() != 1:
        raise ValueError('not NFS minor version 1')
    size = x.uint()
    if not 1 <= size <= 128:
        raise ValueError('compound operation count')
    operations = []
    for _ in range(size):
        op = x.uint()
        row = dict(op=op)
        if op == 53:  # SEQUENCE args
            row['sequence_hex'] = x.take(32).hex()
        elif op in (22, 15, 28, 11):  # PUTFH / LOOKUP / REMOVE / LINK
            value = x.opaque()
            if op == 22:
                row['filehandle_sha256'] = hashlib.sha256(value).hexdigest()
            if op in (28, 11):
                row['name'] = value.decode('ascii')
        elif op == 9:  # GETATTR
            x.bitmap()
        elif op not in (10, 16, 24, 31, 32):
            raise ValueError(f'unsupported request operation {op}')
        operations.append(row)
    x.done()
    return dict(xid=xid, operations=operations)


def reply(data):
    x = Xdr(data)
    xid = x.uint()
    if [x.uint() for _ in range(2)] != [1, 0]:
        raise ValueError('not accepted RPC reply')
    x.uint()
    x.opaque()
    if x.uint() != 0:
        raise ValueError('not RPC success')
    status = x.uint()
    x.opaque()
    size = x.uint()
    if not 1 <= size <= 128:
        raise ValueError('compound reply count')
    operations = []
    for _ in range(size):
        op, code = x.uint(), x.uint()
        operations.append(dict(op=op, status=code))
        if code:
            if len(operations) != size:
                raise ValueError('operations after NFS error')
            continue
        if op == 53:
            x.take(36)
        elif op in (28, 11):
            x.take(20)  # change_info4
        elif op == 9:
            x.bitmap()
            x.opaque()
        elif op == 10:
            x.opaque()
        elif op not in (22, 15, 16, 24, 31, 32):
            raise ValueError(f'unsupported reply operation {op}')
    x.done()
    return dict(xid=xid, status=status, operations=operations)


def read_record(stream):
    """Preserve original record fragments, bounded across all fragments."""
    wire, payload = bytearray(), bytearray()

    def exact(size):
        chunks = bytearray()
        while len(chunks) < size:
            data = stream.recv(size - len(chunks))
            if not data:
                if not chunks and not wire and size == 4:
                    return None
                raise ValueError('truncated RPC record')
            chunks.extend(data)
        return bytes(chunks)

    for _ in range(1024):
        header = exact(4)
        if header is None:
            return None
        marker = struct.unpack('!I', header)[0]
        size = marker & 0x7fffffff
        if len(payload) + size > LIMIT:
            raise ValueError('oversize RPC record')
        data = exact(size)
        wire.extend(header + data)
        payload.extend(data)
        if marker & 0x80000000:
            return bytes(wire), bytes(payload)
    raise ValueError('too many RPC fragments')
