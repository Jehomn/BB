# 个人介绍页模板 — 苹果风三层堆叠

## 设计规范

从麻醉学系统授课项目（27 本教材 → 109 页 PPT）经过三次迭代定型的最终方案。

### 视觉结构

```
┌──────────────────────────────────────────────────┐
│ 背景: #F5F5F7 (Apple 暖浅灰)                       │
│                                                    │
│   ┌──────────────────┐                             │
│   │ 底层: 深蓝半透明  │  毕江浩  34pt bold          │
│   │ transparency: 88 │  华南农业大学动物医院 16pt   │
│   │ 偏移右下 0.28"   │  手术室主管… 13pt           │
│   │ rectRadius 0.15  │  ─────────                  │
│   │ ┌────────────────┐│  专业认证 10pt              │
│   │ │中层: 白色卡片   ││  · RECOVER CPR 救援师认证  │
│   │ │blur 12 off 4  ││  · 麻醉专科首批存量认证    │
│   │ │opacity 0.10   ││                             │
│   │ │rectRadius 0.12││  行业贡献 10pt              │
│   │ │ ┌────────────┐││  · 大湾区麻醉裁判长 ×3     │
│   │ │ │照片 2:3    │││  · 东西部优秀青年兽医师     │
│   │ │ │contain     │││  · 参译 20万+ 字            │
│   │ │ │blur 14     │││  · CPR 小程序开发者         │
│   │ │ │off 5, 0.14 │││                             │
│   │ │ │round 0.08  │││                             │
│   │ │ └────────────┘││                             │
│   │ └────────────────┘│                             │
│   └──────────────────┘                             │
│    3.9 × 5.85" (2:3)                                │
└──────────────────────────────────────────────────┘
```

### 关键参数

| 层 | 尺寸 | 偏移 | 圆角 | 阴影 |
|----|------|------|------|------|
| 底层（半透明卡片） | pw+0.5, ph+0.5 | 右下 0.28" | 0.15 | 无 |
| 中层（白卡） | pw+0.4, ph+0.4 | 右下 0.12" | 0.12 | blur:12, offset:4, opacity:0.10 |
| 顶层（照片） | pw, ph (3.9×5.85) | 0 | 0.08 | blur:14, offset:5, opacity:0.14 |

### 照片要求
- 比例：2:3（3840×5760）
- 文件：`images/photo_bjh.jpg`（或用 `images/photo.jpg`）
- `sizing: { type: 'contain' }` — 即使比例微小偏差也不拉伸不裁剪
- 照片位置：`px = GX + 0.3`, `py = (SH - ph) / 2`
- 右侧文字起点：`ix = px + pw + 1.0`

### 文字排版
- 姓名：34pt, bold, 模块色
- 单位：16pt, bold
- 职位：13pt, `#6A7A8A`
- 分区标题：13pt, bold, `#9AAAB8`
- 正文条目：15pt，`lineSpacingMultiple: 1.55`
- 最后一行（小程序开发者）可用 `#6A7A8A` 弱化
- 页面不显示页码

## 原版代码

