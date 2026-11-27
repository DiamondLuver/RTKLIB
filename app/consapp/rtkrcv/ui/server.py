#!/usr/bin/env python3
"""Web UI for rtkrcv.

Edits an rtkrcv options file (conf/single.conf by default) in place and
starts/stops/monitors rtkrcv through its telnet console.

    python3 server.py [--conf FILE] [--port N] [--no-open]

Stream logins are not kept in the options file: rtkrcv fills ${NAME} in stream
paths from the environment or from the nearest .env file, in the folder of the
options file or a folder above it.

Only the standard library is used. The server listens on 127.0.0.1 only.
"""
import argparse
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
RTKRCV_DIR = os.path.dirname(HERE)
DEFAULT_CONF = os.path.join(RTKRCV_DIR, "conf", "single.conf")
RUN_DIR = os.path.join(RTKRCV_DIR, "gcc")       # rtkrcv is started from here
BINARY = os.path.join(RUN_DIR, "rtkrcv")
PROMPT = "rtkrcv> "

# ----------------------------------------------------------------------------
# options file
# ----------------------------------------------------------------------------
LINE_RE = re.compile(r"^(?P<head>\s*(?P<key>[A-Za-z0-9_]+-[A-Za-z0-9_\-]+)\s*=)(?P<rest>.*)$")

GROUPS = [
    ("inpstr", "Input streams"),
    ("outstr", "Output streams"),
    ("logstr", "Log streams"),
    ("pos1", "Positioning"),
    ("pos2", "Ambiguity and filter"),
    ("out", "Solution format"),
    ("stats", "Statistics"),
    ("ant1", "Rover antenna"),
    ("ant2", "Base antenna"),
    ("file", "Files"),
    ("misc", "Miscellaneous"),
    ("console", "Console"),
]
STREAM_NAMES = {
    "inpstr1": "Rover", "inpstr2": "Base station", "inpstr3": "Correction",
    "outstr1": "Solution 1", "outstr2": "Solution 2",
    "logstr1": "Rover log", "logstr2": "Base station log", "logstr3": "Correction log",
}


def split_eol(line):
    body = line.rstrip("\r\n")
    return body, line[len(body):]


def parse_hint(comment, fmt=None):
    """Interpret an option's choice/unit text.

    "(0:off,1:on)"        -> enum    (value written as the name)
    "(1:gps+2:sbas+...)"  -> flags   (value written as the numeric sum)
    "(deg)"               -> unit
    anything else         -> note

    fmt is the option type from the rtklib option table (0:int, 1:double,
    2:string, 3:enum) when the option is known, else None.
    """
    hint = {"kind": "text", "unit": "", "note": "", "choices": []}
    text = comment.strip()
    m = re.match(r"^\((.*)\)$", text)
    if not m:
        hint["note"] = text
        return hint
    inner = m.group(1).strip()
    parts = re.split(r"([,+])(?=\d+:)", inner)
    items, seps = parts[0::2], parts[1::2]
    choices = []
    for it in items:
        mm = re.match(r"^(\d+):(.+)$", it.strip())
        if not mm:
            choices = []
            break
        choices.append({"num": int(mm.group(1)), "name": mm.group(2).strip()})
    if len(choices) >= 2 and fmt in (None, 0, 3):
        hint["choices"] = choices
        hint["kind"] = "flags" if "+" in seps and fmt != 3 else "enum"
    else:
        hint["unit"] = inner
    return hint


def load_schema():
    """Option tables of this rtkrcv build, read from the C sources.

    The comments in an options file can be older than the program, so the
    valid choices are taken from src/options.c and rtkrcv.c instead.
    Returns {name: {"fmt": int, "comment": str}}; empty if unreadable.
    """
    schema = {}
    sources = [os.path.join(RTKRCV_DIR, "..", "..", "..", "src", "options.c"),
               os.path.join(RTKRCV_DIR, "rtkrcv.c")]
    entry = re.compile(r'^\s*\{"([A-Za-z0-9_\-]+)",\s*(\d),\s*\(void \*\)[^,]+,\s*("[^"]*"|[A-Za-z0-9_]+)\s*\}',
                       re.M)
    for src in sources:
        try:
            with open(src, "r", encoding="latin-1") as f:
                text = f.read()
        except OSError:
            continue
        macros = dict(re.findall(r'^#define\s+([A-Z0-9_]+)\s+"([^"]*)"', text, re.M))
        for name, fmt, comment in entry.findall(text):
            comment = comment[1:-1] if comment.startswith('"') else macros.get(comment, "")
            schema[name] = {"fmt": int(fmt), "comment": comment}
    return schema


