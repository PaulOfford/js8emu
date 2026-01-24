from __future__ import annotations

import random
import time


def epoch_ms_times_1000() -> int:
    # Spec: "current epoch time in milliseconds multiplied by 1000"
    ms = int(time.time() * 1000)
    return ms * 1000


def station_status_id() -> int:
    # Spec: epoch(ms)*1000 - 1499299200000
    return epoch_ms_times_1000() - 1499299200000


def rand_snr() -> int:
    return random.randint(-20, 20)


def rand_tdrift() -> float:
    # random float -2..+2
    return random.uniform(-2.0, 2.0)
