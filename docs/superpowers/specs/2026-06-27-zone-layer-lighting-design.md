# MelGeek Reactive RGB — 区域分层灯效系统设计规格

日期：2026-06-27
版本：v2.1.0
状态：待实现

---

## 1. 概述

### 1.1 目标
将现有「单选灯效」架构重构为「三大区域 × Base + Reactive 双槽」系统：

- **三大区域**：字符区（70 灯）、背板区（189 灯）、侧边灯条（26 灯）
  - **注意**：字符区中空格键位置有 3 个灯位参数（lampId 61/62/63），但硬件上实际可能只有 1 个灯珠发光。渲染时仍按 70 灯珠计算，HID 协议发送完整 70 色，不亮的灯珠收到颜色无物理效果。
- **每区双槽**：Base（背景灯效）+ Reactive（响应灯效）
- **跨区域拼合**：只要区域不同，任何灯效都可以同时运行
- **向后兼容**：现有 `reactive_config.json` 自动迁移到 v2 格式

### 1.2 现有架构问题

1. **单选模式**：一次只能运行一个 effect，无法「彩虹 + 音频氛围」同时存在
2. **区域硬编码**：`compose_frame` 把 3 个区域写死绑定，背板只能用频谱渲染
3. **无图层/混合**：没有透明度、混合模式的抽象，叠加只能靠手工 `lerp_rgb`

### 1.3 设计原则

- **渐进交付**：先重构架构（支持 Base+Reactive），再扩展灯效
- **向后兼容**：v1 配置自动迁移，不破坏现有用户体验
- **区域隔离**：每个区域独立渲染，数据不交叉
- **注册表扩展**：新增灯效只需实现接口 + 注册，不修改核心管线

---

## 2. 数据模型

### 2.1 新配置格式（version: 2）

```json
{
  "version": 2,
  "theme": "noir",
  "global": {
    "brightness": 1.0,
    "fps": 60
  },
  "zones": {
    "keys": {
      "base": {
        "effect": "rainbow",
        "params": { "style": "diagonal", "speed": 1.0, "saturation": 0.68, "value": 0.62 }
      },
      "reactive": {
        "effect": "pressure_dent",
        "params": { "attack": 0.89, "release": 0.28, "color_floor": 0.27 }
      },
      "blend_mode": "add"
    },
    "backplate": {
      "base": {
        "effect": "static",
        "params": {}
      },
      "reactive": {
        "effect": "audio_spectrum",
        "params": { "motion": 1.0 }
      },
      "blend_mode": "normal"
    },
    "sides": {
      "base": {
        "effect": "breathing",
        "params": { "speed": 0.8, "depth": 1.0 }
      },
      "reactive": {
        "effect": "audio_vu",
        "params": { "curve": 0.62 }
      },
      "blend_mode": "add"
    }
  },
  "audio": {
    "mode": "loopback",
    "sensitivity": 1.0,
    "bass_sensitivity": 1.0
  },
  "startup": {
    "pressure_source": "native",
    "pressure_port": 8766,
    "open_pressure_page": false,
    "keyboard_fallback": false
  }
}
```

### 2.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | int | 配置格式版本，v1 未设默认为 1 |
| `theme` | str | 全局主题名称，影响所有灯效的默认配色 |
| `zones` | dict | 三大区域配置 |
| `zones.{zone}.base` | dict \| null | 背景灯效，持续运行 |
| `zones.{zone}.reactive` | dict \| null | 响应灯效，依赖输入触发 |
| `zones.{zone}.blend_mode` | str | 混合模式：`normal` / `add` / `multiply` / `screen` |
| `zones.{zone}.*.effect` | str | 灯效名称，见 §4 注册表 |
| `zones.{zone}.*.params` | dict | 灯效专属参数 |

### 2.3 混合模式定义

| 模式 | 公式（每通道 0-255） | 效果 |
|------|---------------------|------|
| `normal` | `reactive` 直接覆盖 base | 响应层完全替换背景 |
| `add` | `min(base + reactive, 255)` | 响应层叠加到背景上，变亮 |
| `multiply` | `base * reactive / 255` | 响应层与背景相乘，变暗 |
| `screen` | `255 - (255-base)*(255-reactive)/255` | 滤色，适合发光效果 |

---

## 3. 向后兼容

### 3.1 自动迁移规则

v1 配置不含 `version` 字段，检测到后自动迁移：

