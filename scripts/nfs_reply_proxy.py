"""Private disposable TCP observer; hold only matched successful REMOVE replies."""
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time
from nfs_rpc import call, reply, read_record


def serve(backend):
    root = '/tmp/control'
    os.mkdir(root, 0o700)
    lock = threading.RLock()
    state = dict(ready=False, token=None, armed=False, name=None, held=[], released=[],
                 dropped=[], forwarded=[], errors=[], connections=0, received=0, connection_resets=[])
    pending = []
    expected_disconnect = set()

    def save():
        with open(root + '/state.next', 'w', encoding='utf-8') as file:
            json.dump(state, file)
        os.replace(root + '/state.next', root + '/state.json')

    def controls():
        last = None
        while True:
            try:
                with open(root + '/command.json', encoding='utf-8') as file:
                    command = json.load(file)
                if command['token'] != last:
                    with lock:
                        action = command['action']
                        if action == 'arm':
                            if pending or state['armed']:
                                raise ValueError('already armed')
                            state.update(token=command['token'], armed=True, name=command['name'],
                                         held=[], released=[], dropped=[], forwarded=[], errors=[], connection_resets=[])
                        elif action in ('release', 'drop'):
                            close = set()
                            for stream, wire, row in pending:
                                if action == 'release':
                                    try:
                                        stream.sendall(wire)
                                    except OSError:
                                        state['dropped'].append(dict(row, cleanup_peer_closed=True))
                                        continue
                                state['released' if action == 'release' else 'dropped'].append(row)
                                if action == 'drop':
                                    close.add(stream)
                                    if row['connection'] not in state['connection_resets']:
                                        state['connection_resets'].append(row['connection'])
                            pending.clear()
                            state['armed'] = False
                            # Explicit reply loss plus connection interruption;
                            # never assume a bounded retry on a healthy TCP stream.
                            for stream in close:
                                expected_disconnect.add(stream)
                                try:
                                    stream.shutdown(socket.SHUT_RDWR)
                                except OSError:
                                    pass
                                stream.close()
                        else:
                            raise ValueError('unknown relay command')
                        last = command['token']
                        state['command_token'] = last
                        save()
            except FileNotFoundError:
                pass
            except Exception as error:
                with lock:
                    state['errors'].append(str(error))
                    last = command.get('token')
                    save()
            time.sleep(.02)

    def connection(client, number):
        # Preserve the controlled export's existing reserved-port requirement.
        # The runner sets unprivileged_port_start=0 only in this owned netns.
        server = socket.socket()
        server.settimeout(10)
        server.bind(('', 600 + number))
        server.connect((backend, 2049))
        server.settimeout(None)
        calls = {}

        def requests():
            try:
                while (record := read_record(client)) is not None:
                    wire, data = record
                    xid = struct.unpack('!I', data[:4])[0]
                    try:
                        decoded = call(data)
                    except (ValueError, UnicodeError):
                        decoded = None
                    with lock:
                        if len(calls) >= 4096 and xid not in calls:
                            raise ValueError('request map bound')
                        calls[xid] = dict(decoded=decoded, sha256=hashlib.sha256(data).hexdigest())
                        if decoded and any(op.get('op') == 28 for op in decoded['operations']):
                            calls[xid]['payload_hex'] = data.hex()
                    server.sendall(wire)
            except Exception as error:
                with lock:
                    if client not in expected_disconnect:
                        state['errors'].append('request: ' + str(error))
                    save()
            finally:
                try:
                    server.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        threading.Thread(target=requests, daemon=True).start()
        try:
            while (record := read_record(server)) is not None:
                wire, data = record
                xid = struct.unpack('!I', data[:4])[0]
                with lock:
                    request = calls.get(xid, {})
                    decoded = request.get('decoded')
                    state['received'] += 1
                    selected = state['armed'] and decoded and any(
                        op.get('op') == 28 and op.get('name') == state['name'] for op in decoded['operations'])
                    row = dict(connection=number, xid=xid, request=request, receive_id=state['received'],
                               reply_sha256=hashlib.sha256(data).hexdigest(), wire_bytes=len(wire))
                    if selected:
                        row['payload_hex'] = data.hex()
                        observed = reply(data)
                        row['reply'] = observed
                        if observed['status'] == 0 and any(op == dict(op=28, status=0) for op in observed['operations']):
                            if len(pending) >= 128 or sum(len(v[1]) for v in pending) + len(wire) > 16 * 1048576:
                                raise ValueError('withheld reply bound')
                            pending.append((client, wire, row))
                            state['held'].append(row)
                            save()
                            continue
                    client.sendall(wire)
                    if request.get('decoded') and any(op.get('op') == 28 for op in decoded['operations']):
                        row['payload_hex'] = data.hex()
                        row['reply'] = reply(data)
                        state['forwarded'].append(row)
                        state['forwarded'] = state['forwarded'][-128:]
                        save()
                    calls.pop(xid, None)
        except Exception as error:
            with lock:
                if client not in expected_disconnect:
                    state['errors'].append('response: ' + str(error))
                save()
        finally:
            client.close()
            server.close()

    listener = socket.create_server(('0.0.0.0', 2049), backlog=16)
    with lock:
        state['ready'] = True
        save()
    threading.Thread(target=controls, daemon=True).start()
    while True:
        client, _ = listener.accept()
        with lock:
            state['connections'] += 1
            if state['connections'] > 16:
                raise ValueError('connection bound')
            number = state['connections']
        threading.Thread(target=connection, args=(client, number), daemon=True).start()


if __name__ == '__main__':
    serve(sys.argv[1])
