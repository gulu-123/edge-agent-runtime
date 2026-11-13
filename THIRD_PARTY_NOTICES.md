# Third-party software

This repository ships its own adapter, integration scripts and documentation.
It fetches the upstream runtime separately at the commit in
[`config/upstream.json`](config/upstream.json).

| Dependency | Use | License |
|---|---|---|
| [Quchaosheng/embodied-agent-runtime](https://github.com/Quchaosheng/embodied-agent-runtime) | Task runtime, original perception/trigger library and test stack | Apache-2.0 |
| [ROS 2](https://github.com/ros2) | Nodes, Actions, ament and messages | See individual packages; predominantly Apache-2.0 |
| [OpenCV](https://github.com/opencv/opencv) | ArUco detection and JPEG decoding | Apache-2.0 for the validated 4.6 release |
| [GStreamer](https://gstreamer.freedesktop.org/) | Board-side V4L2 capture and JPEG stream | See installed plugins; core LGPL-2.1-or-later |
| [OpenSSH](https://www.openssh.com/) | Authenticated stream transport | BSD-style licenses |
| [PyYAML](https://github.com/yaml/pyyaml) | Runtime configuration | MIT |

The upstream runtime also uses BehaviorTree.CPP, gRPC, Protobuf, SQLite and
can-utils. Its [dependency notices](https://github.com/Quchaosheng/embodied-agent-runtime/blob/93a30014b0a260c92a1d3593889afb6dec94e257/THIRD_PARTY_NOTICES.md)
describe those components. This source-only distribution does not relicense
third-party software or distribute a board firmware image.