def resolve_enum(value, comment):
    """Number rtklib's str2enum() gives for an enum value, or None if rejected."""
    if not value:
        return None
    pos = 0
    while True:
        i = comment.find(value, pos)
        if i < 0:
            break
        if i > 0 and comment[i - 1] == ":":
            j = i - 2
            while j >= 0 and comment[j].isdigit():
                j -= 1
            m = re.match(r"\d+", comment[j + 1:])
            return int(m.group(0)) if m else None
        pos = i + 1
    i = comment.find(value + ":")
    if i >= 0:
        m = re.match(r"\s*[-+]?\d+", comment[i:])
        return int(m.group(0)) if m else None
    return None


def read_conf(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw.decode("latin-1").splitlines(True)


SCHEMA = None


def parse_conf(path):
    global SCHEMA
    if SCHEMA is None:
        SCHEMA = load_schema()
    schema = SCHEMA
    lines = read_conf(path)
    fields = {}
    order = []
    for no, line in enumerate(lines):
        body, _ = split_eol(line)
        if body.lstrip().startswith("#"):
            continue
        m = LINE_RE.match(body)
        if not m:
            continue
        key = m.group("key")
        rest = m.group("rest")
        value, _, comment = rest.partition("#")
        value = value.strip()
        spec = schema.get(key)
        if spec:
            hint = parse_hint("(%s)" % spec["comment"] if spec["comment"] else "", spec["fmt"])
        else:
            hint = parse_hint(comment)
        canon = None
        if hint["kind"] == "enum":
            num = resolve_enum(value, spec["comment"]) if spec else None
            if spec is None and value.isdigit():
                num = int(value)
            names = [c["name"] for c in hint["choices"]]
            if value in names and spec is None:
                canon = value
            for c in hint["choices"]:
                if num is not None and c["num"] == num:
                    canon = c["name"]
        if key not in fields:
            order.append(key)
        fields[key] = {          # the last occurrence wins, as in rtkrcv
            "key": key, "value": value, "line": no + 1,
            "kind": hint["kind"], "unit": hint["unit"], "note": hint["note"],
            "choices": hint["choices"],
            "canon": canon,                          # enum value as rtkrcv reads it
            "known": bool(spec) or not schema,       # False: rtkrcv ignores this option
        }
    groups = {g: [] for g, _ in GROUPS}
    other = []
    for key in order:
        prefix = key.split("-", 1)[0]
        gid = re.sub(r"\d+$", "", prefix) if prefix[:6] in ("inpstr", "outstr", "logstr") else prefix
        f = fields[key]
        f["stream"] = prefix if gid in ("inpstr", "outstr", "logstr") else ""
        (groups[gid] if gid in groups else other).append(f)
    suffix_rank = {"type": 0, "path": 1, "format": 2}
    out = []
    for gid, title in GROUPS:
        fs = groups[gid]
        if not fs:
            continue
        if gid in ("inpstr", "outstr", "logstr"):
            fs.sort(key=lambda f: (f["stream"], suffix_rank.get(f["key"].split("-", 1)[1], 9)))
        out.append({"id": gid, "title": title, "fields": fs})
    if other:
        out.append({"id": "other", "title": "Other", "fields": other})
    return {
        "path": path, "mtime": os.path.getmtime(path),
        "groups": out, "streams": STREAM_NAMES,
    }


def check_value(value):
    if not isinstance(value, str):
        return "value must be text"
    if re.search(r"[\r\n#]", value):
        return "value cannot contain '#' or a line break"
    if len(value) > 1000:
        return "value is too long"
    return ""


def save_conf(path, changes):
    """Rewrite only the lines of the changed options; everything else is kept."""
    lines = read_conf(path)
    seen = set()
    for i, line in enumerate(lines):
        body, eol = split_eol(line)
        if body.lstrip().startswith("#"):
            continue
        m = LINE_RE.match(body)
        if not m or m.group("key") not in changes:
            continue
        key = m.group("key")
        value = changes[key].strip()
        rest = m.group("rest")
        if "#" in rest:
            old, _, comment = rest.partition("#")
            width = len(old)
            field = value.ljust(width) if len(value) < width else value + " "
            body = m.group("head") + field + "#" + comment
        else:
            body = m.group("head") + value
        lines[i] = body + eol
        seen.add(key)
    missing = sorted(set(changes) - seen)
    if missing:
        raise ValueError("option not in file: " + ", ".join(missing))
    with open(path, "wb") as f:
        f.write("".join(lines).encode("latin-1"))


def conf_value(path, key, default=""):
    try:
        for g in parse_conf(path)["groups"]:
            for f in g["fields"]:
                if f["key"] == key:
                    return f["value"]
    except OSError:
        pass
    return default


# ----------------------------------------------------------------------------
# rtkrcv telnet console
# ----------------------------------------------------------------------------
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Console:
    def __init__(self, port, passwd):
        self.port = port
        self.passwd = passwd
        self.sock = None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def _read_until(self, endings, timeout):
        buf = b""
        deadline = time.time() + timeout
        while True:
            text = self._clean(buf)
            for e in endings:
                if text.endswith(e):
                    return text
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError("console did not answer")
            self.sock.settimeout(left)
            data = self.sock.recv(65536)
            if not data:
                raise ConnectionError("console closed")
            buf += data

    @staticmethod
    def _clean(buf):
        buf = re.sub(b"\xff[\xfb-\xfe].", b"", buf, flags=re.S)     # telnet negotiation
        text = buf.decode("latin-1").replace("\r", "").replace("\x00", "")
        return ANSI_RE.sub("", text)

    def connect(self):
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        text = self._read_until(["password: ", PROMPT], 3)
        if text.endswith("password: "):
            self.sock.sendall(self.passwd.encode("latin-1") + b"\r")
            text = self._read_until(["password: ", PROMPT], 3)
            if not text.endswith(PROMPT):
                raise PermissionError("console password rejected")

    def cmd(self, command, timeout=4):
        if not self.sock:
            self.connect()
        self.sock.sendall(command.encode("latin-1") + b"\r")
        text = self._read_until([PROMPT], timeout)
        text = text[:-len(PROMPT)]
        return text.split("\n", 1)[1] if "\n" in text else ""       # drop the echoed command

    def send(self, command):
        if not self.sock:
            self.connect()
        self.sock.sendall(command.encode("latin-1") + b"\r")


def parse_status(text):
    out = {}
    for line in text.split("\n"):
        if len(line) > 29 and line[28] == ":":
            out[line[:28].strip()] = line[29:].strip()
    out.pop("Parameter", None)
    return out


STREAM_RE = re.compile(
    r"^(.{12}) (\S+)\s+(\S*)\s+([-CE])\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) ?(.{0,24}) ?(.*)$")


def parse_streams(text):
    rows = []
    for line in text.split("\n"):
        m = STREAM_RE.match(line)
        if not m or m.group(1).strip() == "Stream":
            continue
        rows.append({
            "name": m.group(1).strip(), "type": m.group(2), "fmt": m.group(3),
            "state": m.group(4), "inb": int(m.group(5)), "inr": int(m.group(6)),
            "outb": int(m.group(7)), "outr": int(m.group(8)),
            "path": m.group(9).strip(), "msg": m.group(10).strip(),
        })
    return rows


def parse_satellites(text):
    header, rows = [], []
    for line in text.split("\n"):
        cells = line.split()
        if not cells:
            continue
        if cells[0] == "SAT":
            header = cells
        elif header and len(cells) == len(header):
            rows.append(cells)
    return {"header": header, "rows": rows}


# ----------------------------------------------------------------------------
# rtkrcv process
# ----------------------------------------------------------------------------
class Runner:
    def __init__(self, conf, console_port):
        self.conf = conf
        self.console_port = console_port
        self.lock = threading.RLock()
        self.proc = None
        self.console = None
        self.started = 0.0
        self.conf_mtime = 0.0
        self.last_exit = None
        self.cache = None
        self.cache_time = 0.0
        self.logdir = tempfile.mkdtemp(prefix="rtkrcv-ui-")
        self.logpath = os.path.join(self.logdir, "rtkrcv.log")

    # -- helpers --------------------------------------------------------------
    def _log_tail(self, n=15):
        try:
            with open(self.logpath, "r", errors="replace") as f:
                return "".join(f.readlines()[-n:]).strip()
        except OSError:
            return ""

    def _reap(self):
        if self.proc and self.proc.poll() is not None:
            code = self.proc.returncode
            reason = "exit code %d" % code
            if code < 0:
                try:
                    reason = "killed by " + signal.Signals(-code).name
                except ValueError:
                    reason = "killed by signal %d" % -code
            self.last_exit = {"code": code, "reason": reason, "log": self._log_tail(),
                              "time": time.time(), "expected": getattr(self, "_stopping", False)}
            self.proc = None
            if self.console:
                self.console.close()
            self.console = None
            self.cache = None

    def others(self):
        """rtkrcv processes of this user that were not started from here."""
        try:
            txt = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "pid=,etime=,command="],
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        mine = self.proc.pid if self.proc else -1
        out = []
        for line in txt.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 3 or not parts[0].isdigit():
                continue
            pid, etime, command = int(parts[0]), parts[1], parts[2]
            argv0 = command.split()[0]
            if os.path.basename(argv0) != "rtkrcv" or pid == mine:
                continue
            out.append({"pid": pid, "etime": etime, "command": command})
        return out

    # -- control --------------------------------------------------------------
    def start(self):
        with self.lock:
            self._reap()
            if self.proc:
                return "rtkrcv is already running"
            if not os.access(BINARY, os.X_OK):
                return "rtkrcv is not built: run `make` in " + RUN_DIR
            if not os.path.isfile(self.conf):
                return "options file not found: " + self.conf
            self._stopping = False
            self.last_exit = None
            log = open(self.logpath, "wb")
            try:
                self.proc = subprocess.Popen(
                    [BINARY, "-s", "-p", str(self.console_port), "-o", self.conf],
                    cwd=RUN_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            except OSError as e:
                return "cannot start rtkrcv: %s" % e
            finally:
                log.close()
            self.started = time.time()
            self.conf_mtime = os.path.getmtime(self.conf)
            self.console = Console(self.console_port, conf_value(self.conf, "console-passwd", "admin"))
            self.cache = None
            return ""

    def stop(self):
        with self.lock:
            self._reap()
            if not self.proc:
                return ""
            self._stopping = True
            proc = self.proc
            try:
                self.console.send("shutdown")
            except Exception:
                pass
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.terminate()                    # rtkrcv shuts down cleanly on SIGTERM
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            self._reap()
            return ""

    def stop_other(self, pid):
        if pid not in [o["pid"] for o in self.others()]:
            return "no such rtkrcv process"
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            return str(e)
        return ""

    # -- monitoring -----------------------------------------------------------
    def snapshot(self):
        with self.lock:
            self._reap()
            now = time.time()
            live = None
            error = ""
            if self.proc:
                if self.cache and now - self.cache_time < 0.7:
                    live = self.cache
                else:
                    try:
                        live = {
                            "status": parse_status(self.console.cmd("status")),
                            "streams": parse_streams(self.console.cmd("stream")),
                            "sats": parse_satellites(self.console.cmd("satellite")),
                        }
                        self.cache, self.cache_time = live, now
                    except Exception as e:      # console not up yet, or lost
                        self.console.close()
                        live = self.cache
                        if now - self.started > 3:
                            error = "console: %s" % e
            try:
                mtime = os.path.getmtime(self.conf)
            except OSError:
                mtime = 0
            return {
                "running": bool(self.proc),
                "pid": self.proc.pid if self.proc else None,
                "uptime": now - self.started if self.proc else 0,
                "stale": bool(self.proc) and mtime > self.conf_mtime,
                "conf_mtime": mtime,
                "last_exit": self.last_exit,
                "others": self.others(),
                "live": live,
                "error": error,
                # rtkrcv keeps running when the server refuses to start (e.g. a
                # ${NAME} in a stream path is not set); its message is in the log
                "log": self._log_tail() if live and live["status"].get("rtk server state") == "stop" else "",
                "built": os.access(BINARY, os.X_OK),
            }


# ----------------------------------------------------------------------------
# http
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "rtkrcv-ui"
    runner = None
    token = ""
    hosts = ()

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self, api):
        if self.headers.get("Host", "") not in self.hosts:       # blocks DNS rebinding
            self._send(403, {"error": "bad host"})
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Token", ""), self.token):
            self._send(403, {"error": "bad token: reload the page"})
            return False
        return True

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not self._allowed(False):
                return
            with open(os.path.join(HERE, "index.html"), "r", encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", self.token)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/config":
            if self._allowed(True):
                try:
                    self._send(200, parse_conf(self.runner.conf))
                except OSError as e:
                    self._send(500, {"error": str(e)})
        elif path == "/api/state":
            if self._allowed(True):
                self._send(200, self.runner.snapshot())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed(True):
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n) or b"{}") if n < 1 << 20 else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return self._send(400, {"error": "bad request"})
        r = self.runner
        path = self.path
        if path == "/api/config":
            changes = data.get("values")
            if not isinstance(changes, dict) or not changes:
                return self._send(400, {"error": "nothing to save"})
            for k, v in changes.items():
                err = check_value(v)
                if err:
                    return self._send(400, {"error": "%s: %s" % (k, err)})
            try:
                save_conf(r.conf, changes)
            except (OSError, ValueError) as e:
                return self._send(400, {"error": str(e)})
            return self._send(200, parse_conf(r.conf))
        if path == "/api/start":
            err = r.start()
        elif path == "/api/stop":
            err = r.stop()
        elif path == "/api/restart":
            err = r.stop() or r.start()
        elif path == "/api/stop-other":
            pid = data.get("pid")
            err = r.stop_other(pid) if isinstance(pid, int) else "bad pid"
        else:
            return self._send(404, {"error": "not found"})
        if err:
            return self._send(400, {"error": err})
        self._send(200, r.snapshot())


