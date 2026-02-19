import random
import threading


class CodeGenerator:
    """Generates unique 6-digit numeric codes for sessions."""

    def __init__(self) -> None:
        self._active_codes: set[str] = set()
        self._lock = threading.Lock()

    def generate(self) -> str:
        with self._lock:
            for _ in range(100):
                code = f"{random.randint(0, 999999):06d}"
                if code not in self._active_codes:
                    self._active_codes.add(code)
                    return code
            raise RuntimeError("Unable to generate unique code after 100 attempts")

    def release(self, code: str) -> None:
        with self._lock:
            self._active_codes.discard(code)

    def is_active(self, code: str) -> bool:
        with self._lock:
            return code in self._active_codes

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_codes)
