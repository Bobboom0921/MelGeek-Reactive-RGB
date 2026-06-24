# MelGeek Reactive RGB 最终用户说明

版本：v1.0.1

这是非官方工具，与 MelGeek、Microsoft、Qt、Nuxt 或其他提到的第三方厂商没有从属、赞助、背书或官方支持关系。产品名和商标归各自权利人所有。

最终用户入口：`MelGeekReactiveRGB.exe`

特性：

- 无 CMD 控制台窗口。
- 主控制面板支持最小化到系统托盘。
- 托盘右键可显示窗口、启动灯效、停止灯效、退出。
- WebHID 压力连接使用独立小浏览器窗口。连接后可以最小化到任务栏，但不要关闭。
- 音频来源是系统播放声音，不是麦克风。
- 支持静态、呼吸、彩虹、涟漪、压力热力、音频氛围、综合模式。

首次使用：

1. 双击 `MelGeekReactiveRGB.exe`。
2. 如需压力效果，点击 `Connect WebHID` 或 `浏览器连接`。
3. 在弹出的小窗口中点击 `Connect WebHID`，选择 MelGeek / MADE68 V2。
4. 连接成功后，可以把小窗口最小化到任务栏，但不要关闭。
5. 主控制面板可以关闭，它会缩到系统托盘。

注意：

- 本软件按原样提供，不提供任何担保。使用 HID、灯光控制、WebHID、音频 loopback 或未签名 EXE 时，请自行承担风险。
- 项目原始源码采用 GPLv3-only 开源许可；第三方依赖和设计参考说明见 `THIRD_PARTY_NOTICES.md`。
- 如果切换耳机/音响，音频会自动尝试切换到有声音的输出设备。
- 如果音频没反应，先播放音乐，再重启灯效。
- 如果压力没反应，确认 WebHID 小窗口还开着。
- 如果要彻底关闭软件，请右键系统托盘图标，选择退出。

开发/打包：

运行 `build_single_exe.bat` 生成最终文件：

`outputs\\MelGeekReactiveRGB.exe`
