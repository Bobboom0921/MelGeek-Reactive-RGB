# MelGeek Reactive RGB — WebView2 桌面版

苹果风格 UI 的独立桌面应用，基于 Python + WebView2(Edge) + HTML/CSS。

---

## 效果预览

双击打开后是一个**独立的窗口**，不是浏览器标签页：

- ✅ 毛玻璃侧边栏（`backdrop-filter: blur`）
- ✅ macOS 风格分段控制器
- ✅ 圆形色卡 + 预设
- ✅ 正确的 MADE68 V2 键盘布局（68% 配列）
- ✅ 背板灯条 + 侧边灯条预览
- ✅ 明暗模式一键切换
- ✅ 系统托盘图标

---

## 快速运行

```bash
cd ui-webview2

# 安装依赖
pip install pywebview pystray pillow

# 运行
python backend/main.py
```

窗口会弹出，加载 `ui/index.html`。

---

## 打包成 .exe

```bash
cd ui-webview2
pip install pyinstaller

pyinstaller --noconfirm --clean --windowed --onefile \
  --name MelGeekReactiveRGB \
  --add-data "ui;ui" \
  --icon ../esc/assets/MelGeekReactiveRGB.ico \
  backend/main.py
```

输出：`dist/MelGeekReactiveRGB.exe`

---

## 项目结构

```
ui-webview2/
├── backend/
│   └── main.py           ← Python 壳（WebView2 窗口 + HTTP 服务器）
├── ui/
│   └── index.html        ← 完整 UI（苹果风格、键盘预览、参数面板）
└── README.md
```

---

## 与现有引擎对接

当前 `main.py` 里的 API 是 stub。接入现有灯效引擎：

1. 把 `melgeek68_premium_reactive.py` 放到 backend/
2. 在 `api_effect_start()` 里启动子进程
3. 通过 WebSocket 或 stdout pipe 向前端推送实时数据

详细对接方案见 `UI_UX_REFACTOR_PLAN.md` 中的"实施建议"章节。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 窗口壳 | Python + pywebview (EdgeChromium) |
| UI 渲染 | HTML5 + CSS3 (Tailwind-like hand-rolled) |
| 字体 | -apple-system / SF Pro / Segoe UI |
| 效果 | CSS backdrop-filter, gradient, transition |
| 后端通信 | localhost HTTP + JS Bridge |
| 托盘 | pystray |
| 打包 | PyInstaller |