| v1 effect | 迁移后 zones 配置 |
|-----------|------------------|
| `static` | 三区 base = static，reactive = null |
| `breathing` | 三区 base = breathing，reactive = null |
| `rainbow` | 三区 base = rainbow，reactive = null |
| `ripple` | 字符区 reactive = ripple，其他 base = static |
| `audio_ambient` | 背板 reactive = audio_spectrum，侧边 reactive = audio_vu，字符区 base = static |
| `pressure_dent` | 字符区 reactive = pressure_dent，其他 base = static |
| `premium_reactive` | 字符区 reactive = pressure_dent，背板 reactive = audio_spectrum，侧边 reactive = audio_vu |

### 3.2 迁移流程

1. 启动时读取 `reactive_config.json`
2. 若无 `version` 字段，视为 v1
3. 按规则生成 v2 配置
4. 写入 `reactive_config.json`，备份原文件为 `.bak`
5. 日志记录迁移过程

---

## 4. 灯效注册表

### 4.1 接口定义

每个灯效实现必须遵循：

```python
class ZoneEffect(ABC):
    """区域灯效基类"""

    name: str              # 注册名，如 "rainbow"
    effect_type: str       # "base" 或 "reactive"
    applicable_zones: set[str]  # {"keys", "backplate", "sides"}

    @abstractmethod
    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        """
        渲染一帧。
        返回：该区域所有灯珠的 RGB 值列表，长度必须等于区域灯珠数。
        """

    @abstractmethod
    def param_schema(self) -> list[dict]:
        """返回该灯效的 UI 参数定义（与现有 PARAM_SCHEMA 格式一致）"""
```

### 4.2 现有灯效迁移

| 灯效 | 类型 | 适用区域 | 说明 |
|------|------|---------|------|
| `static` | Base | all | 全区域统一固定色 |
| `breathing` | Base | all | 全局正弦波呼吸 |
| `rainbow` | Base | all | 空间彩虹流动（5 种风格） |
| `ripple` | Reactive | keys, backplate | 按键触发涟漪扩散 |
| `pressure_dent` | Reactive | keys | 按键压力热力 |
| `audio_spectrum` | Reactive | backplate | 音频频谱柱（原背板渲染） |
| `audio_vu` | Reactive | sides | 音频 VU 表（原侧边渲染） |

### 4.3 新增灯效清单

| 灯效 | 类型 | 适用区域 | 输入依赖 | 优先级 |
|------|------|---------|---------|--------|
| `typewriter` | Reactive | keys | keyboard events | P1 |
| `starfield` | Base | backplate, sides | time + random | P1 |
| `wave` | Base | all | time + position | P1 |
| `chase` | Base | sides | time | P2 |
| `gradient` | Base | all | time + position | P2 |
| `matrix_rain` | Base | backplate | time + random | P2 |
| `aurora` | Base | backplate | time + position | P3 |
| `reactive_keys` | Reactive | keys | keyboard events | P3 |

---

## 5. 渲染管线

### 5.1 每帧流程

```
输入采集（压力 / 音频 / 时间 / 按键事件）
    │
    ▼
┌─────────────────┬─────────────────┬─────────────────┐
│   字符区渲染     │   背板区渲染     │   侧边区渲染     │
│                 │                 │                 │
│  base.render()  │  base.render()  │  base.render()  │
│       ↓         │       ↓         │       ↓         │
│  70 RGB         │  189 RGB        │  26 RGB         │
│       ↓         │       ↓         │       ↓         │
│ reactive.render()│ reactive.render()│ reactive.render()│
│       ↓         │       ↓         │       ↓         │
│  70 RGB         │  189 RGB        │  26 RGB         │
│       ↓         │       ↓         │       ↓         │
│ blend(mode)     │ blend(mode)     │ blend(mode)     │
│       ↓         │       ↓         │       ↓         │
│  70 RGB         │  189 RGB        │  26 RGB         │
└─────────────────┴─────────────────┴─────────────────┘
    │
    ▼
区域合并（concat）→ 285 RGB
    │
    ▼
全局处理（亮度缩放 / 伽马校正 / 限幅）→ HID 发送
```

### 5.2 关键设计

- **区域隔离**：每个 `render()` 只知道自己负责哪些灯珠，通过 `ZoneMask` 过滤
- **NULL 处理**：base 或 reactive 任一设为 `null` 时，直接使用另一层输出；都为 null 则区域全黑
- **性能**：3 个区域可并行计算，但当前单线程也足够 60fps
- **混合统一**：`blend(a, b, mode)` 是纯数学函数，不感知灯效类型

---

## 6. UI 设计

### 6.1 双模式设计

| 模式 | 显示内容 | 目标用户 |
|------|---------|---------|
| **初级模式** | 单一下拉框选择全局 effect（与现有 UI 一致） | 普通用户 |
| **高级模式** | 三区域独立配置面板（Base + Reactive + 混合模式） | 进阶用户 |

### 6.2 高级模式面板

