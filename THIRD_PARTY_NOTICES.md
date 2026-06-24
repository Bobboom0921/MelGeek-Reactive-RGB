# 第三方授权说明

本项目使用和/或参考了一些开源软件。下面的清单基于首次公开发布时源码树和 Windows 打包版本中使用到的 Python 包整理。

这是一份实用性的归属和授权说明，不构成法律意见。公开发布或二次分发打包版本时，请保留本文件，并根据上游项目的最新许可证文本自行复核。

## 打包版可能包含的运行时依赖

`MelGeekReactiveRGB.exe` 使用 PyInstaller 打包，可能包含以下运行时组件及其传递依赖。

| 组件 | 已核对版本 | 用途 | 许可证 / 说明 |
| --- | ---: | --- | --- |
| Python | 3.11 构建环境 | 应用运行时 | Python Software Foundation License。见 https://docs.python.org/3/license.html |
| PySide6 | 6.11.1 | Qt 桌面 UI 绑定和 Qt WebEngine 集成 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only。见 https://doc.qt.io/qtforpython-6/licenses.html |
| PySide6_Addons | 6.11.1 | PySide6 使用的 Qt 附加模块 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_Essentials | 6.11.1 | PySide6 使用的 Qt 基础模块 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.11.1 | PySide6 的 Python/C++ 绑定辅助模块 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| numpy | 2.4.6 | 音频信号处理和数值计算 | BSD-3-Clause，并包含额外第三方声明。见 https://numpy.org/doc/stable/license.html |
| PyAudioWPatch | 0.2.12.8 | WASAPI loopback 音频采集 | Apache-2.0。该项目基于 PyAudio/PortAudio 相关工作，见 https://github.com/s0d3s/PyAudioWPatch |
| sounddevice | 0.5.5 | 音频采集 fallback | MIT。见 https://github.com/spatialaudio/python-sounddevice |
| SoundCard | 0.4.6 | 扬声器 loopback fallback | BSD-3-Clause。见 https://github.com/bastibe/SoundCard |
| hidapi / cython-hidapi | 0.15.0 | native HID 键盘通信 | cython-hidapi 和其捆绑的 hidapi 许可证文件包含 BSD 风格和 GPL-3.0 文本。本项目在可用情况下按 permissive/BSD 授权路径使用；请复核 https://github.com/trezor/cython-hidapi 和 https://github.com/libusb/hidapi |
| cffi | 2.0.0 | 音频库依赖 | MIT |
| pycparser | 传递依赖 | cffi 依赖 | BSD-3-Clause |

### PySide6 / Qt LGPL 说明

PySide6 和 Qt 模块同时提供 LGPL/GPL/商业授权路径。本项目当前按 LGPL 授权路径理解和分发。若你分发打包 EXE，请保留 Qt/PySide 相关声明，不要移除 LGPL 要求保留的用户权利。正式生产分发前，建议随 Release 一并提供完整 Qt 许可证文本和依赖元数据。

### PyInstaller 说明

Windows EXE 由 PyInstaller 生成。

| 组件 | 已核对版本 | 用途 | 许可证 / 说明 |
| --- | ---: | --- | --- |
| PyInstaller | 6.21.0 | 打包工具和 bootloader | GPL-2.0-or-later，并带有 PyInstaller bootloader exception，允许分发被打包的应用。见 https://pyinstaller.org/en/stable/license.html |
| altgraph | 0.17.5 | PyInstaller 依赖 | MIT |
| packaging | 26.2 | PyInstaller 依赖 | Apache-2.0 OR BSD-2-Clause |
| pefile | 2024.8.26 | PyInstaller 依赖 | MIT |
| pyinstaller-hooks-contrib | 2026.6 | PyInstaller hook 集合 | hook 的许可证元数据可能随内容变化，见 https://github.com/pyinstaller/pyinstaller-hooks-contrib |
| pywin32-ctypes | 0.2.3 | PyInstaller Windows 依赖 | BSD-3-Clause |

## 设计参考

桌面 UI 的视觉方向参考了现代组件系统，包括 Nuxt UI。

| 参考项目 | 关系 | 许可证 / 说明 |
| --- | --- | --- |
| Nuxt UI, https://github.com/nuxt/ui | 仅作为视觉和产品设计参考。本仓库和打包 EXE 未包含 Nuxt UI 源码、包、图标、编译资源或复制样式。 | Nuxt UI 为 MIT 许可证。请以上游仓库当前许可证文本为准。 |

## 操作系统和设备 API

本应用通过上述依赖以及 Python 标准库中的 `ctypes`、`subprocess`、`http.server` 等模块访问 Windows 音频/HID 能力。本项目不再分发 Windows、MelGeek 固件或 MelGeek 官方软件。

## 项目自身许可证和免责声明

本项目原创源码采用 GNU General Public License v3.0 only 开源协议。完整协议见仓库中的 `LICENSE`。第三方组件仍适用它们各自的许可证。

本项目是非官方项目，与 MelGeek、Microsoft、Qt、Nuxt 或本文提到的其他第三方厂商没有从属、赞助、背书或官方支持关系。产品名称和商标归各自权利人所有。

本软件按原样提供，不提供任何担保。用户和二次分发者在使用或分发前，应自行复核所在地法律、上游许可证、平台规则，以及设备/固件风险。
