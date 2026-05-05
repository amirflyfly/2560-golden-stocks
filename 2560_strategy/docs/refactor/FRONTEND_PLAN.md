# 前端分离规划

## 技术选择

- React + Vite
- Ant Design 或 Arco Design
- React Query 管理服务端状态
- Zustand 管理轻量客户端状态
- kline-charts 继续用于 K 线

## 目录建议

```text
frontend/
  src/
    api/
    app/
    components/
    layouts/
    pages/
    routes/
    stores/
    styles/
```

## 迁移顺序

1. 登录页与基础布局
2. 首页看板
3. 策略管理
4. 策略扫描
5. 股票详情和 K 线
6. 选股池
7. 后台管理

## 前端约束

- 所有服务端请求通过 api client。
- 禁止直接拼接旧模板路径。
- 权限显示和路由守卫基于后端返回的 permissions。
- 股票涨跌颜色遵循中国市场习惯：涨红跌绿。
