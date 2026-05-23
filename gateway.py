import http.server
import socketserver
import urllib.request
import urllib.error
import os
import sys

# =========================================================================
# CONFIGURATION
# Update this with the actual Local LAN IP address of your Windows 11 machine.
# Make sure your Windows 11 machine is on the same local router/net.
# =========================================================================
WINDOWS_IP = "192.168.1.100"  # <-- CHANGE THIS to your Windows 11 local IP
WINDOWS_PORT = 8000            # Port the Windows FastAPI server runs on
PORT = 8080                    # Port to expose publicly on your Raspberry Pi

class GatewayHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path.startswith('/api/'):
            self.proxy_request('POST')
        else:
            super().do_POST()

    def do_GET(self):
        if self.path.startswith('/api/'):
            self.proxy_request('GET')
        else:
            super().do_GET()

    def proxy_request(self, method):
        # Build target URL on Windows machine
        url = f"http://{WINDOWS_IP}:{WINDOWS_PORT}{self.path}"
        
        # Read request body for POST methods
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        
        # Strip hostile headers or host-specific configurations
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')}
        
        req = urllib.request.Request(url, data=post_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                for k, v in response.getheaders():
                    # Forward response headers back to browser
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as e:
            # If the backend returned an HTTP error (e.g. 400 Aborted)
            self.send_response(e.code)
            for k, v in e.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            # If the Windows 11 machine is off, asleep, or unreachable
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Gateway Error: Windows 11 backend is unreachable.\nDetails: {e}".encode())

if __name__ == '__main__':
    # Verify that the static directory exists next to the script
    if not os.path.exists('static'):
        print("ERROR: Please run this script in the directory containing the 'static' folder.")
        print(f"Current Directory: {os.getcwd()}")
        sys.exit(1)
        
    print("=====================================================================")
    print("                FOE CITY REDESIGNER RASPBERRY PI GATEWAY             ")
    print("=====================================================================")
    print(f" * Public Port: http://0.0.0.0:{PORT} (Expose this to the internet)")
    print(f" * Windows 11 Backend: http://{WINDOWS_IP}:{WINDOWS_PORT}")
    print("=====================================================================")
    print("Press CTRL+C to stop the gateway.")
    
    # Allow address reuse to avoid port blockages on restarts
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), GatewayHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down gateway...")
