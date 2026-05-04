# 产品与过程管理文档索引

本目录用于承接 2560 Strategy 后续产品规划、研发过程管理和验收标准。

## 文档列表

- [PRD.md](./PRD.md)：产品定位、用户旅程、功能需求、非功能需求和下一版本范围。
- [ROADMAP.md](./ROADMAP.md)：P0-P6 阶段路线图、交付内容和验收标准。
- [PROCESS.md](./PROCESS.md)：需求、技术方案、任务拆分、质量门禁、发布和缺陷管理流程。
- [ACCEPTANCE_CHECKLIST.md](./ACCEPTANCE_CHECKLIST.md)：按模块组织的验收清单。
- [../OPTIMIZATION_PLAN.md](../OPTIMIZATION_PLAN.md)：基于头脑风暴结果形成的优化方向和已落地清单。

## 推荐使用方式

1. 新需求先写需求卡，确认是否属于 PRD 当前范围。
2. 根据 ROADMAP 确认阶段和优先级。
3. 按 PROCESS 拆技术方案和任务。
4. 开发完成后按 ACCEPTANCE_CHECKLIST 验收。
5. 上线后更新 ROADMAP 状态和优化清单。

## 当前优先级

1. P0：修复 Python/pytest 环境和仓库卫生。
2. P1：完成扫描自动轮询、扫描结果分页、指定 K 线跳转和入池去重。
3. P2：建设选股池复盘状态流转和复盘时间线。
4. P4：先落地最小周报/月报，再增强回测归因。
