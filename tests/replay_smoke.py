"""Synthetic MJPEG integration smoke; this is not camera/hardware evidence."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

import cv2
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    run = root / 'runs' / (time.strftime('%Y%m%d-%H%M%S') + '-synthetic-replay')
    process = subprocess.Popen(['bash', str(root / 'scripts/run-live.sh'), '--run-dir', str(run), '--duration', '60', '--source', 'synthetic-replay'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    messages = queue.Queue()
    def read():
        for line in process.stdout:
            messages.put(line.decode(errors='replace').rstrip())
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while True:
            if time.monotonic() > deadline or process.poll() is not None:
                raise RuntimeError('Replay runtime did not become ready')
            try:
                line = messages.get(timeout=0.2)
                print(line, flush=True)
                if line.startswith('LIVE_READY '):
                    break
            except queue.Empty:
                pass
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker = cv2.aruco.drawMarker(dictionary, 10, 240)
        marked = np.full((480, 640), 255, dtype=np.uint8)
        marked[120:360, 200:440] = marker
        empty = np.full((480, 640), 255, dtype=np.uint8)
        frames = [(marked, 30), (empty, 15), (marked, 30)]
        for image, count in frames:
            ok, jpeg = cv2.imencode('.jpg', image)
            assert ok
            for _ in range(count):
                if process.poll() is not None:
                    break
                try:
                    process.stdin.write(jpeg.tobytes())
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
                time.sleep(0.2)
        code = process.wait(timeout=15)
        thread.join(timeout=2)
        while not messages.empty():
            print(messages.get(), flush=True)
        summary = json.loads((run / 'summary.json').read_text())
        assert code == 0 and summary['status'] == 'PASS', summary
        assert summary['submissions'] == summary['sqlite_rows'] == 2
        assert summary['can_ack_ids_match']
        assert summary['input_source'] == 'synthetic-replay'
        print('SYNTHETIC_REPLAY_PASS', run)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass


if __name__ == '__main__':
    main()
