"""Smoke test: launch the built exe and verify it stays alive at startup.

The packaged app is a GUI (console=False), so a crash on import or SMC
contract init would terminate the process early. This launches the exe,
polls liveness, and reports pass/fail with the exit code if it died.
"""

import subprocess
import sys
import time

EXE = r"dist\AI Market Analyst\AI Market Analyst.exe"
LIVENESS_SECONDS = 20


def main() -> int:
    process = subprocess.Popen([EXE])
    print(f"launched pid={process.pid} exe={EXE}", flush=True)
    alive = True
    waited = 0.0
    while waited < LIVENESS_SECONDS:
        time.sleep(1.0)
        waited += 1.0
        if process.poll() is not None:
            alive = False
            break
    if alive:
        print(f"SMOKE_PASS: process alive after {waited:.0f}s (no early crash)", flush=True)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("SMOKE_RESULT=pass", flush=True)
        return 0
    code = process.returncode
    print(f"SMOKE_FAIL: process exited early with code={code} after {waited:.0f}s", flush=True)
    print("SMOKE_RESULT=fail", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())