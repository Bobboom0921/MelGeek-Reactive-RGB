# MelGeek Reactive RGB 开发交接文档

版本：v2.1.2 | 最后更新：2026-06-28

---

## 一、项目架构

```
esc/
├── backend/                    # Python 后端
│   ├── main.py                 # 主入口：WebView2 + HTTP API + 引擎循环
│   ├── melgeek68_premium_reactive.py   # 旧渲染核心（已逐步迁移）
│   ├── melgeek68_direct_hid.py         # HID 底层通信
│   ├── melgeek_native_pressure_probe.py # 原生压力读取
│   ├── effect_registry.py      # 灯效注册表（ZoneEffect 包装）
│   ├── zone_effect.py          # ZoneEffect ABC + RenderContext
│   ├── zone_renderer.py        # 区域渲染器（按 zones 合并）
│   ├── blend_engine.py         # 混合引擎（normal/add/multiply/screen）
│   ├── config_migrator.py      # v1→v2 配置迁移
│   └── new_effects.py          # 新灯效实现（打字机、星空等）
├── ui/
│   └── index.html              # 单一 HTML 文件，包含全部 UI + JS
├── tests/
│   ├── test_zones.py           # 区域系统测试
│   └── test_migrator.py        # 配置迁移测试
├── assets/
│   └── MelGeekReactiveRGB.ico  # 程序图标
├── reactive_config.json        # 默认/当前配置（v2 格式）
├── MelGeekReactiveRGB.spec     # PyInstaller 配置
└── build_single_exe.bat        # 打包脚本
```

## 二、核心数据流

```
物理键盘 HID → PressureState → _loop() ──┐
                                          │
系统音频 WASAPI → AudioState ─────────────┤→ RenderContext → ZoneRenderer → BlendEngine → HID 发送
                                          │
UI API (set_params/update_config) ────────┘
```

关键循环在 `main.py:PreviewEngine._loop()`，30fps：
1. 读取压力 → `pressures, flashes = self._pressure_state.tick_decay()`
2. 读取音频 → `self._audio_state.snapshot()`
3. 构建 `RenderContext` → 传入 `theme/audio/pressures/flashes/params`
4. `renderer.render_frame(ctx)` → 各区域灯效渲染 + 混合
5. HID 发送 + UI 预览更新

## 三、添加新灯效

### 3.1 在 `backend/new_effects.py` 中实现

```python
class MyEffect(ZoneEffect):
    """我的新灯效。"""

    def __init__(self) -> None:
        super().__init__("my_effect", "base", {"keys", "backplate", "sides"})
        # base 型：静态/循环动画（不依赖外部输入）
        # reactive 型：依赖压力/音频（如压力热力、频谱）
        # applicable_zones：该灯效可用在哪些区域

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        """返回 ctx.lamp_count 个 RGB 值。"""
        colors = []
        for i in range(ctx.lamp_count):
            # 你的渲染逻辑
            colors.append((r, g, b))
        return colors

    def param_schema(self) -> list[dict[str, Any]]:
        """定义 UI 参数控件。"""
        return [
            {"key": "speed", "label": "速度", "min": 0.1, "max": 5, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "style", "label": "样式", "type": "select", "options": ["a", "b"]},
        ]
```

**重要规则：**
- 返回值长度 **必须等于 `ctx.lamp_count`**，否则会 `ValueError`
- 需要持久化状态（如 Typewriter 的 waves、Starfield 的 stars）→ 提升为 `self._xxx` 实例属性
- 不要每帧做昂贵计算（如 `load_params_from_cache()`）→ 使用 `ctx.normalized` 和 `ctx.distance_cache`
- 主题色 → `_get_theme(ctx.theme)` 会自动处理 Theme 对象或字符串

### 3.2 注册到 `effect_registry.py`

```python
from new_effects import MyEffect  # 或直接在文件内定义

_EFFECT_REGISTRY = {
    # ... 现有灯效 ...
    "my_effect": MyEffect,
}
```

### 3.3 在 `config_migrator.py` 的 `MIGRATION_RULES` 中定义配置映射

```python
"my_effect": {
    "keys": {"base": {"effect": "my_effect", "params": {}}, "reactive": None, "blend_mode": "normal"},
    "backplate": {"base": {"effect": "my_effect", "params": {}}, "reactive": None, "blend_mode": "normal"},
    "sides": {"base": {"effect": "my_effect", "params": {}}, "reactive": None, "blend_mode": "normal"},
},
```

### 3.4 在 `ui/index.html` 中添加列表项

```html
<li class="effect-item" data-effect="my_effect">
  <span class="icon">🎯</span>
  <span class="name">我的灯效</span>
  <span class="desc">描述文字</span>
</li>
```

### 3.5 更新 `HARD_CODED_EFFECTS`

```javascript
const HARD_CODED_EFFECTS = [
  // ...
  { id: 'my_effect', name: '我的灯效', zones: ['keys', 'backplate', 'sides'] },
];
```

### 3.6 测试

```bash
cd esc && python -m pytest tests/ -v
```

## 四、配置系统（v2 格式）

