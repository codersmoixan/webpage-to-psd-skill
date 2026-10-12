"""Serve a local static project on loopback for browser-to-PSD capture."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import quote


class ProjectHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript', '.mjs': 'text/javascript',
        '.css': 'text/css', '.svg': 'image/svg+xml',
        '.woff': 'font/woff', '.woff2': 'font/woff2',
    }

    def translate_path(self, path):
        resolved = Path(super().translate_path(path)).resolve()
        root = Path(self.directory).resolve()
        if not resolved.is_relative_to(root):
            raise PermissionError('Requested path is outside the project directory')
        return str(resolved)

    def send_head(self):
        try:
            return super().send_head()
        except PermissionError:
            self.send_error(403, 'Path is outside the project directory')
            return None

    def list_directory(self, path):
        self.send_error(404, 'No index.html in this directory')
        return None


def make_server(project_dir, entry='index.html', port=0):
    root = Path(project_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Project path must be a directory')
    entry_path = Path(entry)
    if entry_path.is_absolute():
        raise ValueError('--entry must be relative to the project directory')
    target = (root / entry_path).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError('Entry must be a file inside the project directory')
    if target.suffix.lower() not in ('.html', '.htm'):
        raise ValueError('Entry must be an HTML file')
    handler = partial(ProjectHandler, directory=str(root))
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    actual_port = server.server_address[1]
    relative = target.relative_to(root).as_posix()
    source = {
        'kind': 'local-static-project', 'projectDirectory': str(root),
        'entry': relative, 'url': f'http://127.0.0.1:{actual_port}/{quote(relative, safe="/")}',
        'port': actual_port, 'bindAddress': '127.0.0.1',
    }
    return server, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, required=True)
    parser.add_argument('--entry', default='index.html')
    parser.add_argument('--port', type=int, default=0,
                        help='0 selects an available port automatically')
    parser.add_argument('--job-dir', type=Path,
                        help='Record local_source.json in the PSD job directory')
    args = parser.parse_args()
    try:
        server, source = make_server(args.project_dir, args.entry, args.port)
    except (ValueError, OSError) as error:
        parser.exit(2, f'Cannot serve static project: {error}\n')
    try:
        if args.job_dir:
            args.job_dir.mkdir(parents=True, exist_ok=True)
            (args.job_dir / 'local_source.json').write_text(json.dumps(source, indent=2))
        print(json.dumps(source), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print('Static project server stopped.', file=sys.stderr)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
