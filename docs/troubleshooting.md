# 排查说明

## 有 video 节点但无法取图

节点存在不等于传感器探测成功。先读取：

```sh
media-ctl -p -d /dev/media0
dmesg | grep -iE 'ov5695|sensor|dphy'
v4l2-ctl -d /dev/video1 --get-fmt-video
```

现场曾出现 `Unexpected sensor id(000000), ret(-5)` 和媒体链路缺少传感器。
正常关机断电、检查连接并上电后，驱动恢复为 `Detected OV005695 sensor`。
遇到同类现象，应结合连接、供电、设备树与驱动排查，不要直接判定相机损坏。
摄像头模块或排线按厂商说明连接，不带电插拔。

## Device or resource busy

先查看采集节点占用及媒体拓扑，不直接终止已有进程。该实机实验在预览占用主通道时
使用可用的 ISP selfpath。`/dev/video1` 是该板配置，不是所有设备的统一编号。

## Buildroot 的 HOME 与账户主目录不同

用 `echo "$HOME"`、`grep '^root:' /etc/passwd` 核对。SSH 服务读取的账户主目录
可能与当前终端的 HOME 环境变量不同，公钥应放在账户实际主目录的 `.ssh/authorized_keys`。
老版本 Dropbear 可能不支持 Ed25519，需核对版本并使用其支持的密钥。
中转脚本只使用已配置的 SSH 连接，不安装密钥或更改 SSH 服务。

## 虚拟 CAN 不存在

在 Linux 运行端执行 `bash scripts/setup-vcan.sh`，按提示在本机输入 sudo 密码。
虚拟机的 Linux 内核必须支持 vcan。接口在重启后通常需要重新创建。
Windows 中转端不需要创建 vcan。

## 传输连接失败

先分别使用 SSH 登录板子和运行端，确认网络、账号、密钥权限和主机指纹。
VMware NAT 网络可以通过 Windows 中转，使板子与虚拟机分别接受已有 SSH 连接。
填写 `config/local/relay.local.json`，不要把真实地址或密钥提交到 Git。
`StrictHostKeyChecking` 保持开启，不绕过主机指纹错误。

## 为什么 ID 20 能识别，但连续验收不通过

上游默认配置包含 10 和 20。本仓库的两次展示验收固定检查 10 → `single_task/dock_a`，
使用其他 ID 会与实验预期不同。持续展示中的短暂丢检与足够长的移开也有区别：
只有连续五帧无映射标记才会重新启用。

## 为什么成功消息只写 acknowledged

默认虚拟设备没有单独的执行完成状态。匹配 ACK 证明协议响应，不证明电机运动。
保留这一语义，避免把软件确认展示成实测动作完成。
