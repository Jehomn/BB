# BB — Claude Code Skills

个人 Claude Code 技能备份仓库。`skills/` 下的技能同步自 `~/.claude/skills/`。

## 技能清单

### 自定义技能
- `bb-analysis` — 双轴分析法深度研究（纵轴历程 + 横轴竞品对比 → PDF 报告）
- `general-standard` — 全局规范总则（思维原则、沟通方式、红线、工程纪律）
- `investor-skill` — 机构投资人分析（行业研究、尽调、BP 分析、投资备忘录）
- `neat-freak` — 知识库洁癖级同步（跨平台 Agent Skill）
- `ppt-builder` — 从源材料生成课件（委托 source-library-builder 做前期筹备）
- `source-library-builder` — 前期资料库搭建（六阶段管道）
- `vet-lit-review` — 兽医文献快报（检索 → 证据提取 → PDF 输出）

### 社区技能（有上游更新源）
- `docx` — Word 文档处理 · [anthropics/skills](https://github.com/anthropics/skills)
- `pdf` — PDF 处理 · [anthropics/skills](https://github.com/anthropics/skills)
- `pptx` — PPT 处理 · [anthropics/skills](https://github.com/anthropics/skills)
- `xlsx` — 电子表格处理 · [anthropics/skills](https://github.com/anthropics/skills)
- `skill-creator` — 技能创建/迭代 · [anthropics/skills](https://github.com/anthropics/skills)
- `frontend-design` — 前端界面设计 · [anthropics/skills](https://github.com/anthropics/skills)
- `ui-ux-pro-max` — UI/UX 设计智能 · [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)

## 更新方式

社区技能检查上游更新：

```bash
# 1. 从 anthropics/skills 拉取最新
cd ~ && git clone --depth 1 https://github.com/anthropics/skills.git anthropics-skills-upstream

# 2. 逐技能 diff 比对
for s in docx pdf pptx xlsx skill-creator frontend-design; do
  diff -rq ~/.claude/skills/$s ~/anthropics-skills-upstream/skills/$s
done

# 3. 有差异则覆盖本地 + BB 仓库
for s in docx pdf pptx xlsx skill-creator frontend-design; do
  rm -rf ~/.claude/skills/$s
  cp -r ~/anthropics-skills-upstream/skills/$s ~/.claude/skills/$s
  rm -rf ~/BB/skills/$s
  cp -r ~/anthropics-skills-upstream/skills/$s ~/BB/skills/$s
done

# 4. UI/UX Pro Max 单独检查
git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git ui-ux-pro-max-upstream
diff -rq ~/.claude/skills/ui-ux-pro-max ~/ui-ux-pro-max-upstream/.claude/skills/ui-ux-pro-max

# 5. 推送
cd ~/BB && git add -A && git commit -m "sync: update community skills" && git push
```

## 结构

```
BB/
├── skills/         # 技能文件夹（与 ~/.claude/skills/ 同步）
│   ├── bb-analysis/
│   ├── docx/
│   ├── ...
│   └── xlsx/
├── .gitignore
└── README.md
```
