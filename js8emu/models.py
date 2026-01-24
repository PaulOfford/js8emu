from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Connection:
    sock: socket.socket
    addr: tuple[str, int]
    recv_buffer: bytearray = field(default_factory=bytearray)
    send_lock: threading.Lock = field(default_factory=threading.Lock)
    closed: bool = False

    def close(self) -> None:
        with self.send_lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass


@dataclass
class InterfaceState:
    name: str
    port: int
    callsign: str
    maidenhead: str
    offset: int
    frequency: int  # mutable
    listener: socket.socket
    conn: Optional[Connection] = None  # exactly one connection allowed

    def is_connected(self) -> bool:
        return self.conn is not None and not self.conn.closed
