"""Exercise redirect handling against real local HTTP listeners."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import diagnostics


class TelemetryRedirectTest(unittest.TestCase):
    def server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.addCleanup(cleanup)
        return 'http://127.0.0.1:' + str(server.server_port)

    def test_redirect_never_reaches_destination_or_forwards_bearer(self):
        destination_headers = []
        source_headers = []

        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                destination_headers.append(dict(self.headers))
                self.send_response(204)
                self.end_headers()
            do_POST = do_GET
            def log_message(self, *_args):
                pass

        destination = self.server(Destination)
        redirect_status = 302

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                source_headers.append(self.headers.get('Authorization'))
                self.send_response(redirect_status)
                self.send_header('Location', destination + '/events')
                self.end_headers()
            def log_message(self, *_args):
                pass

        source = self.server(Redirect)
        for redirect_status in (301, 302, 303, 307, 308):
            with self.subTest(status=redirect_status):
                destination_headers.clear()
                result = diagnostics.send_remote_event({}, source + '/events', 'test-secret')
                self.assertEqual(destination_headers, [], 'redirect leaked request headers: ' + str(destination_headers))
                self.assertEqual(result, 'TELEMETRY_HTTP_' + str(redirect_status))
        self.assertEqual(source_headers, ['Bearer test-secret'] * 5)