- **全局区**：主题选择器、亮度滑块、FPS 设置
- **字符区卡片**：Base 下拉框、Reactive 下拉框、混合模式下拉框、参数折叠面板
- **背板区卡片**：同上
- **侧边区卡片**：同上
- **操作按钮**：保存配置、复制 JSON、重置默认

### 6.3 交互细节

- 下拉框根据区域自动过滤不适用的灯效
- 键盘预览图实时渲染当前组合效果
- 参数面板跟随 PARAM_SCHEMA 动态渲染
- 混合模式有可视化预览（显示叠加前后对比）

---

## 7. 新增灯效详细规格

### 7.1 typewriter（打字机）

- **触发**：检测到新按键按下时
- **效果**：从按下位置向外扩散一道光波，波前为亮色，波尾渐暗
- **参数**：
  - `wave_speed`：扩散速度（0.5-3.0，默认 1.5）
  - `wave_color`：波前颜色（默认主题 accent 色）
  - `decay`：衰减系数（0.5-0.95，默认 0.82）
- **实现**：维护活跃光波列表，每帧更新位置和衰减

### 7.2 starfield（星空）

- **效果**：随机灯珠以不同频率闪烁，偶尔有「流星」从一端划到另一端
- **参数**：
  - `density`：星星密度（0.1-1.0，默认 0.3）
  - `speed`：流星频率（0-1.0，默认 0.2）
  - `twinkle`：闪烁幅度（0-1.0，默认 0.5）
- **实现**：维护星星状态数组（位置、亮度、相位），流星用插值动画

### 7.3 wave（波浪）

- **效果**：正弦波沿 x 或 y 轴传播，形成波浪状明暗变化
- **参数**：
  - `direction`：方向（"horizontal" / "vertical" / "radial"）
  - `speed`：传播速度（0.1-3.0，默认 1.0）
  - `frequency`：波数（0.5-5.0，默认 2.0）
  - `amplitude`：振幅（0-1.0，默认 0.5）
- **实现**：每灯珠计算 `sin(pos * freq + time * speed) * amplitude`

---

## 8. 实现范围与优先级

### Phase 1：架构重构（核心）
- [ ] 定义 `ZoneEffect` 抽象基类
- [ ] 实现 `ZoneRenderer`（三大区域独立渲染）
- [ ] 实现 `BlendEngine`（4 种混合模式）
- [ ] 将现有 7 个灯效迁移为 `ZoneEffect` 子类
- [ ] 实现 v1 → v2 配置自动迁移
- [ ] 重构 `PreviewEngine._loop()` 使用新管线

### Phase 2：新增灯效
- [ ] 实现 `typewriter`
- [ ] 实现 `starfield`
- [ ] 实现 `wave`
- [ ] 实现 `chase`
- [ ] 实现 `gradient`

### Phase 3：UI 更新
- [ ] 新增高级模式切换按钮
- [ ] 实现三区域独立配置面板
- [ ] 下拉框动态过滤（按区域）
- [ ] 混合模式可视化预览
- [ ] 键盘预览图支持多区域实时渲染

### Phase 4：测试与发布
- [ ] 向后兼容测试（v1 配置迁移）
- [ ] 性能测试（60fps 保证）
- [ ] 所有灯效组合测试
- [ ] 打包 v2.1.0 EXE
- [ ] GitHub Release

---

## 9. 风险与注意事项

1. **性能风险**：多区域并行渲染 + 混合计算可能增加 CPU 负载。缓解：当前单线程已足够 60fps，混合操作是纯数学计算，开销极小。
2. **配置复杂度**：v2 配置比 v1 复杂 3 倍。缓解：初级模式隐藏复杂度，用户无需接触 JSON。
3. **HID 带宽**：285 灯珠 × 30-60fps 对 HID 通信是固定负载，架构变更不影响带宽。
4. **向后兼容**：v1 配置迁移后若用户降级到旧版 EXE，新配置会被误解。缓解：迁移后备份原文件，降级后可手动恢复。
5. **空格灯珠硬件限制**：字符区空格键位置参数定义了 3 个 lampId（61/62/63），但硬件实际可能仅 1 个灯珠发光。所有灯效实现仍按 70 灯珠计算，HID 协议发送完整 70 色。涟漪/压力效果扩散到 5 个灯珠（60-64）是为了视觉效果平滑，不受此限制影响。

---

## 10. 参考

- 现有代码：`backend/melgeek68_premium_reactive.py`（渲染核心）
- 现有代码：`backend/main.py`（PreviewEngine、HTTP API）
- 现有配置：`reactive_config.json`
- 键盘参数：`backend/melgeek_keyboard_params.json`
