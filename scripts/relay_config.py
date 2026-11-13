"""Configuration and shell quoting for the two existing SSH connections."""
import json
from pathlib import Path, PurePosixPath
import re
import shlex


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    for name in ('board', 'runtime'):
        host = config[name]
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*', host['target']):
            raise ValueError(f'{name}.target must be user@hostname or user@IPv4')
        if not 1 <= int(host.get('port', 22)) <= 65535:
            raise ValueError('SSH port must be between 1 and 65535')
        for field in ('identity_file', 'known_hosts_file'):
            if not host.get(field):
                raise ValueError(f'{name}.{field} is required')
    project = config['runtime']['project_dir']
    if not PurePosixPath(project).is_absolute() or any(char in project for char in '\n\r\x00'):
        raise ValueError('runtime.project_dir must be an absolute Linux path')
    camera = config['camera']
    if not re.fullmatch(r'/dev/video[0-9]+', camera['device']):
        raise ValueError('camera.device must be /dev/videoN')
    for field in ('input_width', 'input_height', 'output_width', 'output_height'):
        value = camera[field]
        if type(value) is not int or not 16 <= value <= 4096 or value % 2:
            raise ValueError(f'{field} must be an even integer between 16 and 4096')
    for field, lower, upper in (('fps', 1, 30), ('jpeg_quality', 1, 95)):
        if type(camera[field]) is not int or not lower <= camera[field] <= upper:
            raise ValueError(f'{field} must be between {lower} and {upper}')
    return config


def ssh_args(host):
    identity = Path(host['identity_file']).expanduser().resolve(strict=True)
    known_hosts = Path(host['known_hosts_file']).expanduser().resolve(strict=True)
    return ['ssh', '-i', str(identity), '-p', str(host.get('port', 22)),
            '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
            '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known_hosts}', host['target']]


def receiver_command(project, run_name, duration):
    base = PurePosixPath(project)
    run = str(base / 'runs' / run_name)
    command = shlex.join(['bash', str(base / 'scripts/run-live.sh'), '--run-dir', run, '--duration', str(duration)])
    return run, command


def camera_command(camera, duration):
    return shlex.join([
        'timeout', str(duration + 10), 'gst-launch-1.0', '-q', 'v4l2src',
        'device=' + camera['device'], '!',
        f'video/x-raw,format=NV12,width={camera["input_width"]},height={camera["input_height"]}',
        '!', 'videorate', 'drop-only=true', '!', f'video/x-raw,framerate={camera["fps"]}/1',
        '!', 'videoscale', '!', f'video/x-raw,width={camera["output_width"]},height={camera["output_height"]}',
        '!', 'jpegenc', f'quality={camera["jpeg_quality"]}', '!', 'fdsink', 'fd=1', 'sync=false'])
