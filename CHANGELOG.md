# Changelog

所有显著的变更都会记录在这个文件中。

## [v2.1.2] - 2026-06-28

### 修复

- **按X直接退出 → 最小化到系统托盘**：添加 `window.events.closing` 事件处理，按X隐藏窗口；托盘"显示"菜单可唤起窗口。

## [v2.1.1] - 2026-06-28

### 新增

- 新增 5 个灯效：打字机 (typewriter)、星空 (starfield)、波浪 (wave)、追逐 (chase)、渐变 (gradient)。
- 区域分层渲染系统：字符区 / 背板区 / 侧边区可独立配置 Base + Reactive + 混合模式。
- UI 右上角 FPS 显示改为实时数据（原硬编码假数字）。

### 修复

- **选择灯效无效**：`set_params()` 同步更新 `zones` 配置，简单模式灯效切换生效。
- **修改参数重置灯效**：UI 同步 `config.effect`；`setConfigValue` 只发送修改部分。
- **页面完全无响应**：移除全局灯效下拉框时遗留多余 `});` 导致 JS 语法错误。
- **主题颜色覆盖丢失**：`RenderContext` 传递 Theme 对象而非字符串；`_get_theme()` 支持 Theme 对象。
- **peak_hold 每帧重置**：提升为 `AudioSpectrumEffect` 实例属性。
- **flashes 压力闪光丢失**：`RenderContext` 新增 `flashes` 字段，`zone_renderer` 传递。
- **配置未执行 v1→v2 迁移**：`load_config()` 和 `_check_config_reload()` 均调用迁移。
- **硬编码返回长度**：`PressureDentEffect`/`AudioSpectrumEffect`/`AudioVuEffect` 改为 `ctx.lamp_count` 动态切片。
- **ZoneRenderer 每帧重建**：初始化时构建，配置变化时才重建。
- **涟漪灯效侧边不参与**：`applicable_zones` 和 `MIGRATION_RULES` 加入 sides。
- **星空灯效"静止"**：闪烁速度 0.5-2.5 → 3.0-8.0；默认 twinkle 0.9、density 0.5。
- **追逐灯效一格一格**：双灯珠插值，保持小数位置平滑过渡。
- **动画卡顿、CPU 高**：Rainbow/Ripple 使用 `ctx.normalized`；PressureDent 缓存 `distance_cache`。

### 优化

- `effect_registry.py` 三个灯效移除每帧 `load_params_from_cache()`/`normalize_positions()` 重复计算。
- `PressureDentEffect` 缓存 `distance_cache`，radius 变化时才重建。

## [v2.1.0] - 2026-06-27

### 新增

- 全新 WebView2 (Edge) + HTML/CSS 桌面控制面板，废弃 PySide6。
- 区域灯效系统：`ZoneEffect` ABC + `BlendEngine` + `ZoneRenderer`。
- v1→v2 配置迁移器（带备份）。
- 高级模式：三区域 Base/Reactive/Blend 独立配置。

### 架构

- 重构目录结构：`backend/` 核心引擎，`ui/` 前端界面，`archive/` legacy 脚本。
- `PreviewEngine._loop()` 重构为区域渲染管线。

### 修复

- HID 写入失败自动重连。
- 日志轮转（10MB × 3 备份）。
- 配置浮点去噪（6 位小数）。
