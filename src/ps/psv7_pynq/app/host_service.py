"""Same-process LAN host. No PYNQ import, overlay loading or second owner."""
import copy
import hmac
import json
import mimetypes
import secrets
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


HOST_ASSETS = ('index.html', 'app.js', 'network-link.js', 'models-data.js', 'styles.css',
               'vendor/3dmol-min.js', 'vendor/3dmol_license.txt')


def validate_host_assets(root):
    """Check exact filename case and HTML routes, including on Windows."""
    host_root = Path(root) / 'host'
    for name in HOST_ASSETS:
        current = host_root
        for part in name.split('/'):
            if part not in {child.name for child in current.iterdir()}:
                raise FileNotFoundError('Host asset missing or case mismatch: ' + name)
            current = current / part
        if not current.is_file():
            raise FileNotFoundError('Host asset is not a file: ' + name)

    class AssetReferences(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            ref = attrs.get('src') if tag == 'script' else (
                attrs.get('href') if tag == 'link' and attrs.get('rel') == 'stylesheet' else None)
            if ref:
                url = urlsplit(ref)
                if url.scheme or url.netloc or url.path.lstrip('/') not in HOST_ASSETS:
                    raise ValueError('HTML asset has no local host route: ' + ref)

    AssetReferences().feed((host_root / 'index.html').read_text(encoding='utf-8'))
    return len(HOST_ASSETS)


class CommandError(Exception):
    def __init__(self, reason, code=409):
        super().__init__(reason)
        self.reason, self.code = reason, code


def local_hosts():
    names = {'localhost', '127.0.0.1', socket.gethostname().lower()}
    try:
        names.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    # Linux PYNQ can advertise every active IPv4 NIC without remote traffic.
    try:
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for _, name in socket.if_nameindex():
                try:
                    raw = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', name.encode()[:15]))
                    names.add(socket.inet_ntoa(raw[20:24]))
                except OSError:
                    pass
    except (ImportError, AttributeError, OSError):
        pass
    return names


class HostController:
    def __init__(self, app, root):
        self.app, self.root = app, Path(root)
        self.lock = threading.RLock()
        self.server_id = uuid.uuid4().hex
        self.accepting = True
        self.worker = None
        self.job = None
        self.revision = 0
        self.previous = None
        source = (self.root / 'host/models-data.js').read_text(encoding='utf-8')
        prefix = 'window.MOLECULE_DATA = '
        if not source.startswith(prefix) or not source.rstrip().endswith(';'):
            raise ValueError('Unexpected molecule data format')
        self.data = json.loads(source[len(prefix):].strip()[:-1])
        catalog = json.loads((self.root / 'assets/voice/catalog.json').read_text(encoding='utf-8'))['classes']
        self.models = {m['class_id']: m for m in self.data['models']}
        if len(self.models) != 22 or set(self.models) != set(range(22)):
            raise ValueError('Host requires the exact 22-class catalog')
        for item in catalog:
            model = self.models[item['class_id']]
            if (model['name_zh'], model['training_label'], model['formula']) != (item['name'], item['label'], item['formula']):
                raise ValueError('Host/native catalog mapping mismatch')
        if [str(label) for label in app.labels] != [self.models[i]['name_zh'] for i in range(22)]:
            raise ValueError('Host/application class order mismatch')
        with app.lock:
            status = app.audio.status()
            app.requests.ready(status['status'] & 31 == 3 and not status['control'] & 1,
                               app.voice_model.ready, bool(app.requests.status()['line_input']))

    def snapshot(self):
        # Never take app.lock: voice capture/inference holds it for seconds.
        with self.lock:
            with self.app.requests.lock:
                request = self.app.requests.status()
                timing = self.app.current_voice_timing(request) if hasattr(self.app, 'current_voice_timing') else None
                camera_timing = self.app.current_camera_timing(request) if hasattr(self.app, 'current_camera_timing') else None
            valid = bool(request.get('valid')) and request.get('class_id') in self.models
            model = self.models[request['class_id']] if valid else None
            source = {'CAMERA': 'camera', 'VOICE': 'voice', 'TEST': 'manual',
                      'EXTERNAL': 'manual', 'GOLDEN': 'reference', 'DEMO': 'reference'}.get(request.get('source'), 'none')
            if source == 'voice' and getattr(self.app, 'reference_voice_token', None) == (
                    2, request.get('request_epoch'), request.get('request_id')):
                source = 'reference'
            voice_alive = bool(self.app.voice_worker and self.app.voice_worker.is_alive())
            data = {'protocol_version': 1, 'server_id': self.server_id,
                    'mapping_version': self.data['mapping_version'],
                    'running': bool(self.app.running and not self.app.stop_event.is_set()),
                    'accepting': self.accepting, 'request': request,
                    'busy': bool(self.worker and self.worker.is_alive()) or voice_alive or bool(request.get('active')),
                    'voice_worker_alive': voice_alive,
                    'selection': {'valid': valid, 'class_id': model['class_id'] if model else None,
                                  'molecule_id': model['molecule_id'] if model else None,
                                  'name': model['name_zh'] if model else None, 'source': source},
                    'voice_timing': timing,
                    'camera_timing': camera_timing,
                    'job': copy.deepcopy(self.job), 'worker_error': self.app.worker_error}
            key = json.dumps(data, sort_keys=True, ensure_ascii=False)
            if key != self.previous:
                self.revision += 1
                self.previous = key
            data['revision'] = self.revision
            return data

    def command(self, body):
        if not isinstance(body, dict) or set(body) - {'command', 'value', 'server_id', 'mode_epoch', 'request_id'}:
            raise CommandError('INVALID_COMMAND', 400)
        name = body.get('command')
        if name not in ('mode', 'recognize', 'audio_input', 'select', 'clear', 'cancel'):
            raise CommandError('INVALID_COMMAND', 400)
        with self.lock:
            if not self.accepting or not self.app.running or self.app.stop_event.is_set():
                raise CommandError('APPLICATION_STOPPED')
            if body.get('server_id') != self.server_id:
                raise CommandError('STALE_SERVER')
            state = self.app.requests.status()
            if (type(body.get('mode_epoch')) is not int or type(body.get('request_id')) is not int or
                    body['mode_epoch'] != state['mode_epoch'] or body['request_id'] != state['request_id']):
                raise CommandError('STALE_STATE')
            value = body.get('value')
            if name == 'mode':
                if value not in ('camera', 'voice'):
                    raise CommandError('INVALID_MODE', 400)
                self.app.set_mode(value)
            elif name == 'cancel':
                self.app.cancel()
            else:
                # Clear interrupts immediately, but its hardware cleanup must
                # wait for existing work. Do not spawn a second clear worker.
                busy = self.snapshot()['busy']
                if name == 'clear' and busy:
                    self.app.cancel()
                    return {'ok': True, 'reason': 'CANCELLED', 'state': self.snapshot()}
                if busy:
                    raise CommandError('BUSY')
                if name == 'audio_input':
                    if value not in ('mic', 'linein'):
                        raise CommandError('INVALID_AUDIO_INPUT', 400)
                    self.app.requests.ready(bool(state['audio_ready']), bool(state['recognizer_ready']), value == 'linein')
                else:
                    if name == 'select' and (type(value) is not int or value not in self.models):
                        raise CommandError('INVALID_CLASS', 400)
                    if name == 'clear':
                        state = self.app.cancel()
                    epoch = state['mode_epoch']
                    mode, line_input = state['mode'], bool(state['line_input'])
                    self.job = {'id': uuid.uuid4().hex, 'command': name, 'state': 'running', 'error': None}
                    job_id = self.job['id']
                    def run():
                        error = None
                        try:
                            if name == 'recognize':
                                if mode == 'CAMERA':
                                    self.app.recognize(expected_epoch=epoch)
                                else:
                                    self.app.voice_once(line_input=line_input, expected_epoch=epoch)
                            elif name == 'select':
                                self.app.select(value, expected_epoch=epoch)
                            else:
                                self.app.clear(expected_epoch=epoch)
                        except Exception as failure:
                            error = str(failure)
                        finally:
                            with self.lock:
                                if self.job and self.job['id'] == job_id:
                                    cancelled = bool(error and self.app.requests.status().get('mode_epoch') != epoch)
                                    self.job.update(state='cancelled' if cancelled else 'error' if error else 'finished',
                                                    error=None if cancelled else error)
                    self.worker = threading.Thread(target=run, name='psv7-host-command', daemon=True)
                    self.worker.start()
            return {'ok': True, 'reason': 'ACCEPTED', 'state': self.snapshot()}

    def close(self, timeout=15):
        with self.lock:
            self.accepting = False
            self.app.cancel()
            worker = self.worker
        if worker is not None:
            worker.join(timeout)
            if worker.is_alive():
                raise RuntimeError('Host command still owns application state; keep session and retry stop')


class HostService:
    def __init__(self, app, root, host='0.0.0.0', port=8765, allowed_hosts=None):
        if not app.running:
            raise RuntimeError('Application must already be running')
        self.root, self.host, self.port = Path(root), host, port
        validate_host_assets(self.root)
        self.controller = HostController(app, root)
        self.token = secrets.token_urlsafe(32)
        self.allowed_hosts = local_hosts() | set(allowed_hosts or [])
        if host != '0.0.0.0':
            self.allowed_hosts.add(host)
        self.httpd = None
        self.thread = None
        self.assets = {}
        for name in HOST_ASSETS:
            file = self.root / 'host' / name
            self.assets['/' + name] = (file.read_bytes(), mimetypes.guess_type(name)[0] or 'application/octet-stream')
        self.assets['/'] = self.assets['/index.html']

    def start(self):
        if self.httpd is not None:
            raise RuntimeError('Host already started')
        service = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code, payload, content_type='application/json; charset=utf-8'):
                raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _valid_host(self):
                try:
                    value = urlsplit('http://' + self.headers.get('Host', ''))
                    return value.hostname in service.allowed_hosts and value.port == service.port
                except ValueError:
                    return False

            def do_GET(self):
                if not self._valid_host():
                    return self._reply(403, {'ok': False, 'reason': 'INVALID_HOST'})
                path = urlsplit(self.path).path
                if path in ('/api/connect', '/api/state'):
                    result = {'ok': True, 'state': service.controller.snapshot()}
                    if path == '/api/connect':
                        result['token'] = service.token
                    return self._reply(200, result)
                if path in service.assets:
                    raw, mime = service.assets[path]
                    return self._reply(200, raw, mime)
                self._reply(404, {'ok': False, 'reason': 'NOT_FOUND'})

            def do_POST(self):
                if not self._valid_host():
                    return self._reply(403, {'ok': False, 'reason': 'INVALID_HOST'})
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + self.headers.get('Host', ''):
                    return self._reply(403, {'ok': False, 'reason': 'INVALID_ORIGIN'})
                if not hmac.compare_digest(self.headers.get('X-PSV7-Token', ''), service.token):
                    return self._reply(403, {'ok': False, 'reason': 'INVALID_TOKEN'})
                if urlsplit(self.path).path != '/api/command':
                    return self._reply(404, {'ok': False, 'reason': 'NOT_FOUND'})
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self._reply(415, {'ok': False, 'reason': 'JSON_REQUIRED'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2048:
                        raise ValueError('length')
                    body = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeDecodeError):
                    return self._reply(400, {'ok': False, 'reason': 'INVALID_JSON'})
                try:
                    result = service.controller.command(body)
                    self._reply(200, result)
                except CommandError as error:
                    self._reply(error.code, {'ok': False, 'reason': error.reason, 'state': service.controller.snapshot()})
                except Exception:
                    self._reply(500, {'ok': False, 'reason': 'APPLICATION_ERROR'})

            def setup(self):
                super().setup()
                self.connection.settimeout(3)

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        server.daemon_threads = True
        self.httpd = server
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1},
                                       name='psv7-host-http', daemon=True)
        self.thread.start()
        return self.info()

    def info(self):
        hosts = sorted(self.allowed_hosts if self.host == '0.0.0.0' else {self.host})
        return {'host_running': bool(self.thread and self.thread.is_alive()),
                'port': self.port, 'urls': ['http://%s:%s/' % (name, self.port) for name in hosts],
                'server_id': self.controller.server_id, 'hardware_owner': 'existing_notebook_session'}

    def stop(self):
        # Disable before waiting; cancellation uses the request lock, never the
        # expensive app lock. A timeout is reported rather than releasing BOs.
        self.controller.close()
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join(3)
            if self.thread.is_alive():
                raise RuntimeError('Host HTTP thread did not stop')
            self.httpd = None
        return {'host_running': False, 'http_thread_alive': bool(self.thread and self.thread.is_alive()),
                'command_thread_alive': bool(self.controller.worker and self.controller.worker.is_alive()),
                'server_id': self.controller.server_id}
