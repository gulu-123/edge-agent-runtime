"""Use the two already-authorized Windows SSH connections as a binary relay."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from relay_config import load_config, ssh_args, receiver_command, camera_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--duration', type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.duration <= 600:
        parser.error('--duration must be between 30 and 600 seconds')
    config = load_config(args.config)
    name = datetime.now().strftime('%Y%m%d-%H%M%S') + '-live-camera'
    output = args.output_dir or Path(__file__).resolve().parents[1] / 'runs' / (name + '-relay')
    output.mkdir(parents=True, exist_ok=False)
    remote, command = receiver_command(config['runtime']['project_dir'], name, args.duration)
    runtime_ssh = ssh_args(config['runtime'])
    board_ssh = ssh_args(config['board'])
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    log = (output / 'relay.log').open('w', encoding='utf-8')
    errors = (output / 'vm-ssh.log').open('wb')
    board_errors = (output / 'board-stream.log').open('wb')
    receiver = subprocess.Popen(runtime_ssh + [command],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, creationflags=flags)
    messages = queue.Queue()
    def read_status():
        for line in receiver.stdout:
            messages.put(line.decode('utf-8', errors='replace').rstrip())
    threading.Thread(target=read_status, daemon=True).start()
    def show(line):
        print(line, flush=True)
        log.write(line + '\n')
        log.flush()
    sender = None
    transfer = None
    try:
        deadline = time.monotonic() + 40
        while True:
            try:
                line = messages.get(timeout=0.2)
                show(line)
                if line.startswith('LIVE_READY '):
                    break
            except queue.Empty:
                pass
            if receiver.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('VM runtime did not become ready; inspect vm-ssh.log')
        pipeline = camera_command(config['camera'], args.duration)
        sender = subprocess.Popen(board_ssh + [pipeline],
                                  stdout=subprocess.PIPE, stderr=board_errors, creationflags=flags)
        def forward():
            try:
                while True:
                    data = sender.stdout.read1(65536)
                    if not data:
                        break
                    receiver.stdin.write(data)
                    receiver.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    receiver.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
        transfer = threading.Thread(target=forward, daemon=True)
        transfer.start()
        show('CAMERA_RELAY_STARTED ' + remote)
        deadline = time.monotonic() + args.duration + 40
        while receiver.poll() is None:
            try:
                show(messages.get(timeout=0.3))
            except queue.Empty:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('Relay deadline exceeded')
        while not messages.empty():
            show(messages.get_nowait())
        if receiver.returncode:
            raise RuntimeError(f'VM validation exited {receiver.returncode}; run={remote}')
        show('RELAY_COMPLETE ' + remote)
    finally:
        for process in (sender, receiver):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        if transfer:
            transfer.join(timeout=2)
        log.close()
        errors.close()
        board_errors.close()


if __name__ == '__main__':
    main()
