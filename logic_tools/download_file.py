"""
universal_downloader.py — Universal File Downloader

Give it a webpage URL. It finds downloadable files on that page
(.exe, .pdf, .jpg, .zip, .mp4, .docx, ...) and downloads them for you.

Usage:
    python universal_downloader.py                               # interactive mode
    python universal_downloader.py <url>                         # step 1: scan + list (cached)
    python universal_downloader.py <url> 3                       # step 2: download serial 3
    python universal_downloader.py <url> 1,2,3                   # step 2: download several
    python universal_downloader.py <url> [1,2,3]                 # brackets also accepted
    python universal_downloader.py <url> --ext pdf,exe           # filter extensions
    python universal_downloader.py <url> --out ./downloads       # output folder
    python universal_downloader.py <url> --browser               # render JS with Playwright
    python universal_downloader.py <url> --debug                 # save raw HTML for inspection
    python universal_downloader.py <direct-file-or-drive-link>   # downloads directly

Host handling: the URL is tried exactly as given (apex domain first).
If that host is unreachable or bounces to the homepage, it automatically
retries once with the www. variant (and vice versa).

Requirements:
    pip install requests beautifulsoup4
    # optional, for JavaScript-heavy pages:
    pip install playwright && playwright install chromium
"""

import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# Live progress bar only on a real terminal; piped output gets milestone lines
IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

DEFAULT_EXTENSIONS = (
    # executables / installers
    "exe", "msi", "apk", "dmg", "pkg", "deb", "rpm", "iso",
    # documents
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt", "epub",
    # archives
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
    # images
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "tiff",
    # audio / video
    "mp3", "wav", "flac", "ogg", "m4a", "mp4", "mkv", "avi", "mov", "webm",
)

# Browser-like headers so servers don't 403 us for looking like a bot
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# A URL "looks like a file" if its path ends with .ext / .ext?query.
# Matches absolute (http...) AND relative (files/report.pdf) paths.
FILE_URL_RE = r"(?:https?://[^\s\"'<>]+|[\w./~+-]+)\.({exts})(?:[?#][^\s\"'<>]*)?"

# Attributes that commonly hold a file URL on a tag
LINK_ATTRS = ("href", "src", "data-src", "data-href", "data-url",
              "data-file", "data-download", "poster", "data-original")


# ----------------------------------------------------------------------------
# URL handling
# ----------------------------------------------------------------------------

