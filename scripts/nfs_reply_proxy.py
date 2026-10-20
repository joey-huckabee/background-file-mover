"""Private disposable TCP observer; hold matched successful REMOVE or LINK replies."""
import base64
import zlib
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
    state = dict(ready=False, token=None, armed=False, name=None, operation=28, held=[], released=[],
                 dropped=[], forwarded=[], errors=[], connections=0, active=0, received=0,
                 connection_resets=[], transport_events=[], observing=False, trace=[], trace_bytes=0, trace_overflow=False)
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
                        if action == 'observe':
                            state.update(observing=True, trace=[], trace_bytes=0, trace_overflow=False)
                        elif action == 'stop_observe':
                            state['observing'] = False
                        elif action == 'checkpoint':
                            pass  # Persist the complete live trace without resetting its window.
                        elif action == 'arm':
                            if command.get('operation', 28) not in (5, 11, 28, 38):
                                raise ValueError('unsupported selected operation')
                            if pending or state['armed']:
                                raise ValueError('already armed')
                            state.update(token=command['token'], armed=True, name=command['name'], operation=command.get('operation', 28),
                                         held=[], released=[], dropped=[], forwarded=[], errors=[], connection_resets=[], transport_events=[])
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

    def observe(direction, number, data, decoded):
        if not state['observing']:
            return
        if len(state['trace']) >= 8192 or state['trace_bytes'] + len(data) > 64 * 1048576:
            state['trace_overflow'] = True
            return
        state['trace_bytes'] += len(data)
        state['trace'].append(dict(direction=direction, connection=number,
            monotonic_ns=time.monotonic_ns(), xid=struct.unpack('!I', data[:4])[0],
            sha256=hashlib.sha256(data).hexdigest(), decoded=decoded,
            payload_zlib_base64=base64.b64encode(zlib.compress(data)).decode('ascii')))
        # Flush with the next acknowledged control/hold/event/error checkpoint.
        # Rewriting the full growing window per packet distorts the workload.

    def connection(client, number):
        # Preserve the controlled export's existing reserved-port requirement.
        # The runner sets unprivileged_port_start=0 only in this owned netns.
        server = socket.socket()
        closed = threading.Event()

        def event(kind, error=None):
            with lock:
                state['transport_events'].append(dict(connection=number, kind=kind, error=error))
                state['transport_events'] = state['transport_events'][-128:]
                save()

        def close_streams(kind):
            with lock:
                if closed.is_set():
                    return
                closed.set()
                expected_disconnect.add(client)
                # close() alone cannot wake a recv in the other forwarding
                # thread. Shut down BOTH directions before releasing descriptors.
                for stream in (client, server):
                    try:
                        stream.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    stream.close()
                state['active'] -= 1
                event(kind)

        # Keep the accepted frontend while the backend is unavailable. No RPC
        # bytes have been forwarded yet, so retrying connect cannot duplicate RPCs.
        deadline = time.monotonic() + 600
        while True:
            try:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.settimeout(1)
                server.bind(('', 600 + number))
                server.connect((backend, 2049))
                server.settimeout(None)
                break
            except OSError as error:
                event('backend_connect_failed', str(error))
                server.close()
                if time.monotonic() >= deadline:
                    with lock:
                        state['errors'].append('backend connect deadline')
                    close_streams('connect_deadline_closed')
                    return
                time.sleep(1)
                server = socket.socket()
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
                        observe('call', number, data, decoded)
                        if len(calls) >= 4096 and xid not in calls:
                            raise ValueError('request map bound')
                        calls[xid] = dict(decoded=decoded, sha256=hashlib.sha256(data).hexdigest())
                        if decoded and any(op.get('op') in (5, 11, 28, 38) for op in decoded['operations']):
                            calls[xid]['payload_hex'] = data.hex()
                    server.sendall(wire)
            except Exception as error:
                with lock:
                    if isinstance(error, OSError) and client not in expected_disconnect:
                        event('request_transport_error', str(error))
                    elif client not in expected_disconnect:
                        state['errors'].append('request: ' + str(error))
                    save()
            finally:
                close_streams('frontend_closed')

        threading.Thread(target=requests, daemon=True).start()
        try:
            while (record := read_record(server)) is not None:
                wire, data = record
                xid = struct.unpack('!I', data[:4])[0]
                with lock:
                    request = calls.get(xid, {})
                    decoded = request.get('decoded')
                    state['received'] += 1
                    try:
                        observed_reply = reply(data)
                    except ValueError:
                        observed_reply = None
                    observe('reply', number, data, observed_reply)
                    selected = state['armed'] and decoded and any(
                        op.get('op') == state['operation'] and (state['name'] is None or op.get('name') == state['name']) for op in decoded['operations'])
                    row = dict(connection=number, xid=xid, request=request, receive_id=state['received'],
                               reply_sha256=hashlib.sha256(data).hexdigest(), wire_bytes=len(wire))
                    if selected:
                        row['payload_hex'] = data.hex()
                        observed = reply(data)
                        row['reply'] = observed
                        if observed['status'] == 0 and any(op['op'] == state['operation'] and op['status'] == 0 for op in observed['operations']):
                            if len(pending) >= 128 or sum(len(v[1]) for v in pending) + len(wire) > 16 * 1048576:
                                raise ValueError('withheld reply bound')
                            pending.append((client, wire, row))
                            state['held'].append(row)
                            save()
                            continue
                    client.sendall(wire)
                    if request.get('decoded') and any(op.get('op') == state['operation'] and (state['name'] is None or op.get('name') == state['name']) for op in decoded['operations']):
                        row['payload_hex'] = data.hex()
                        row['reply'] = reply(data)
                        state['forwarded'].append(row)
                        state['forwarded'] = state['forwarded'][-128:]
                        save()
                    calls.pop(xid, None)
        except Exception as error:
            with lock:
                if isinstance(error, OSError) and client not in expected_disconnect:
                    event('response_transport_error', str(error))
                elif client not in expected_disconnect:
                    state['errors'].append('response: ' + str(error))
                save()
        finally:
            close_streams('backend_closed')

    listener = socket.create_server(('0.0.0.0', 2049), backlog=16)
    with lock:
        state['ready'] = True
        save()
    threading.Thread(target=controls, daemon=True).start()
    while True:
        client, _ = listener.accept()
        with lock:
            if state['active'] >= 16 or state['connections'] >= 400:
                client.close()
                if 'connection bound' not in state['errors']:
                    state['errors'].append('connection bound')
                save()
                continue
            state['connections'] += 1
            state['active'] += 1
            number = state['connections']
            save()
        threading.Thread(target=connection, args=(client, number), daemon=True).start()


if __name__ == '__main__':
    serve(sys.argv[1])
