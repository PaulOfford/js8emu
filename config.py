from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralConfig:
    fragment_size: int
    frame_time: float


@dataclass
class InterfaceConfig:
    name: str
    port: int
    callsign: str
    frequency: int
    offset: int
    maidenhead: str


@dataclass(frozen=True)
class AppConfig:
    general: GeneralConfig
    interfaces: list[InterfaceConfig]


class ConfigError(ValueError):
    pass


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")

    if "general" not in cp:
        raise ConfigError("Missing [general] section")

    try:
        fragment_size = int(cp["general"]["fragment_size"])
        frame_time = float(cp["general"]["frame_time"])
    except KeyError as e:
        raise ConfigError(f"Missing [general] key: {e}") from e
    except ValueError as e:
        raise ConfigError(f"Invalid [general] value: {e}") from e

    if fragment_size <= 0:
        raise ConfigError("[general] fragment_size must be > 0")
    if frame_time < 0:
        raise ConfigError("[general] frame_time must be >= 0")

    interfaces: list[InterfaceConfig] = []
    for section in cp.sections():
        if not section.startswith("interface_"):
            continue
        s = cp[section]
        try:
            port = int(s["port"])
            callsign = str(s["callsign"]).strip().strip('"').strip("'")
            frequency = int(s["frequency"])
            offset = int(s["offset"])
            maidenhead = str(s["maidenhead"]).strip().strip('"').strip("'")
        except KeyError as e:
            raise ConfigError(f"Missing [{section}] key: {e}") from e
        except ValueError as e:
            raise ConfigError(f"Invalid [{section}] value: {e}") from e

        if not callsign:
            raise ConfigError(f"[{section}] callsign must be non-empty")
        if port <= 0 or port > 65535:
            raise ConfigError(f"[{section}] port out of range: {port}")
        if frequency <= 0:
            raise ConfigError(f"[{section}] frequency must be > 0")
        # offset can be 0, but keep simple sanity check
        if abs(offset) > 200000:
            raise ConfigError(f"[{section}] offset seems unreasonable: {offset}")
        if not maidenhead:
            raise ConfigError(f"[{section}] maidenhead must be non-empty")

        interfaces.append(
            InterfaceConfig(
                name=section,
                port=port,
                callsign=callsign,
                frequency=frequency,
                offset=offset,
                maidenhead=maidenhead,
            )
        )

    if not interfaces:
        raise ConfigError("No [interface_N] sections found")

    # Startup validation: duplicate ports/callsigns => immediate failure
    ports = [i.port for i in interfaces]
    if len(set(ports)) != len(ports):
        raise ConfigError("Duplicate interface port detected; ports must be unique")

    calls = [i.callsign.upper() for i in interfaces]
    if len(set(calls)) != len(calls):
        raise ConfigError("Duplicate interface callsign detected; callsigns must be unique")

    return AppConfig(
        general=GeneralConfig(fragment_size=fragment_size, frame_time=frame_time),
        interfaces=interfaces,
    )