def normalize_url(url):
    """Ensure a scheme is present. Host form (www vs apex) is left exactly
    as given — fetch_page_html handles the fallback at request time."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def alt_host_url(url):
    """Same URL on the opposite host form (www.x <-> x). None for IPs/localhost."""
    p = urlparse(url)
    host = p.netloc
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host.split(":")[0]) or host.startswith("localhost"):
        return None
    if host.startswith("www."):
        bare = host[4:]
        return url.replace(f"//{host}", f"//{bare}", 1)
    return url.replace(f"//{host}", f"//www.{host}", 1)


def cache_key(url):
    """Canonical cache key: same entry whether the caller passed www or not."""
    return re.sub(r"//(www\.)", "//", url, count=1).rstrip("/")


# ----------------------------------------------------------------------------
# Link discovery
# ----------------------------------------------------------------------------

def looks_like_file(url, extensions):
    """True if the URL path ends with one of the wanted extensions."""
    path = urlparse(url).path.lower()
    return any(path.endswith("." + e) for e in extensions)


def is_direct_file_url(url, session=None):
    """True if this URL itself serves a file: extension match, or a HEAD
    probe shows non-HTML content (covers extension-less download links)."""
    if looks_like_file(url, DEFAULT_EXTENSIONS):
        return True
    try:
        s = session or requests.Session()
        r = s.head(url, headers=HEADERS, allow_redirects=True, timeout=15)
        if r.status_code >= 400:
            return False
        ctype = r.headers.get("Content-Type", "").lower()
        return not ("text/html" in ctype or "application/xhtml" in ctype)
    except requests.RequestException:
        return False


def extract_links_from_html(html, page_url, extensions):
    """Collect candidate file URLs from raw HTML + parsed DOM."""
    found = {}  # url -> source description (keeps order, dedupes)

    # 1) DOM: check every relevant attribute on every tag
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        for attr in LINK_ATTRS:
            val = tag.get(attr)
            if not val or not isinstance(val, str):
                continue
            # Some frameworks wrap the real path inside a query param
            # e.g. /_next/image?url=%2Ffiles%2Freport.pdf&w=800
            if "url=" in val:
                m = re.search(r"[?&]url=([^&]+)", val)
                if m:
                    val = unquote(m.group(1))
            full = urljoin(page_url, val)
            if looks_like_file(full, extensions):
                label = (tag.get_text(strip=True) or
                         tag.get("download") or
                         tag.get("alt") or tag.name)
                found.setdefault(full, label)

    # 2) Raw regex sweep: catches URLs inside <script>, onclick=, JSON blobs
    pattern = re.compile(FILE_URL_RE.format(exts="|".join(extensions)),
                         re.IGNORECASE)
    for m in pattern.finditer(html):
        full = urljoin(page_url, m.group(0).strip('"\''))
        if looks_like_file(full, extensions):
            found.setdefault(full, "(embedded in page source)")

    # 3) <meta http-equiv="refresh"> style redirects
    for m in re.finditer(r'content=["\']\s*\d+\s*;\s*url=([^"\']+)', html,
                         re.IGNORECASE):
        full = urljoin(page_url, m.group(1))
        if looks_like_file(full, extensions):
            found.setdefault(full, "(meta redirect)")

    # 4) Known file-hosting patterns (regardless of extension tail)
    for m in re.finditer(r'https?://drive\.google\.com/file/d/([\w-]+)', html):
        fid = m.group(1)
        found.setdefault(drive_direct_url(fid), "(google drive)")

    return found

def drive_direct_url(file_id):
    """Convert a Drive view/share link to a direct-download URL."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def drive_confirm_url(html, base):
    """Extract the confirm-download URL from Drive's virus-scan interstitial."""
    m = re.search(r'action="([^"]+)"', html)
    if m and "usercontent" in m.group(1) or (m and "export=download" in m.group(1)):
        return m.group(1).replace("&amp;", "&")
    m = re.search(r'href="(/download\?[^"]+|https://drive\.usercontent[^"]+)"', html)
    if m:
        return urljoin(base, m.group(1).replace("&amp;", "&"))
    return None


def fetch_page_html(page_url, use_browser=False, timeout=30, _alt_tried=False):
    """Fetch page HTML. Optionally render JavaScript via Playwright.

    Host fallback: the URL is tried as given. If the host is unreachable
    (DNS miss) or the request gets bounced to a bare homepage, it retries
    once on the opposite host form (www <-> apex). _alt_tried prevents loops.
    """
    if use_browser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("Playwright is not installed.\n"
                     "Run:  pip install playwright && playwright install chromium")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(page_url, wait_until="networkidle", timeout=timeout * 1000)
            page.wait_for_timeout(2000)  # let lazy content settle
            html = page.content()
            browser.close()
            return html

    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.ConnectionError:
        alt = None if _alt_tried else alt_host_url(page_url)
        if alt:
            print(f"  Host unreachable — retrying with: {alt}")
            return fetch_page_html(alt, use_browser, timeout, True)
        raise
    if resp.url.rstrip("/") != page_url.rstrip("/"):
        print(f"  NOTE: redirected to {resp.url}")
        # Asked for a deep link, got the front door? Try the other host form.
        if not _alt_tried and urlparse(resp.url).path in ("", "/"):
            alt = alt_host_url(page_url)
            if alt:
                print(f"  Bounced to homepage — retrying with: {alt}")
                return fetch_page_html(alt, use_browser, timeout, True)
    return resp.text


# ----------------------------------------------------------------------------
# Downloading
# ----------------------------------------------------------------------------

def filename_from_response(url, resp):
    """Prefer the server-provided filename, else derive one from the URL."""
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd, re.IGNORECASE)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
    return name or "downloaded_file"


