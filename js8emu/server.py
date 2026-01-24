from __future__ import annotations

import logging
import selectors
import socket
from typing import Any

from .config import AppConfig
from .models import Connection, InterfaceState
from .protocol import ProtocolError, fragment_text, parse_json_line, to_json_line
from .scheduler import Scheduler
from .util import epoch_ms_times_1000, rand_snr, rand_tdrift, station_status_id

log = logging.getLogger("js8emu")

# Maximum number of bytes to log for outbound payloads
MAX_LOG_BYTES = 200


class JS8EmuServer:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.sel = selectors.DefaultSelector()
        self.scheduler = Scheduler()
        self._closed = False

        self.interfaces: dict[str, InterfaceState] = {}
        for ic in cfg.interfaces:
            ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            ls.bind(("127.0.0.1", ic.port))
            ls.listen()
            ls.setblocking(False)

            state = InterfaceState(
                name=ic.name,
                port=ic.port,
                callsign=ic.callsign,
                maidenhead=ic.maidenhead,
                offset=ic.offset,
                frequency=ic.frequency,
                listener=ls,
            )
            self.interfaces[ic.name] = state
            self.sel.register(ls, selectors.EVENT_READ, data=("listener", ic.name))
            log.info("Listening %s on 127.0.0.1:%d callsign=%s dial=%d offset=%d grid=%s",
                     ic.name, ic.port, ic.callsign, ic.frequency, ic.offset, ic.maidenhead)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        try:
            self.scheduler.close()
        finally:
            for iface in self.interfaces.values():
                if iface.conn:
                    iface.conn.close()
                try:
                    self.sel.unregister(iface.listener)
                except KeyError:
                    pass
                try:
                    iface.listener.close()
                except OSError:
                    pass
            try:
                self.sel.close()
            except OSError:
                pass

    def run_forever(self) -> None:
        log.info("JS8Emu running.")
        while not self._closed:
            events = self.sel.select(timeout=0.25)
            for key, _mask in events:
                kind, name = key.data
                if kind == "listener":
                    self._accept(name)
                elif kind == "client":
                    self._read_client(name)

    # --- Socket handling ---

    def _accept(self, iface_name: str) -> None:
        iface = self.interfaces[iface_name]
        try:
            conn, addr = iface.listener.accept()
            conn.setblocking(False)
        except OSError:
            return

        # Only one connection allowed per interface
        if iface.is_connected():
            log.warning("%s rejecting extra connection from %s (already connected).", iface_name, addr)
            try:
                conn.close()
            except OSError:
                pass
            return

        c = Connection(sock=conn, addr=addr)
        iface.conn = c
        self.sel.register(conn, selectors.EVENT_READ, data=("client", iface_name))
        log.info("%s accepted connection from %s", iface_name, addr)

    def _read_client(self, iface_name: str) -> None:
        iface = self.interfaces[iface_name]
        c = iface.conn
        if c is None or c.closed:
            return

        try:
            data = c.sock.recv(4096)
        except OSError:
            data = b""

        if not data:
            self._disconnect(iface_name)
            return

        c.recv_buffer.extend(data)

        # Process complete lines
        while True:
            nl = c.recv_buffer.find(b"\n")
            if nl < 0:
                break
            line = bytes(c.recv_buffer[:nl])  # without newline
            del c.recv_buffer[: nl + 1]

            if log.isEnabledFor(logging.DEBUG):
                shown = line[:MAX_LOG_BYTES]
                suffix = b"..." if len(line) > MAX_LOG_BYTES else b""
                log.debug(
                    "RX ← %-12s %r%s",
                    iface_name,
                    shown,
                    suffix,
                )

            if not line.strip():
                continue

            try:
                msg = parse_json_line(line)
            except ProtocolError:
                log.exception("%s received malformed JSON; ignoring.", iface_name)
                continue

            self._handle_message(iface_name, msg)

    def _disconnect(self, iface_name: str) -> None:
        iface = self.interfaces[iface_name]
        c = iface.conn
        iface.conn = None
        if c:
            try:
                self.sel.unregister(c.sock)
            except KeyError:
                pass
            c.close()
        log.info("%s disconnected.", iface_name)

    def _safe_send(self, iface: InterfaceState, payload: bytes) -> None:
        # Debug logging with payload truncation to avoid log spam
        if log.isEnabledFor(logging.DEBUG):
            shown = payload[:MAX_LOG_BYTES]
            suffix = b"..." if len(payload) > MAX_LOG_BYTES else b""
            log.debug(
                "TX → %-12s %r%s",
                iface.name,
                shown,
                suffix,
            )
        c = iface.conn
        if c is None or c.closed:
            return
        try:
            with c.send_lock:
                if c.closed:
                    return
                c.sock.sendall(payload)
        except OSError:
            # treat as disconnect
            self._disconnect(iface.name)

    # --- Message handling ---

    def _handle_message(self, iface_name: str, msg: dict[str, Any]) -> None:
        mtype = msg.get("type", "")
        if mtype == "STATION.GET_CALLSIGN":
            self._on_get_callsign(iface_name, msg)
        elif mtype == "RIG.GET_FREQ":
            self._on_get_freq(iface_name, msg)
        elif mtype == "RIG.SET_FREQ":
            self._on_set_freq(iface_name, msg)
        elif mtype == "TX.SEND_MESSAGE":
            self._on_tx_send_message(iface_name, msg)
        else:
            # requirement: log unknown types and continue
            log.debug("%s unknown message type %r ignored.", iface_name, mtype)

    def _on_get_callsign(self, iface_name: str, msg: dict[str, Any]) -> None:
        iface = self.interfaces[iface_name]
        req_params = msg.get("params") or {}
        _id = req_params.get("_ID")

        resp = {
            "params": {"_ID": _id},
            "type": "STATION.CALLSIGN",
            "value": iface.callsign,
        }
        self._safe_send(iface, to_json_line(resp))

    def _on_get_freq(self, iface_name: str, msg: dict[str, Any]) -> None:
        """
        Handle RIG.GET_FREQ.

        Respond with RIG.FREQ on the same interface instance.
        """
        iface = self.interfaces[iface_name]
        req_params = msg.get("params") or {}
        _id = req_params.get("_ID")

        dial = iface.frequency
        offset = iface.offset

        resp = {
            "params": {
                "DIAL": dial,
                "FREQ": dial + offset,
                "OFFSET": offset,
                "_ID": _id,
            },
            "type": "RIG.FREQ",
            "value": "",
        }
        self._safe_send(iface, to_json_line(resp))

    def _on_set_freq(self, iface_name: str, msg: dict[str, Any]) -> None:
        iface = self.interfaces[iface_name]
        params = msg.get("params") or {}
        dial = params.get("DIAL")
        try:
            new_freq = int(dial)
        except ValueError:
            log.warning("%s RIG.SET_FREQ invalid DIAL=%r ignored.", iface_name, dial)
            return

        iface.frequency = new_freq
        self._emit_station_status(iface)

    def _emit_station_status(self, iface: InterfaceState) -> None:
        dial = iface.frequency
        offset = iface.offset
        status = {
            "params": {
                "DIAL": dial,
                "FREQ": dial + offset,
                "OFFSET": offset,
                "SELECTED": "",
                "SPEED": 1,
                "_ID": str(station_status_id()),
            },
            "type": "STATION.STATUS",
            "value": "",
        }
        self._safe_send(iface, to_json_line(status))

    def _on_tx_send_message(self, sender_iface_name: str, msg: dict[str, Any]) -> None:
        sender = self.interfaces[sender_iface_name]
        payload = msg.get("value", "")
        if not isinstance(payload, str):
            payload = str(payload)

        # Spec: JS8Emu MUST prefix the payload with the sending interface callsign, colon, and space.
        # If the client already provided the prefix, do not duplicate it.
        prefix = f"{sender.callsign}: "
        full_payload = payload if payload.startswith(prefix) else f"{prefix}{payload}"

        fragments = fragment_text(full_payload, self.cfg.general.fragment_size)
        if not fragments:
            return

        # Determine recipients: same frequency, connected, not the sender
        recipients = [
            iface for iface in self.interfaces.values()
            if iface.name != sender.name
            and iface.frequency == sender.frequency
            and iface.is_connected()
        ]
        if not recipients:
            return

        # Transmission task (threaded)
        frame_time = self.cfg.general.frame_time

        def tx_task() -> None:
            # Per sender-receiver pair reassembly: since we own the fragmentation,
            # each receiver can be reassembled deterministically from this tx.
            # We'll send RX.ACTIVITY fragments, then RX.DIRECTED + RX.SPOT.
            for i, frag in enumerate(fragments):
                if not self.scheduler.sleep(frame_time):
                    return
                for r in recipients:
                    self._emit_rx_activity(receiver=r, frag=frag)

            # After full message delivered, emit RX.DIRECTED + RX.SPOT (single write)
            for r in recipients:
                self._emit_rx_directed_and_spot(sender=sender, receiver=r, original_text=payload)

        self.scheduler.run_in_thread(tx_task, name=f"tx-{sender.callsign}-{epoch_ms_times_1000()}")

    # --- RX emission ---

    def _emit_rx_activity(self, receiver: InterfaceState, frag: str) -> None:
        dial = receiver.frequency
        offset = receiver.offset
        msg = {
            "params": {
                "DIAL": dial,
                "FREQ": dial + offset,
                "OFFSET": offset,
                "SNR": rand_snr(),
                "SPEED": 1,
                "TDRIFT": rand_tdrift(),
                "UTC": epoch_ms_times_1000(),
                "_ID": -1,
            },
            "type": "RX.ACTIVITY",
            "value": frag,
        }
        self._safe_send(receiver, to_json_line(msg))

    def _emit_rx_directed_and_spot(self, sender: InterfaceState, receiver: InterfaceState, original_text: str) -> None:
        # Spec: append five bytes " \xe2\x99\xa2 " which is " ♢ " (space diamond space)
        suffix = " ♢ "
        text = f"{original_text}{suffix}"

        parts = text.split()
        to_call = parts[1] if len(parts) >= 2 else ""

        dial = receiver.frequency
        offset = receiver.offset
        snr = rand_snr()
        tdrift = rand_tdrift()
        utc = epoch_ms_times_1000()

        directed = {
            "params": {
                "CMD": " ",
                "DIAL": dial,
                "EXTRA": "",
                "FREQ": dial + offset,
                "FROM": sender.callsign,
                "GRID": "",
                "OFFSET": offset,
                "SNR": snr,
                "SPEED": 1,
                "TDRIFT": tdrift,
                "TEXT": text,
                "TO": to_call,
                "UTC": utc,
                "_ID": -1,
            },
            "type": "RX.DIRECTED",
            "value": text,
        }

        spot = {
            "params": {
                "CALL": sender.callsign,
                "DIAL": dial,
                "FREQ": dial + offset,
                "GRID": sender.maidenhead,
                "OFFSET": offset,
                "SNR": snr,
                "_ID": -1,
            },
            "type": "RX.SPOT",
            "value": "",
        }

        payload = to_json_line(directed) + to_json_line(spot)  # must be one TCP send
        self._safe_send(receiver, payload)
