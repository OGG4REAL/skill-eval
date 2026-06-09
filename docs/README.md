# Docs Index

本目录是当前 spec coding 的事实源。旧的长设计稿、HTML 评审稿和业务样例材料已经被合并或删除，不再作为实现入口。

## 当前主线

当前产品方向是 `Skill Eval Studio`：围绕 skill 的固定任务、对照实验、run 复盘和结果可信度，建立本地可跑的评估闭环。

当前改造入口：

- [skill-eval-restructure/README.md](skill-eval-restructure/README.md)
- [skill-eval-restructure/current-state.md](skill-eval-restructure/current-state.md)
- [skill-eval-restructure/phase2-13-evaluation-api-and-ui.md](skill-eval-restructure/phase2-13-evaluation-api-and-ui.md)
- [skill-eval-restructure/phase2-14-regression-and-failure-cases.md](skill-eval-restructure/phase2-14-regression-and-failure-cases.md)

## 目录说明

| 路径 | 用途 |
| --- | --- |
| [architecture/](architecture/) | 当前系统架构事实：Agent、工具、workspace、evaluation harness |
| [adr.md](adr.md) | 单文件 ADR，记录关键决策路线 |
| [products/](products/) | 产品定位、对象模型和 roadmap |
| [skill-eval-restructure/](skill-eval-restructure/) | 当前 skill eval 改造的施工文档 |

## 文档维护规则

- 新实现前先看 `skill-eval-restructure/current-state.md`，确认当前阶段。
- 架构事实只写进 `architecture/`，不要再散落到根目录。
- 决策理由写进 `adr.md`，不要新建 ADR 子目录。
- 产品方向写进 `products/`，不要把业务样例或客户材料放回 `docs/`。
- HTML 评审稿只作为临时审阅物，不长期保留在 `docs/`。