def unique_path(folder, filename):
    """Avoid overwriting: report.pdf -> report (1).pdf"""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    n = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return candidate


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def resolve_true_url(url, resp, session=None, extensions=DEFAULT_EXTENSIONS):
    """If the response is actually an HTML download page, extract the real file URL."""
    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" not in ctype:
        return None
    # Drive confirm pages must be handled by the Drive branch, not ranked here
    if "drive.google.com" in url:
        return None
    # peek at the body without consuming the stream
    raw = resp.raw.read(65536, decode_content=True)
    if not raw.lstrip().lower().startswith(b"<!doctype html") and b"<html" not in raw[:200].lower():
        return None
    html = raw.decode("utf-8", errors="replace")
    candidates = []
    # meta refresh redirect
    for m in re.finditer(r'http-equiv=["\']?refresh["\']?[^>]*url=([^"\'>\s]+)', html, re.IGNORECASE):
        candidates.append(urljoin(url, unquote(m.group(1))))
    # direct file links in href/src/embedded URLs
    pattern = re.compile(FILE_URL_RE.format(exts="|".join(DEFAULT_EXTENSIONS)), re.IGNORECASE)
    for m in pattern.finditer(html):
        candidates.append(urljoin(url, m.group(0).strip('"\'')))
    # JS location redirects
    for m in re.finditer(r'(?:window\.)?location(?:\.href)?\s*=\s*["\']([^"\']+)', html):
        candidates.append(urljoin(url, m.group(1)))
    # dedupe, keep order
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]
    # filter to real files, then rank:
    # 1) basename matches the original URL's filename
    # 2) larger Content-Length wins (real downloads beat icons/images)
    orig_name = unquote(urlparse(url).path.rstrip("/").split("/")[-1]).lower()
    s = session or requests.Session()
    valid = []
    for c in candidates:
        if not looks_like_file(c, DEFAULT_EXTENSIONS):
            continue
        try:
            r = s.head(c, headers=HEADERS, allow_redirects=True, timeout=15)
            ctype = r.headers.get("Content-Type", "").lower()
            if "text/html" in ctype or "application/xhtml" in ctype:
                continue
            try:
                size = int(r.headers.get("Content-Length") or 0)
            except ValueError:
                size = 0
        except requests.RequestException:
            continue
        cname = unquote(urlparse(c).path.rstrip("/").split("/")[-1]).lower()
        ext_match = any(cname.endswith("." + e) for e in extensions)
        score = (1 if ext_match else 0, 1 if cname == orig_name else 0, size)
        valid.append((score, c, size))
    if not valid:
        return None
    valid.sort(key=lambda t: t[0], reverse=True)
    best = valid[0]
    print(f"  Selected: {unquote(urlparse(best[1]).path.split('/')[-1])} "
          f"({human(best[2]) if best[2] else 'size unknown'})")
    return best[1]


def download_file(url, out_folder, timeout=60, retries=3, _hop=0, session=None,
                  extensions=DEFAULT_EXTENSIONS):
    """Stream-download one file with a progress bar and retries."""
    for attempt in range(1, retries + 1):
        try:
            s = session or requests.Session()
            with s.get(url, headers=HEADERS, stream=True,
                       timeout=timeout, allow_redirects=True) as resp:
                resp.raise_for_status()
                true_url = None if _hop else resolve_true_url(url, resp, s,
                                                               extensions)
                ctype_now = resp.headers.get("Content-Type", "").lower()
                # Drive interstitial: "can't scan this file for viruses" page
                if (not true_url and "text/html" in ctype_now
                        and ("drive.google.com" in url
                             or "drive.usercontent.google.com" in url)):
                    peek = resp.raw.read(262144, decode_content=True)
                    cu = drive_confirm_url(peek.decode("utf-8", errors="replace"), url)
                    if cu:
                        print(f"\n  Drive confirm page detected. Following: {cu}")
                        if _hop >= 3:
                            print("  Too many redirects; giving up.")
                            return None
                        return download_file(cu, out_folder, timeout,
                                             retries, _hop + 1, s, extensions)
                if not true_url and "text/html" in ctype_now:
                    print("\n  HTML page, no valid file link found inside. Aborting this URL.")
                    return None
                if true_url:
                    print(f"\n  HTML download page detected.")
                    print(f"  Following true download URL: {true_url}")
                    if _hop >= 3:
                        print("  Too many redirects; giving up.")
                        return None
                    return download_file(true_url, out_folder, timeout,
                                         retries, _hop + 1, s, extensions)
                filename = filename_from_response(url, resp)
                dest = unique_path(out_folder, filename)
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                with open(dest, "wb") as f:
                    last_milestone = 0
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            if total:
                                pct = done * 100 // total
                                if IS_TTY:
                                    sys.stdout.write(
                                        f"\r  [{pct:3d}%] {human(done)} / {human(total)}")
                                    sys.stdout.flush()
                                elif pct // 25 > last_milestone:
                                    last_milestone = pct // 25
                                    print(f"  [{last_milestone * 25}%] "
                                          f"{human(done)} / {human(total)}")
                print(f"\n  Saved: {os.path.abspath(dest)}"
                      + (f" ({human(done)})" if done else ""))
                return dest
        except requests.RequestException as e:
            print(f"\n  Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    print(f"  FAILED permanently: {url}")
    return None


# ----------------------------------------------------------------------------
# Scan + cache
# ----------------------------------------------------------------------------

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "_dl_cache.json")

