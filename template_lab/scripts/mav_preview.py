from __future__ import annotations

import argparse
import http.server
import socketserver
from functools import partial

from mav_schema import LAB_ROOT, read_json, run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a generated MAV preview.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-server", action="store_true", help="Only print the preview URL")
    return parser.parse_args()


def preview_url(run_id: str, port: int) -> str:
    path = run_dir(run_id)
    manifest_path = path / "preview_manifest.json"
    if not manifest_path.exists():
        manifest_path = path / "preview_manifest_v3.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing preview manifest for run: {path}")
    manifest = read_json(manifest_path)
    return f"http://127.0.0.1:{port}/runs/{path.name}/{manifest['master']}"


def main() -> None:
    args = parse_args()
    url = preview_url(args.run_id, args.port)
    print(f"MAV preview: {url}")
    if args.no_server:
        return
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(LAB_ROOT))
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as server:
        print("Serving Template Lab root. Press Ctrl+C to stop.")
        server.serve_forever()


if __name__ == "__main__":
    main()
