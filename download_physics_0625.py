#!/usr/bin/env python3
"""Recursively download CAIE IGCSE Physics 0625 question papers.

Source folder:
https://pastpapers.papacambridge.com/papers/caie/igcse-physics-0625

The crawler follows only pages whose URL remains under the Physics 0625
folder, extracts direct PDF URLs from PapaCambridge's Download File links,
and downloads only official question-paper files by default.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_URL = "https://pastpapers.papacambridge.com/papers/caie/igcse-physics-0625"
DEFAULT_OUTPUT = "CAIE_IGCSE_Physics_0625_Question_Papers"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0 Safari/537.36"
)
PDF_MAGIC = b"%PDF-"
PRINT_LOCK = threading.Lock()
THREAD_LOCAL = threading.local()


@dataclass(frozen=True)
class Paper:
    session: str
    filename: str
    url: str
    source_page: str


def log(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": ROOT_URL,
        }
    )
    return session


def thread_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = make_session()
        THREAD_LOCAL.session = session
    return session


def normalize_page_url(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    # Some PapaCambridge links are written as "papers/caie/..." without a
    # leading slash. Repair the duplicated path produced by ordinary urljoin.
    while "/papers/caie/papers/caie/" in path:
        path = path.replace("/papers/caie/papers/caie/", "/papers/caie/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def resolve_href(page_url: str, href: str, document_base: str | None = None) -> str:
    href = href.strip()
    page = urlsplit(page_url)
    if href.startswith("papers/caie/"):
        return urljoin(f"{page.scheme}://{page.netloc}/", href)
    return urljoin(document_base or page_url, href)


def safe_component(value: str) -> str:
    value = unquote(value).strip().replace(" ", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "root"


def is_question_paper(filename: str, link_text: str = "") -> bool:
    name = filename.lower()
    text = link_text.lower()
    return bool(
        re.search(r"(?:^|_)qp(?:_|\.)", name)
        or "question-paper" in name
        or "question paper" in text
    )


def extract_direct_pdf(href: str, base_url: str, document_base: str | None = None) -> str | None:
    absolute = resolve_href(base_url, href, document_base)
    parsed = urlsplit(absolute)
    query = parse_qs(parsed.query)

    # PapaCambridge's Download File links contain the real URL in ?files=...
    for key in ("files", "file", "url"):
        values = query.get(key)
        if values:
            candidate = unquote(values[0]).strip()
            if candidate.lower().split("?", 1)[0].endswith(".pdf"):
                return candidate

    # Some pages may expose the PDF directly.
    if parsed.path.lower().endswith(".pdf"):
        return absolute
    return None


def session_from_page(page_url: str, root_url: str) -> str:
    page_path = urlsplit(page_url).path.rstrip("/")
    root_path = urlsplit(root_url).path.rstrip("/")
    root_slug = root_path.rsplit("/", 1)[-1]
    page_slug = page_path.rsplit("/", 1)[-1]

    if page_path == root_path:
        return "root"
    if page_slug.startswith(root_slug):
        suffix = page_slug[len(root_slug) :].lstrip("-")
        return safe_component(suffix)

    relative = page_path[len(root_path) :].strip("/")
    return safe_component(relative.replace("/", "__"))


def is_allowed_folder_page(candidate: str, root_url: str) -> bool:
    candidate_n = normalize_page_url(candidate)
    root_n = normalize_page_url(root_url)
    c = urlsplit(candidate_n)
    r = urlsplit(root_n)

    if c.scheme not in {"http", "https"} or c.netloc != r.netloc:
        return False
    if any(part in c.path.lower() for part in ("/viewer/", "download_file.php", "/directories/")):
        return False
    return c.path == r.path or c.path.startswith(r.path + "-") or c.path.startswith(r.path + "/")


def crawl(root_url: str, page_delay: float, max_pages: int) -> list[Paper]:
    session = make_session()
    root_url = normalize_page_url(root_url)
    queue: deque[str] = deque([root_url])
    visited: set[str] = set()
    papers_by_url: dict[str, Paper] = {}

    while queue:
        page_url = queue.popleft()
        if page_url in visited:
            continue
        if len(visited) >= max_pages:
            raise RuntimeError(
                f"Stopped after {max_pages} pages. Increase --max-pages only after checking the crawl scope."
            )

        visited.add(page_url)
        log(f"[crawl {len(visited):>3}] {page_url}")
        response = session.get(page_url, timeout=(20, 60))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        base_tag = soup.find("base", href=True)
        document_base = (
            resolve_href(page_url, base_tag.get("href", "")) if base_tag else page_url
        )
        session_name = session_from_page(page_url, root_url)

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            text = " ".join(anchor.stripped_strings)
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            direct_pdf = extract_direct_pdf(href, page_url, document_base)
            if direct_pdf:
                filename = safe_component(Path(urlsplit(direct_pdf).path).name)
                if filename.lower().endswith(".pdf") and is_question_paper(filename, text):
                    papers_by_url.setdefault(
                        direct_pdf,
                        Paper(
                            session=session_name,
                            filename=filename,
                            url=direct_pdf,
                            source_page=page_url,
                        ),
                    )
                continue

            candidate = normalize_page_url(resolve_href(page_url, href, document_base))
            if is_allowed_folder_page(candidate, root_url) and candidate not in visited:
                queue.append(candidate)

        if page_delay > 0:
            time.sleep(page_delay)

    papers = sorted(papers_by_url.values(), key=lambda p: (p.session, p.filename))
    log(f"\nDiscovered {len(papers)} unique question-paper PDFs across {len(visited)} pages.")
    return papers


def existing_is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == PDF_MAGIC
    except OSError:
        return False


def download_one(paper: Paper, output_dir: Path, overwrite: bool) -> tuple[Paper, str, int, str]:
    session_dir = output_dir / safe_component(paper.session)
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / paper.filename
    temp = target.with_suffix(target.suffix + ".part")

    if target.exists() and not overwrite and existing_is_pdf(target):
        return paper, "skipped-existing", target.stat().st_size, str(target)

    if temp.exists():
        temp.unlink()

    session = thread_session()
    with session.get(paper.url, timeout=(20, 180), stream=True, allow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        with temp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)

    if not existing_is_pdf(temp):
        preview = temp.read_bytes()[:160]
        temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Server did not return a valid PDF for {paper.filename}. "
            f"Content-Type={content_type!r}; first bytes={preview!r}"
        )

    os.replace(temp, target)
    return paper, "downloaded", target.stat().st_size, str(target)


def write_manifest(path: Path, rows: Iterable[dict[str, object]]) -> None:
    fieldnames = [
        "session",
        "filename",
        "url",
        "source_page",
        "status",
        "size_bytes",
        "local_path",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_zip(output_dir: Path, zip_path: Path) -> None:
    temp_zip = zip_path.with_suffix(zip_path.suffix + ".part")
    temp_zip.unlink(missing_ok=True)
    with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file_path in sorted(output_dir.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() == ".pdf":
                archive.write(file_path, file_path.relative_to(output_dir.parent))
        manifest = output_dir / "download_manifest.csv"
        if manifest.exists():
            archive.write(manifest, manifest.relative_to(output_dir.parent))
    os.replace(temp_zip, zip_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively download all CAIE IGCSE Physics 0625 question papers from PapaCambridge."
    )
    parser.add_argument("--root-url", default=ROOT_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=3, help="Parallel downloads (default: 3).")
    parser.add_argument("--page-delay", type=float, default=0.75, help="Delay between folder-page requests.")
    parser.add_argument("--max-pages", type=int, default=300, help="Crawl safety limit.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-zip", action="store_true", help="Do not create the final ZIP archive.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1 or args.workers > 8:
        print("--workers must be between 1 and 8", file=sys.stderr)
        return 2

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "download_manifest.csv"

    try:
        papers = crawl(args.root_url, max(args.page_delay, 0), args.max_pages)
    except Exception as exc:
        log(f"\nCrawl failed: {exc}")
        return 1

    if not papers:
        log("No question-paper PDFs were found. The website layout may have changed.")
        return 1

    rows: list[dict[str, object]] = []
    downloaded = skipped = failed = 0
    total = len(papers)

    log(f"\nDownloading into: {output_dir}")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(download_one, paper, output_dir, args.overwrite): paper
            for paper in papers
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            paper = future_map[future]
            try:
                _, status, size, local_path = future.result()
                if status == "downloaded":
                    downloaded += 1
                else:
                    skipped += 1
                log(f"[{index:>3}/{total}] {status:>16}  {paper.session}/{paper.filename}")
                rows.append(
                    {
                        "session": paper.session,
                        "filename": paper.filename,
                        "url": paper.url,
                        "source_page": paper.source_page,
                        "status": status,
                        "size_bytes": size,
                        "local_path": local_path,
                        "error": "",
                    }
                )
            except Exception as exc:
                failed += 1
                log(f"[{index:>3}/{total}] {'FAILED':>16}  {paper.session}/{paper.filename}: {exc}")
                rows.append(
                    {
                        "session": paper.session,
                        "filename": paper.filename,
                        "url": paper.url,
                        "source_page": paper.source_page,
                        "status": "failed",
                        "size_bytes": 0,
                        "local_path": "",
                        "error": str(exc),
                    }
                )
            write_manifest(manifest_path, sorted(rows, key=lambda r: (str(r["session"]), str(r["filename"]))))

    zip_path = output_dir.with_suffix(".zip")
    if not args.no_zip:
        log(f"\nCreating ZIP: {zip_path}")
        create_zip(output_dir, zip_path)

    log(
        f"\nFinished. Downloaded: {downloaded}; already present: {skipped}; failed: {failed}.\n"
        f"Manifest: {manifest_path}"
    )
    if not args.no_zip:
        log(f"ZIP: {zip_path}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
