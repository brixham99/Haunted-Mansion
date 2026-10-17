"""Two-player network play for Haunted Mansion (standard library only).

One player hosts and owns the house (seed, key, enemies, furniture, lives,
score); the other joins. Both run the same game code: each moves its own
player locally and the host checks the rest.

Discovery: while waiting, the host broadcasts a small JSON beacon on UDP
DISCOVERY_PORT once a second (to the LAN and to 127.0.0.1); the joining game
listens there and lists the hosts it hears. An address can also be typed.

Play: one TCP connection on GAME_PORT carrying JSON lines (one message per
line). TCP keeps events in order and never loses them, so pushes, searches,
the key and the end of the game need no resend logic; the 20 Hz state
messages double as a heartbeat (TIMEOUT_S of silence = gone). Reading and
writing run on background threads, so the game loop never waits on the
network: it drains Link.poll() once a frame and Link.send() only queues.
"""

import json
import queue
import socket
import threading
import time

GAME_ID = "hm"
PROTOCOL = 1
GAME_PORT = 50555
DISCOVERY_PORT = 50556
BEACON_S = 1.0
STATE_HZ = 20
TIMEOUT_S = 5.0
CONNECT_TIMEOUT_S = 4.0
MAX_LINE = 1 << 20


def _clock() -> float:
    return time.monotonic()


def local_ip() -> str:
    """Best guess at this machine's LAN address (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def host_label() -> str:
    """Short machine name for the list of games."""
    name = socket.gethostname().split(".")[0] or "Player"
    return name[:20]


def parse_hostport(text: str, default_port: int = GAME_PORT):
    """'192.168.1.20', 'avon-3.local' or '192.168.1.20:50560' -> (host, port)."""
    host, sep, port = text.strip().partition(":")
    return host.strip(), int(port) if sep and port.strip() else default_port


def _encode(msg) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


def _decode(data: bytes):
    try:
        msg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return msg if isinstance(msg, dict) else None


# ----------------------------------------------------------------- discovery
class Beacon:
    """Host side: 'a game is here' once a second on the discovery port."""

    def __init__(self, info: dict, port: int = DISCOVERY_PORT):
        self.info = dict(info, id=GAME_ID, v=PROTOCOL)
        self.port = port
        self.next_t = 0.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        self.sock.setblocking(False)

    def tick(self):
        t = _clock()
        if t < self.next_t:
            return
        self.next_t = t + BEACON_S
        data = _encode(self.info)
        for addr in (("255.255.255.255", self.port), ("127.0.0.1", self.port)):
            try:
                self.sock.sendto(data, addr)
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Scanner:
    """Join side: listen on the discovery port and collect hosts."""

    def __init__(self, port: int = DISCOVERY_PORT):
        self.found = {}    # (ip, port) -> info
        self.error = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            self.sock.bind(("", port))
        except OSError as exc:
            self.error = f"Can't listen for games (UDP {port}): {exc.strerror or exc}"
        self.sock.setblocking(False)

    def poll(self):
        if self.error:
            return
        while True:
            try:
                data, (ip, _p) = self.sock.recvfrom(65536)
            except (BlockingIOError, InterruptedError, OSError):
                break
            msg = _decode(data.strip())
            if not msg or msg.get("id") != GAME_ID or msg.get("v") != PROTOCOL:
                continue
            try:
                port = int(msg.get("port", GAME_PORT))
            except (TypeError, ValueError):
                continue
            # one beacon arrives twice (LAN and loopback): one entry, LAN address preferred
            key = (str(msg.get("ip", ip)), port)
            old = self.found.get(key)
            if old is not None and not old["addr"][0].startswith("127.") and ip.startswith("127."):
                old["seen"] = _clock()
                continue
            msg["addr"] = (ip, port)
            msg["seen"] = _clock()
            self.found[key] = msg
        t = _clock()
        for k in [k for k, m in self.found.items() if t - m["seen"] > 4 * BEACON_S]:
            del self.found[k]   # that host stopped waiting

    def hosts(self):
        """[(address, info)] by name."""
        return sorted(((m["addr"], m) for m in self.found.values()), key=lambda am: (am[1].get("name", ""), am[0]))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ----------------------------------------------------------------- connection
class Link:
    """A connected TCP socket: a reader thread fills an inbox, a writer
    thread empties an outbox. Never blocks the caller."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        sock.settimeout(None)
        self.inbox = queue.Queue()
        self.outbox = queue.Queue()
        self.closed = False
        self.reason = ""
        self.last_recv = _clock()
        self.next_state_t = 0.0
        self.sent = self.received = 0
        try:
            self.peer = "%s:%d" % sock.getpeername()[:2]
        except OSError:
            self.peer = "?"
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._writer, daemon=True).start()

    def _reader(self):
        buf = b""
        try:
            while not self.closed:
                data = self.sock.recv(65536)
                if not data:
                    self._shut("The other player closed the game")
                    return
                buf += data
                if len(buf) > MAX_LINE:
                    self._shut("Bad data from the other game")
                    return
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = _decode(line)
                    if msg is not None:
                        self.last_recv = _clock()
                        self.received += 1
                        self.inbox.put(msg)
        except OSError as exc:
            self._shut(f"Connection lost ({exc.strerror or exc})")

    def _writer(self):
        try:
            while True:
                msg = self.outbox.get()
                if msg is None or self.closed:
                    return
                self.sock.sendall(_encode(msg))
                self.sent += 1
        except OSError as exc:
            self._shut(f"Connection lost ({exc.strerror or exc})")

    def _shut(self, reason):
        if not self.closed:
            self.closed = True
            self.reason = reason
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.outbox.put(None)

    def send(self, msg: dict):
        if not self.closed:
            self.outbox.put(msg)

    def poll(self):
        """Messages received since the last call, oldest first."""
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        if not self.closed and _clock() - self.last_recv > TIMEOUT_S:
            self._shut("The other game stopped answering")
        return out

    def state_due(self) -> bool:
        t = _clock()
        if t < self.next_state_t:
            return False
        self.next_state_t = t + 1.0 / STATE_HZ
        return True

    def close(self, say_bye=True):
        if self.closed:
            return
        if say_bye:
            try:   # best effort, straight away (the writer may be mid-message)
                self.sock.sendall(_encode({"t": "bye"}))
            except OSError:
                pass
        self._shut("Closed")


class Server:
    """Host side: listen on GAME_PORT and accept the first player (background thread)."""

    def __init__(self, port: int = GAME_PORT):
        self.port = port
        self.link = None
        self.error = None
        self.closed = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("", port))
            self.sock.listen(1)
        except OSError as exc:
            self.error = f"Can't open port {port}: {exc.strerror or exc}"
            return
        self.sock.settimeout(0.25)
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self.closed and self.link is None:
            try:
                conn, _addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.link = Link(conn)
        self.stop()

    def stop(self):
        """Stop listening (the accepted link, if any, stays open)."""
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Connector:
    """Join side: connect in the background; .link when done, .error if not."""

    def __init__(self, host: str, port: int = GAME_PORT, timeout: float = CONNECT_TIMEOUT_S):
        self.host, self.port = host, port
        self.link = None
        self.error = None
        self.done = False
        threading.Thread(target=self._run, args=(timeout,), daemon=True).start()

    def _run(self, timeout):
        try:
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
            self.link = Link(sock)
        except socket.gaierror:
            self.error = f"Can't find {self.host}"
        except socket.timeout:
            self.error = f"No answer from {self.host}"
        except OSError as exc:
            self.error = f"Can't connect to {self.host} ({exc.strerror or exc})"
        self.done = True