```javascript
function intro(pptx) {
  const s = pptx.addSlide(); s.background = { color: 'F5F5F7' };
  const pw = 3.9, ph = 5.85, px = GX + 0.3, py = (SH - ph) / 2;
  // 底层：深蓝半透明卡片
  s.addShape('rect', { x: px + 0.28, y: py + 0.28, w: pw + 0.5, h: ph + 0.5, fill: { color: C.m1, transparency: 88 }, rectRadius: 0.15 });
  // 中层：白色卡片 + 软阴影
  s.addShape('rect', { x: px + 0.12, y: py + 0.12, w: pw + 0.4, h: ph + 0.4, fill: { color: C.white }, shadow: { type: 'outer', blur: 12, offset: 4, color: '000000', opacity: 0.10 }, rectRadius: 0.12 });
  // 顶层：照片
  s.addImage({ path: 'images/photo_bjh.jpg', x: px, y: py, w: pw, h: ph, sizing: { type: 'contain', w: pw, h: ph }, rounding: 0.08, shadow: { type: 'outer', blur: 14, offset: 5, color: '000000', opacity: 0.14 } });
  // 右侧文字
  const ix = px + pw + 1.0, iw = SW - ix - GX;
  s.addText('毕江浩', { x: ix, y: py + 0.15, w: iw, h: 0.7, fontSize: 34, fontFace: FONT, color: C.m1, bold: true });
  s.addText('华南农业大学动物医院', { x: ix, y: py + 0.9, w: iw, h: 0.35, fontSize: 16, fontFace: FONT, color: C.body, bold: true });
  s.addText('手术室主管 · 培训主管 · 主治医师', { x: ix, y: py + 1.28, w: iw, h: 0.3, fontSize: 13, fontFace: FONT, color: '6A7A8A' });
  s.addShape('rect', { x: ix, y: py + 1.85, w: 1.2, h: 0.015, fill: { color: C.divider } });
  let cy = py + 2.15;
  s.addText('专业认证', { x: ix, y: cy, w: iw, h: 0.32, fontSize: 13, fontFace: FONT, color: '9AAAB8', bold: true }); cy += 0.42;
  s.addText([{ text: '国际兽医复苏再评估运动（RECOVER）CPR 救援师认证', options: { fontSize: 15, color: C.body } }, { text: '\n', options: { fontSize: 5 } }, { text: '中国兽医协会麻醉专科 首批存量专科医师认证', options: { fontSize: 15, color: C.body } }], { x: ix + 0.15, y: cy, w: iw - 0.15, h: 0.92, fontFace: FONT, valign: 'top', lineSpacingMultiple: 1.55 }); cy += 1.18;
  s.addText('行业贡献', { x: ix, y: cy, w: iw, h: 0.32, fontSize: 13, fontFace: FONT, color: '9AAAB8', bold: true }); cy += 0.42;
  s.addText([{ text: '连续三届大湾区医师大会 麻醉竞赛裁判长', options: { fontSize: 15, color: C.body } }, { text: '\n', options: { fontSize: 5 } }, { text: '第十七届东西部小动物临床兽医师大会 优秀青年兽医师（博莱得利）', options: { fontSize: 15, color: C.body } }, { text: '\n', options: { fontSize: 5 } }, { text: '参译出版兽医麻醉相关专业书籍 累计超二十万字', options: { fontSize: 15, color: C.body } }, { text: '\n', options: { fontSize: 5 } }, { text: 'CPR 救援小程序开发者，Vibe Coding 之人', options: { fontSize: 15, color: '6A7A8A' } }], { x: ix + 0.15, y: cy, w: iw - 0.15, h: 1.72, fontFace: FONT, valign: 'top', lineSpacingMultiple: 1.55 });
  // intro — no page number
}
```

### 依赖常量

- `FONT = 'Microsoft YaHei'`
- `C.m1` = 模块色（麻醉项目为深蓝 `'1E5A7A'`，除颤项目同，可按需更换）
- `C.body` = `'172228'`
- `C.white` = `'FFFFFF'`
- `C.divider` = `'B9CAE1'`
- `SW = 13.3`, `SH = 7.5`, `GX = 0.5`

### 个人内容修改指南

替换以下部分即可适配任何人：
1. `images/photo_bjh.jpg` → 新照片路径
2. `毕江浩` → 姓名
3. `华南农业大学动物医院` → 单位
4. `手术室主管 · 培训主管 · 主治医师` → 职位
5. 专业认证列表 → 替换 `text` 数组
6. 行业贡献列表 → 替换 `text` 数组
7. `C.m1` → 按项目模块色调整

### 版本历史

- v1：基础 addImage（麻醉项目初次实现）
- v2：苹果风三层堆叠（麻醉项目最终版，blur 12+14，offset 4+5）
- v3：字体上调 13.5→15pt，标题 10→11pt（除颤项目 v7 适配）