def main():
    ap = argparse.ArgumentParser(description="Web UI for rtkrcv")
    ap.add_argument("--conf", default=DEFAULT_CONF, help="options file (default: conf/single.conf)")
    ap.add_argument("--port", type=int, default=8765, help="web port (default: 8765)")
    ap.add_argument("--console-port", type=int, default=2950,
                    help="telnet console port given to rtkrcv (default: 2950)")
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args()

    conf = os.path.abspath(args.conf)
    if not os.path.isfile(conf):
        sys.exit("options file not found: " + conf)

    runner = Runner(conf, args.console_port)
    Handler.runner = runner
    Handler.token = secrets.token_urlsafe(24)
    Handler.hosts = ("127.0.0.1:%d" % args.port, "localhost:%d" % args.port)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        sys.exit("cannot listen on port %d: %s (try --port N)" % (args.port, e))
    httpd.daemon_threads = True

    def shutdown(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)

    url = "http://127.0.0.1:%d/" % args.port
    print("rtkrcv UI : " + url)
    print("options   : " + conf)
    print("Ctrl-C stops the UI and the rtkrcv it started.")
    if not args.no_open:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()
        httpd.server_close()
        shutil.rmtree(runner.logdir, ignore_errors=True)


if __name__ == "__main__":
    main()
