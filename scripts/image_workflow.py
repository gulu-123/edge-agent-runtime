"""Run the upstream image adapter against an isolated virtual-device stack."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import time

import cv2
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from std_msgs.msg import Bool
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--run-dir', type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    repo = project / 'repo'
    workspace = repo / 'ros2_ws'
    image_path = args.image.resolve(strict=True)
    run = args.run_dir or project / 'runs' / (time.strftime('%Y%m%d-%H%M%S') + '-image-workflow')
    run = run.resolve()
    if run.exists():
        raise RuntimeError(f'Refusing to overwrite an existing run: {run}')
    run.mkdir(parents=True)
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError('Cannot decode input image')
    config = workspace / 'src/perception_task_adapter/config/perception_task_adapter.yaml'
    params = yaml.safe_load(config.read_text())['perception_task_adapter']['ros__parameters']
    _, ids, _ = cv2.aruco.detectMarkers(
        image, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    detected = [] if ids is None else ids.flatten().tolist()
    mapped = [value for value in params['marker_ids'] if value in detected]
    summary = {'status': 'STARTED', 'input_path': str(image_path),
               'input_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
               'dictionary': 'DICT_4X4_50', 'detected_ids': detected,
               'execution_device': 'virtual_can_device on vcan0'}
    (run / 'detection.json').write_text(json.dumps(summary, indent=2) + '\n')
    if len(mapped) != 1:
        raise RuntimeError(f'Expected exactly one mapped marker; found {mapped}')
    mapping_index = params['marker_ids'].index(mapped[0])
    expected_target = params['target_ids'][mapping_index]
    shutil.copy2(image_path, run / ('input' + image_path.suffix))
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            executable = (proc / 'exe').resolve(strict=True)
        except (OSError, PermissionError):
            continue
        if executable.is_relative_to(workspace / 'install'):
            raise RuntimeError(f'Another runtime process is active: {proc.name}')
    subprocess.run(['ip', 'link', 'show', 'vcan0'], check=True, capture_output=True)
    processes = []
    handles = []
    db = run / 'runtime.sqlite3'
    events = run / 'task_events.jsonl'
    stages = run / 'stage_events.jsonl'
    ready = {'runtime': False, 'history': False}
    rclpy.init()
    node = rclpy.create_node('real_image_workflow_verifier')
    node.create_subscription(Bool, '/runtime/ready',
                             lambda msg: ready.update(runtime=msg.data), 1)
    def on_diagnostics(msg):
        if any(item.name == 'runtime/history' for item in msg.status):
            ready['history'] = True
    node.create_subscription(DiagnosticArray, '/diagnostics', on_diagnostics, 10)

    def binary(package, executable):
        return str(workspace / 'install' / package / 'lib' / package / executable)

    def start(name, command):
        handle = (run / (name + '.log')).open('w')
        handles.append(handle)
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
        processes.append((name, process))

    def ros(package, executable, *extra):
        return [binary(package, executable), '--ros-args', *extra]

    try:
        start('can', ['/usr/bin/candump', '-L', 'vcan0'])
        start('virtual', ros('virtual_can_device', 'virtual_can_device_node',
                            '-p', 'interface_name:=vcan0', '-p', 'mode:=normal'))
        start('history', ros('runtime_history', 'runtime_history_node',
                            '-p', f'database_path:={db}'))
        start('monitor', ros('runtime_monitor', 'runtime_monitor_node', '--params-file',
                            str(workspace / 'src/runtime_monitor/config/runtime_monitor.yaml')))
        start('bridge', ros('device_bridge', 'device_bridge_node', '--params-file',
                           str(workspace / 'src/device_bridge/config/device_bridge.yaml'),
                           '-p', f'stage_event_log_path:={stages}'))
        start('executor', ros('task_executor', 'task_executor_node', '--params-file',
                             str(workspace / 'src/task_executor/config/targets.yaml'),
                             '-p', f'stage_event_log_path:={stages}',
                             '-p', f'task_event_capture_path:={events}'))
        start('orchestrator', ros('task_orchestrator', 'task_orchestrator_node'))
        deadline = time.monotonic() + 20
        while not all(ready.values()):
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'{name} exited before runtime became ready')
            if time.monotonic() > deadline:
                raise RuntimeError(f'Readiness deadline exceeded: {ready}')
            rclpy.spin_once(node, timeout_sec=0.1)
        with (run / 'perception.log').open('w') as handle:
            result = subprocess.run(ros('perception_task_adapter', 'perception_task_adapter_node',
                                       '--params-file', str(config), '-p', 'input_mode:=image',
                                       '-p', f'image_path:={image_path}'),
                                    stdout=handle, stderr=subprocess.STDOUT, timeout=25)
        if result.returncode != 0:
            raise RuntimeError(f'Upstream perception adapter exited {result.returncode}')
        terminal = [json.loads(line) for line in events.read_text().splitlines() if line]
        if len(terminal) != 1:
            raise RuntimeError(f'Expected one terminal TaskEvent, got {len(terminal)}')
        event = terminal[0]
        if (event['target_id'], event['outcome'], event['error_code']) != (expected_target, 0, 0):
            raise RuntimeError(f'Unexpected task result: {event}')
        deadline = time.monotonic() + 5
        rows = []
        while time.monotonic() < deadline:
            with sqlite3.connect(db) as connection:
                connection.row_factory = sqlite3.Row
                rows = [dict(row) for row in connection.execute(
                    'SELECT * FROM task_runs WHERE task_id = ?', (event['task_id'],))]
            if rows:
                break
            time.sleep(0.1)
        if len(rows) != 1:
            raise RuntimeError('Exactly one corresponding SQLite record was not found')
        if any(rows[0].get(key) != event[key] for key in ('target_id', 'outcome', 'error_code')):
            raise RuntimeError('SQLite result differs from the terminal TaskEvent')
        (run / 'sqlite-record.json').write_text(json.dumps(rows[0], indent=2) + '\n')
        summary.update(status='PASS', marker_id=mapped[0], target_id=expected_target,
                       workflow_id=params['workflow_ids'][mapping_index], task_event=event,
                       sqlite_rows=1)
    except Exception as error:
        summary.update(status='FAIL', error=str(error))
        raise
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        for handle in handles:
            handle.close()
        node.destroy_node()
        rclpy.shutdown()
        can_text = (run / 'can.log').read_text() if (run / 'can.log').exists() else ''
        summary['can_command_observed'] = '100#' in can_text
        summary['can_response_observed'] = '101#' in can_text
        if summary['status'] == 'PASS' and not (
                summary['can_command_observed'] and summary['can_response_observed']):
            summary.update(status='FAIL', error='CAN command/response evidence missing')
        (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not (summary['can_command_observed'] and summary['can_response_observed']):
        raise RuntimeError('CAN command/response evidence missing; inspect can.log')
    print(json.dumps(summary, indent=2))
    print(f'IMAGE_WORKFLOW_PASS {run}')


if __name__ == '__main__':
    main()
