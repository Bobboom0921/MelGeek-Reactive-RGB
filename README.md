# MelGeek Reactive RGB

MelGeek Reactive RGB 是一个面向 MelGeek / MADE68 V2 键盘的非官方 Windows 响应式 RGB 控制面板。它可以根据按键压力和系统播放音频驱动键盘灯效，并提供桌面控制面板和系统托盘常驻体验。

本项目不是 MelGeek、Microsoft、Qt、Nuxt 或本仓库中提到的任何第三方厂商的官方项目，也不代表它们的赞助、背书、授权或技术支持。产品名称和商标归各自权利人所有。

## 功能

- 基于 PySide6 的现代桌面控制面板。
- 支持静态、呼吸、彩虹、涟漪、压力热力、音频氛围、综合响应等灯效。
- 优先使用 native HID 读取压力数据。
- 保留 WebHID 桥接作为压力读取 fallback。
- 通过 PyAudioWPatch 使用 WASAPI loopback 获取系统播放音频。
- 键盘预览支持日间、夜间和跟随系统主题。
- 点击窗口右上角关闭会最小化到系统托盘；彻底退出需要右键托盘图标退出。
- 可打包为无 CMD 控制台窗口的 Windows 单文件 EXE。

## 下载与发布说明

普通用户请从 GitHub Releases 下载打包好的 `MelGeekReactiveRGB.exe`，不要直接下载源码树运行。

使用前请注意：

- 仅面向 Windows。
- 压力灯效依赖兼容的 MelGeek / MADE68 V2 HID 数据。
- 部分压力读取场景可能需要 WebHID 桥接窗口保持打开。
- 音频灯效读取的是系统播放声音，不是麦克风输入。
- 当前 EXE 未进行代码签名，Windows 或安全软件可能提示风险，这是未签名 PyInstaller 单文件程序的常见情况。

## 首次使用

1. 运行 `MelGeekReactiveRGB.exe`。
2. 选择灯效并调整参数。
3. 如果使用压力灯效，按界面提示连接键盘。
4. 如果使用音频灯效，请先通过目标输出设备播放音乐或其他声音。
5. 点击右上角关闭按钮会将主窗口缩到系统托盘。要彻底退出，请右键托盘图标并选择退出。

## 从源码构建

在 Windows 上安装 Python 3.10+，然后运行：

```bat
build_single_exe.bat
```

构建脚本会安装所需依赖、执行项目验证、使用 PyInstaller 打包，并生成：

```text
outputs\MelGeekReactiveRGB.exe
```

常用脚本：

- `install_gui_deps.bat`：安装并验证 PySide6 + QtWebEngine。
- `install_audio_deps.bat`：安装音频采集依赖。
- `verify_all.bat`：运行语法和项目验证。
- `scan_loopback_devices.bat`：列出音频 loopback 设备。
- `MelGeekReactiveRGB.spec`：最终 EXE 的 PyInstaller 配置。

## 项目结构

- `work/reactive_control_panel_modern.py`：主桌面 UI。
- `work/melgeek68_premium_reactive.py`：响应式灯效核心引擎。
- `work/melgeek_keyboard_params.json`：键盘布局和按键元数据。
- `reactive_config.json`：默认运行配置。
- `README_USER.md`：随 Release 附带的最终用户说明。
- `THIRD_PARTY_NOTICES.md`：第三方依赖、设计参考和授权说明。

## 第三方授权

开源依赖、设计参考和相关授权说明见 `THIRD_PARTY_NOTICES.md`。公开发布或二次分发打包 EXE 时，请保留这份文件。

## 开源协议

本项目原创源码采用 GNU General Public License v3.0 only 开源协议。完整协议正文见 `LICENSE`。

本软件按原样提供，不提供任何明示或暗示担保。使用 HID、键盘灯光控制、WebHID、音频 loopback 或未签名 EXE 时，请自行承担风险。第三方组件仍适用它们各自的许可证，详见 `THIRD_PARTY_NOTICES.md`。