```json
{
  "version": 2,
  "effect": "premium_reactive",
  "theme": "noir",
  "global": { "brightness": 1, "radius": 13 },
  "audio": { "mode": "loopback", "sensitivity": 1 },
  "effects": { "rainbow": { "speed": 1 } },
  "zones": {
    "keys": { "base": null, "reactive": {"effect": "pressure_dent", "params": {}}, "blend_mode": "normal" },
    "backplate": { "base": null, "reactive": {"effect": "audio_spectrum", "params": {}}, "blend_mode": "normal" },
    "sides": { "base": null, "reactive": {"effect": "audio_vu", "params": {}}, "blend_mode": "normal" }
  }
}
```

**关键规则：**
- `effect`（顶层）只影响简单模式；实际渲染用 `zones`
- `set_params(effect=xxx)` 会根据 `MIGRATION_RULES` 自动更新 `zones`
- 修改参数时 `setConfigValue` 只发送增量（防止覆盖 `zones`）
- `load_config()` 和 `_check_config_reload()` 都会自动调用 `migrate_v1_to_v2()`

## 五、常见 Bug 排查

### 5.1 灯效切换无效
检查 `set_params()` 是否同步更新了 `zones`。简单模式依赖 `MIGRATION_RULES`。

### 5.2 页面完全无响应
检查浏览器控制台（F12 → Console）是否有 JS 错误。常见原因：HTML/JS 语法错误（多余的括号）。

### 5.3 状态每帧重置（如 Typewriter 不动）
检查 `ZoneRenderer` 是否在循环内被重建。应在初始化时构建，配置变化时才重建。

### 5.4 主题颜色覆盖不生效
检查 `RenderContext` 是否传了 Theme 对象而非字符串。`_get_theme()` 需要支持 `Theme` 对象。

### 5.5 动画卡顿、CPU 高
用 `cProfile` 分析：
```python
import cProfile; cProfile.run('_loop_one_frame()', 'prof')
```
常见原因：每帧重复 `load_params_from_cache()` / `normalize_positions()` / `build_distance_cache()`。

### 5.6 涟漪/频谱等涉及多区域的灯效缺失
检查 `applicable_zones` 是否包含该区域，以及 `MIGRATION_RULES` 是否映射正确。

## 六、UI 修改指南

`ui/index.html` 是一个单文件，全部逻辑在内：

| 区域 | 代码位置 | 说明 |
|------|---------|------|
| 灯效列表 | `data-effect` 属性 | 点击 → `apiSet({ effect })` |
| 参数面板 | `renderParamPanel()` | 从 `appState.schema.params[effect]` 动态生成 |
| 主题选择 | `THEME_LABELS` + popover | 点击 → `apiSet({ theme })` |
| 高级模式 | `advanced-toggle` | 切换时发送 zones 配置或 effect |
| 键盘预览 | `.kb-key[data-lamp-id]` | `updatePreviewColors()` 更新颜色 |
| 状态栏 | `pollStatus()` | 每 2 秒轮询 `/api/status` |
| FPS 显示 | `#fps-text` | 实时显示 `st.fps` |

**JS 全局错误捕获**：页面顶部已添加 `window.onerror` 和 `unhandledrejection`，崩溃时会显示红色全屏错误。

## 七、打包发布流程

```bash
# 1. 运行测试
python -m pytest tests/ -v

# 2. 打包 EXE
python -m PyInstaller --noconfirm MelGeekReactiveRGB.spec

# 3. 复制到 outputs
copy dist\MelGeekReactiveRGB.exe outputs\
copy README_USER.md outputs\

# 4. 更新版本号（README.md / README_USER.md / CHANGELOG.md）

# 5. 提交代码
git add -A
git commit -m "feat/fix: ..."
git push origin main

# 6. 创建 GitHub Release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "..." --target main
gh release upload vX.Y.Z outputs/MelGeekReactiveRGB.exe

# 7. 更新桌面快捷方式（如路径变化）
```

## 八、关键类速查

| 类/函数 | 文件 | 职责 |
|---------|------|------|
| `PreviewEngine` | `main.py` | 主引擎：配置管理 + 渲染循环 + API |
| `ZoneEffect` | `zone_effect.py` | 灯效 ABC，子类实现 `render(ctx)` |
| `RenderContext` | `zone_effect.py` | 每帧上下文：theme/audio/pressures/params |
| `ZoneRenderer` | `zone_renderer.py` | 按 zones 调度渲染，调用 BlendEngine |
| `BlendEngine` | `blend_engine.py` | base + reactive 颜色混合 |
| `PressureState` | `melgeek68_premium_reactive.py` | 压力数据解析 + tick_decay |
| `AudioState` | `melgeek68_premium_reactive.py` | 音频采集 + snapshot |
| `create_effect()` | `effect_registry.py` | 工厂函数，按名称创建灯效实例 |
| `migrate_v1_to_v2()` | `config_migrator.py` | 配置迁移 + 备份 |

## 九、环境依赖

```bash
pip install pywebview pystray pillow numpy PyAudioWPatch soundcard sounddevice hidapi pyinstaller
```

## 十、联系方式

- GitHub: https://github.com/Bobboom0921/MelGeek-Reactive-RGB
- 发布页: https://github.com/Bobboom0921/MelGeek-Reactive-RGB/releases

---

> 本文档由 Claude (Anthropic) 在修复 v2.1.0 的 17 个 bug 后编写，供后续维护参考。
