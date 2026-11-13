"""Receive MJPEG on stdin and verify two physical marker presentations."""
import argparse
import json
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from std_msgs.msg import Bool


def lines(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--duration', type=int, default=300)
    parser.add_argument('--source', choices=('camera', 'synthetic-replay'), default='camera')
    args = parser.parse_args()
    if not 30 <= args.duration <= 600:
        parser.error('--duration must be between 30 and 600 seconds')
    project = Path(__file__).resolve().parents[1]
    workspace = project / 'repo/ros2_ws'
    run = args.run_dir.resolve()
    if run.exists():
        raise RuntimeError(f'Run directory already exists: {run}')
    run.mkdir(parents=True)
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            exe = (proc / 'exe').resolve(strict=True)
        except (OSError, PermissionError):
            continue
        if exe.is_relative_to(workspace / 'install'):
            raise RuntimeError(f'Another runtime is active: {proc.name}')
    subprocess.run(['ip', 'link', 'show', 'vcan0'], check=True, capture_output=True)
    db = run / 'runtime.sqlite3'
    events = run / 'task_events.jsonl'
    stages = run / 'stage_events.jsonl'
    telemetry = run / 'frames.jsonl'
    handles, processes = [], []
    summary = {'status': 'RUNNING', 'input_source': args.source,
               'source': 'synthetic generated JPEG replay' if args.source == 'synthetic-replay' else 'camera stream over SSH relay',
               'device': 'virtual_can_device', 'confirm_frames': 3, 'rearm_missing_frames': 5}
    ready = {'runtime': False, 'history': False}
    rclpy.init()
    node = rclpy.create_node('live_camera_workflow_verifier')
    node.create_subscription(Bool, '/runtime/ready', lambda msg: ready.update(runtime=msg.data), 1)
    def diagnostics(msg):
        if any(item.name == 'runtime/history' for item in msg.status):
            ready['history'] = True
    node.create_subscription(DiagnosticArray, '/diagnostics', diagnostics, 10)
    def ros(package, executable, *extra):
        return [str(workspace / 'install' / package / 'lib' / package / executable), '--ros-args', *extra]
    def start(name, command, stdin=None, stdout=None):
        out = (run / (stdout or (name + '.log'))).open('w')
        handles.append(out)
        if stdout:
            err = (run / (name + '.log')).open('w')
            handles.append(err)
        else:
            err = subprocess.STDOUT
        process = subprocess.Popen(command, stdin=stdin, stdout=out, stderr=err)
        processes.append((name, process))
        return process
    reader = None
    try:
        start('can', ['/usr/bin/candump', '-L', 'vcan0'])
        start('virtual', ros('virtual_can_device', 'virtual_can_device_node', '-p', 'interface_name:=vcan0', '-p', 'mode:=normal'))
        start('history', ros('runtime_history', 'runtime_history_node', '-p', f'database_path:={db}'))
        start('monitor', ros('runtime_monitor', 'runtime_monitor_node', '--params-file', str(workspace / 'src/runtime_monitor/config/runtime_monitor.yaml')))
        start('bridge', ros('device_bridge', 'device_bridge_node', '--params-file', str(workspace / 'src/device_bridge/config/device_bridge.yaml'), '-p', f'stage_event_log_path:={stages}'))
        start('executor', ros('task_executor', 'task_executor_node', '--params-file', str(workspace / 'src/task_executor/config/targets.yaml'), '-p', f'stage_event_log_path:={stages}', '-p', f'task_event_capture_path:={events}'))
        start('orchestrator', ros('task_orchestrator', 'task_orchestrator_node'))
        deadline = time.monotonic() + 20
        while not all(ready.values()):
            if time.monotonic() > deadline:
                raise RuntimeError(f'Readiness timeout: {ready}')
            if any(process.poll() is not None for _, process in processes):
                raise RuntimeError('A core node exited before readiness')
            rclpy.spin_once(node, timeout_sec=0.1)
        import sys
        executable = project / 'adapters_ws/install/remote_camera_adapter/lib/remote_camera_adapter/remote_camera_adapter'
        reader = start('adapter', [str(executable), str(run), '--ros-args',
                                  '--params-file', str(workspace / 'src/perception_task_adapter/config/perception_task_adapter.yaml'),
                                  '-p', 'input_mode:=camera', '-p', f'stream_duration_seconds:={float(args.duration)}'],
                       stdin=sys.stdin.buffer, stdout='frames.jsonl')
        print(f'LIVE_READY {run}', flush=True)
        deadline = time.monotonic() + args.duration
        last_count = -1
        second_frame = None
        while time.monotonic() < deadline:
            if any(process.poll() is not None for _, process in processes):
                raise RuntimeError('A stream/runtime process exited; inspect logs')
            frames, terminal = lines(telemetry), lines(events)
            triggers = [row for row in frames if row['submitted']]
            state = {'frames': len(frames), 'last_ids': frames[-1]['ids'] if frames else [],
                     'submissions': len(triggers), 'terminal_tasks': len(terminal)}
            temporary = run / 'status.tmp'
            temporary.write_text(json.dumps(state) + '\n')
            temporary.replace(run / 'status.json')
            if len(terminal) != last_count:
                print('LIVE_STATE ' + json.dumps(state), flush=True)
                last_count = len(terminal)
            if len(terminal) > 2 or len(triggers) > 2:
                raise RuntimeError('More than two tasks triggered during the experiment')
            if len(terminal) == 2:
                if second_frame is None:
                    second_frame = frames[-1]['frame'] if frames else 0
                quiet = [row for row in frames if row['frame'] > second_frame and 10 in row['ids']]
                if len(quiet) >= 10:
                    break
            time.sleep(0.2)
        else:
            raise RuntimeError('Experiment timeout before two marker presentations completed')
        frames, terminal = lines(telemetry), lines(events)
        indices = [index for index, row in enumerate(frames) if row['submitted']]
        if len(indices) != 2 or len(terminal) != 2:
            raise RuntimeError('Expected exactly two submissions and two task results')
        for index in indices:
            if index < 2 or not all(10 in row['ids'] and 20 not in row['ids'] for row in frames[index-2:index+1]):
                raise RuntimeError('A submission lacks three matching source frames')
        between = frames[indices[0]+1:indices[1]]
        first_empty = next((index for index, row in enumerate(between) if not set(row['ids']) & {10, 20}), len(between))
        held_frames = sum(10 in row['ids'] for row in between[:first_empty])
        missing, longest = 0, 0
        for row in between:
            missing = missing + 1 if not set(row['ids']) & {10, 20} else 0
            longest = max(longest, missing)
        if held_frames < 10 or longest < 5:
            raise RuntimeError(f'Hold/rearm evidence insufficient: hold={held_frames}, empty={longest}')
        if any((event['target_id'], event['outcome'], event['error_code']) != ('dock_a', 0, 0) for event in terminal):
            raise RuntimeError('A workflow did not complete with its expected protocol outcome')
        with sqlite3.connect(db) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute('SELECT * FROM task_runs')]
        if len(rows) != 2 or {row['task_id'] for row in rows} != {event['task_id'] for event in terminal}:
            raise RuntimeError('SQLite does not match the two terminal task identities')
        by_id = {event['task_id']: event for event in terminal}
        if any(row[key] != by_id[row['task_id']][key] for row in rows for key in ('target_id', 'outcome', 'error_code')):
            raise RuntimeError('SQLite results differ from terminal TaskEvents')
        (run / 'sqlite-records.json').write_text(json.dumps(rows, indent=2) + '\n')
        summary.update(status='PASS', frames=len(frames), submissions=2, terminal_tasks=2,
                       first_hold_frames_without_repeat=held_frames, longest_empty_streak=longest,
                       trigger_frame_numbers=[frames[index]['frame'] for index in indices],
                       task_ids=[event['task_id'] for event in terminal], sqlite_rows=len(rows))
    except Exception as error:
        summary.update(status='FAIL', error=str(error))
        raise
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        for handle in handles:
            handle.close()
        node.destroy_node()
        rclpy.shutdown()
        can_text = (run / 'can.log').read_text() if (run / 'can.log').exists() else ''
        packets = re.findall(r'vcan0\s+(100|101)#([0-9A-Fa-f]{16})', can_text)
        commands = [bytes.fromhex(value) for frame, value in packets if frame == '100']
        responses = [bytes.fromhex(value) for frame, value in packets if frame == '101']
        summary['can_commands'] = len(commands)
        summary['can_responses'] = len(responses)
        command_ids = {cmd[1:3] for cmd in commands}
        response_ids = {ack[1:3] for ack in responses}
        summary['can_ack_ids_match'] = len(commands) == len(responses) == len(command_ids) == 2 \
            and command_ids == response_ids and all(ack[3] == 0 for ack in responses) \
            and all(cmd[3] == 1 and int.from_bytes(cmd[4:8], 'big', signed=True) == 42 for cmd in commands)
        if summary['status'] == 'PASS' and not summary['can_ack_ids_match']:
            summary.update(status='FAIL', error='CAN command/ACK evidence mismatch')
        (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if summary['status'] != 'PASS':
        raise RuntimeError(summary.get('error', 'Experiment failed'))
    print('LIVE_PASS ' + json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