def prompt(msg, default=""):
    val = input(f"{msg}{(' [' + default + ']') if default else ''}: ").strip()
    return val or default

def list_files(items):
    print(f"\nFound {len(items)} candidate file(s):\n")
    for i, (u, label) in enumerate(items, 1):
        name = unquote(urlparse(u).path.rstrip("/").split("/")[-1])
        if "drive.google.com" in u:
            fid = re.search(r"id=([\w-]+)", u)
            name = f"drive:{fid.group(1)[:20]}" if fid else "drive file"
        print(f"  {i:>2}. {name:<45} {label[:40]}")

def scan(url, extensions, use_browser=False, debug=False):
    print(f"Scanning: {url}")
    try:
        html = fetch_page_html(url, use_browser=use_browser)
    except requests.RequestException as e:
        print(f"Could not fetch the page: {e}")
        return []
    if debug:
        with open("_last_scan.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  (debug: server response saved to _last_scan.html, "
              f"{len(html)} chars)")
    links = extract_links_from_html(html, url, extensions)
    if not links:
        print("No matching files found.")
        if not use_browser:
            print("Tip: rerun with --browser for JS-heavy pages.")
        return []
    items = list(links.items())
    list_files(items)
    return items

def save_cache(key, items):
    try:
        cache = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        cache[key] = [list(x) for x in items]
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"  (cache save failed: {e})")

def load_cache(key):
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        return [tuple(x) for x in cache.get(key, [])]
    except Exception:
        return []


# ----------------------------------------------------------------------------
# Arg mode (step 1 list / step 2 download by serial list)
# ----------------------------------------------------------------------------

def parse_serials(token):
    """Parse '3' / '1,2,3' / '[1, 2, 3]' into a list of ints, else None."""
    cleaned = token.strip().strip("[]").strip()
    if not cleaned:
        return None
    parts = [p.strip() for p in re.split(r"[,\s]+", cleaned) if p.strip()]
    if parts and all(p.isdigit() for p in parts):
        return [int(p) for p in parts]
    return None

def parse_args(argv):
    """<url> [serials] [--ext e1,e2] [--out dir] [--browser] [--debug] — any order."""
    url, serials, exts = None, None, None
    out, use_browser, debug = "downloads", False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--ext" and i + 1 < len(argv):
            exts = tuple(e.strip().lower().lstrip(".")
                         for e in argv[i + 1].split(",") if e.strip())
            i += 2
        elif a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
        elif a == "--browser":
            use_browser = True
            i += 1
        elif a == "--debug":
            debug = True
            i += 1
        elif a.startswith("--"):
            sys.exit(f"Unknown option: {a}")
        else:
            serials_parsed = parse_serials(a)
            if serials_parsed:
                serials = (serials or []) + serials_parsed
                i += 1
            elif url is None:
                url = a
                i += 1
            else:
                sys.exit(f"Unexpected extra argument: {a}")
    return url, serials, exts, out, use_browser, debug

