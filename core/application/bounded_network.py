"""Owned, cancellable network I/O with an absolute deadline, including DNS.

Only the system DNS call runs in a short-lived child process: getaddrinfo has no
portable cancellation API. No archive key, application state or model context is
sent to that process. HTTP remains in the worker and sockets are explicitly owned.
"""
from __future__ import annotations

import errno
import ipaddress
import json
import select
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection as BaseHTTPConnection
from http.client import HTTPSConnection as BaseHTTPSConnection
from typing import Self


class OperationCancelled(RuntimeError):
    pass


CancellationCheck = Callable[[], bool]

_DNS_SCRIPT = (
    "import json,socket,sys; host,port=json.load(sys.stdin); "
    "json.dump(socket.getaddrinfo(host,port,socket.AF_UNSPEC,socket.SOCK_STREAM),sys.stdout)"
)


class NetworkDeadline:
    def __init__(self, seconds: float, cancel_requested: CancellationCheck | None = None) -> None:
        self._expires = time.monotonic() + seconds
        self._cancel = cancel_requested
        self._stop = threading.Event()
        self._sockets: list[socket.socket] = []
        self._lock = threading.Lock()
        self._watchdog = threading.Thread(target=self._watch, name="network-deadline", daemon=True)

    def __enter__(self) -> Self:
        self.check()
        self._watchdog.start()
        return self

    def __exit__(self, *_args) -> None:
        self._stop.set()
        self._watchdog.join()
        for sock in self._sockets:
            sock.close()

    def check(self) -> None:
        if self._cancel is not None and self._cancel():
            raise OperationCancelled("Operation cancelled")
        if time.monotonic() >= self._expires:
            raise TimeoutError("Network operation exceeded its total deadline")

    def remaining(self) -> float:
        self.check()
        return max(0.001, self._expires - time.monotonic())

    def _watch(self) -> None:
        while not self._stop.wait(0.025):
            try:
                self.check()
            except (OperationCancelled, TimeoutError):
                with self._lock:
                    sockets = tuple(self._sockets)
                for sock in sockets:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return

    def _own(self, sock: socket.socket) -> socket.socket:
        with self._lock:
            self._sockets.append(sock)
        self.check()
        return sock

    def resolve(self, host: str, port: int) -> list[tuple]:
        self.check()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
            address = (str(literal), port, 0, 0) if literal.version == 6 else (str(literal), port)
            return [(family, socket.SOCK_STREAM, 0, "", address)]
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", _DNS_SCRIPT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        request = json.dumps([host, port]).encode("utf-8")
        dns_expires = min(self._expires, time.monotonic() + 8.0)
        try:
            while True:
                self.check()
                if time.monotonic() >= dns_expires:
                    raise TimeoutError("DNS resolution exceeded its deadline")
                try:
                    output, _ = process.communicate(request, timeout=0.05)
                    if process.returncode:
                        raise OSError("Host could not be resolved")
                    return [tuple(row[:4]) + (tuple(row[4]),) for row in json.loads(output)]
                except subprocess.TimeoutExpired:
                    request = None
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def connect(self, address: tuple[str, int], addresses: tuple[str, ...] | None = None) -> socket.socket:
        host, port = address
        rows = self.resolve(host, port) if addresses is None else [
            row for ip in addresses for row in self.resolve(ip, port)
        ]
        last_error: OSError | None = None
        for family, socktype, proto, _canonname, sockaddr in rows:
            self.check()
            sock = self._own(socket.socket(family, socktype, proto))
            try:
                sock.setblocking(False)
                result = sock.connect_ex(sockaddr)
                if result not in {0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY}:
                    raise OSError(result, "Connection failed")
                while result:
                    self.check()
                    _, writable, exceptional = select.select([], [sock], [sock], min(0.05, self.remaining()))
                    if writable or exceptional:
                        result = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                        if result:
                            raise OSError(result, "Connection failed")
                sock.settimeout(self.remaining())
                return sock
            except OSError as exc:
                self.check()
                last_error = exc
                sock.close()
        raise OSError("No address could be reached") from last_error

    def wrap_tls(self, sock: socket.socket, context: ssl.SSLContext, host: str) -> ssl.SSLSocket:
        wrapped = self._own(context.wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False))
        wrapped.settimeout(self.remaining())
        wrapped.do_handshake()
        self.check()
        return wrapped


class HTTPConnection(BaseHTTPConnection):
    def __init__(self, *args, deadline: NetworkDeadline, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self) -> None:
        self.sock = self._deadline.connect((self.host, self.port))


class HTTPSConnection(BaseHTTPSConnection):
    def __init__(self, *args, deadline: NetworkDeadline, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self) -> None:
        sock = self._deadline.connect((self.host, self.port))
        self.sock = self._deadline.wrap_tls(sock, self._context, self.host)