def run_args(argv):
    url, serials, exts, out, use_browser, debug = parse_args(argv)
    if not url:
        print("Usage: python universal_downloader.py <url> [serials] "
              "[--ext pdf,exe] [--out dir] [--browser] [--debug]\n"
              "  serials: one number (3) or a list (1,2,3 or [1,2,3])")
        return
    url = normalize_url(url)
    extensions = exts or DEFAULT_EXTENSIONS

    # Direct file link? (Drive /view links, raw .pdf/.zip URLs, or any
    # extension-less URL whose server answers with a file) — skip scanning.
    m = re.search(r'drive\.google\.com/file/d/([\w-]+)', url)
    if m:
        target = drive_direct_url(m.group(1))
    elif is_direct_file_url(url):
        target = url
    else:
        target = None
    if target:
        os.makedirs(out, exist_ok=True)
        print("Direct file link detected — downloading directly.")
        if download_file(target, out, extensions=extensions):
            print("\nDone.")
        else:
            print("\nDownload failed.")
        return

    key = cache_key(url)

    if not serials:
        # ---- STEP 1: scan, list, cache ----
        items = scan(url, extensions, use_browser, debug)
        if items:
            save_cache(key, items)
            print("\nStep 1 done. Re-run with the same URL + serial number(s) "
                  "to download, e.g.  1,2,3")
        return

    # ---- STEP 2: download serial(s) from the cached scan ----
    serials = list(dict.fromkeys(serials))  # dedupe, keep order
    items = load_cache(key)
    if not items:
        print("No cached scan for this URL — rescanning...")
        items = scan(url, extensions, use_browser, debug)
        if items:
            save_cache(key, items)
    if not items:
        return
    bad = [n for n in serials if not 1 <= n <= len(items)]
    if bad:
        print(f"Invalid serial(s) {bad}. 1-{len(items)} available. "
              f"Run without serials to list files.")
        return

    os.makedirs(out, exist_ok=True)
    print(f"\nDownloading {len(serials)} file(s) to '{out}/' ...")
    ok = fail = 0
    for pos, n in enumerate(serials, 1):
        target = items[n - 1][0]
        name = unquote(urlparse(target).path.split("/")[-1]) or target
        print(f"\n[{pos}/{len(serials)}] #{n}: {name}")
        if download_file(target, out, extensions=extensions):
            ok += 1
        else:
            fail += 1
        time.sleep(0.5)
    print(f"\nDone. {ok} downloaded, {fail} failed.")


# ----------------------------------------------------------------------------
# Interactive mode
# ----------------------------------------------------------------------------

def interactive():
    """Run with no arguments to use it."""
    print("=== universal_downloader.py interactive mode (Ctrl+C to quit) ===")
    while True:
        try:
            url = prompt("\nPage URL (or direct file/Drive link)").strip()
            if not url:
                continue
            url = normalize_url(url)

            m = re.search(r'drive\.google\.com/file/d/([\w-]+)', url)
            if m:
                url = drive_direct_url(m.group(1))
            if "drive.google.com" in url or is_direct_file_url(url):
                out = prompt("Output folder", "downloads")
                os.makedirs(out, exist_ok=True)
                print("\nDirect file link — downloading.")
                download_file(url, out)
                continue

            ext_raw = prompt("Extensions (comma sep, Enter = default list)")
            browser = prompt("Render with browser? y/n", "n").lower() == "y"
            out = prompt("Output folder", "downloads")

            extensions = tuple(
                e.strip().lower().lstrip(".")
                for e in (ext_raw.split(",") if ext_raw else DEFAULT_EXTENSIONS)
                if e.strip()
            )

            items = scan(url, extensions, browser)
            if not items:
                continue

            raw = prompt("Download? (numbers like 1,3 | all | Enter = first)")
            if raw.lower() in ("all", "a"):
                chosen = items
            elif not raw:
                chosen = items[:1]
            else:
                idxs = [int(p) for p in raw.replace(",", " ").split()
                        if p.isdigit() and 1 <= int(p) <= len(items)]
                chosen = [items[n - 1] for n in dict.fromkeys(idxs)] or items[:1]

            os.makedirs(out, exist_ok=True)
            print(f"\nDownloading {len(chosen)} file(s) to '{out}/' ...")
            ok = fail = 0
            for u, _ in chosen:
                print(f"\n> {unquote(urlparse(u).path.split('/')[-1])}")
                if download_file(u, out, extensions=extensions):
                    ok += 1
                else:
                    fail += 1
                time.sleep(0.5)

            print(f"\nDone. {ok} downloaded, {fail} failed.")

        except KeyboardInterrupt:
            print("\nExiting.")
            return
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_args(sys.argv[1:])
    else:
        interactive()