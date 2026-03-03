# QQ Bot 配置技能 (安全版)

## 🎯 目标
安全地为 OpenClaw 添加 QQ Bot 配置，避免直接修改配置文件导致网关崩溃。

## ⚠️ 之前的问题
直接使用 `sed` 等文本工具修改 JSON 配置文件容易导致：
- JSON 格式错误
- 配置丢失
- 网关无法启动

## ✅ 正确的做法
使用专门的 Node.js 脚本，通过 JSON 解析来安全地修改配置。

## 📦 使用方法

### 方法一：使用安全脚本（推荐）

```bash
# 执行配置脚本
node /home/node/.openclaw/workspace/skills/config-qqbot-safe.js <AppID> <AppSecret> [Token]

# 示例
node /home/node/.openclaw/workspace/skills/config-qqbot-safe.js 102886849 BHNTZgnu18FMUcks08GPYhqz8HRblv5F ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM
```

### 方法二：手动步骤

1. **备份当前配置**
```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup
```

2. **使用 Node.js 修改配置**
```javascript
const fs = require('fs');
const config = JSON.parse(fs.readFileSync('~/.openclaw/openclaw.json', 'utf8'));
config.channels.qqbot = {
  enabled: true,
  appId: '102886849',
  clientSecret: 'BHNTZgnu18FMUcks08GPYhqz8HRblv5F',
  token: 'ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM'
};
fs.writeFileSync('~/.openclaw/openclaw.json', JSON.stringify(config, null, 2));
```

3. **验证配置**
```bash
cat ~/.openclaw/openclaw.json | grep -A 5 '"qqbot"'
```

4. **重启网关（如需要）**
```bash
# 找到网关进程
ps aux | grep openclaw-gateway

# 重启（可选，某些情况下配置会热重载）
kill <PID>
```

## 🔧 故障恢复

如果配置出错，立即恢复备份：

```bash
# 恢复备份
cp ~/.openclaw/openclaw.json.backup ~/.openclaw/openclaw.json

# 验证恢复成功
cat ~/.openclaw/openclaw.json | grep '"qqbot"'
# 应该没有输出或显示旧配置
```

## 📋 配置参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| appId | QQ 开放平台的机器人 ID | 102886849 |
| clientSecret | QQ 机器人密钥 | BHNTZgnu18FMUcks08GPYhqz8HRblv5F |
| token | 可选的额外令牌 | ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM |

## ✅ 验证清单

- [ ] 配置文件已备份
- [ ] JSON 格式正确
- [ ] QQ Bot 配置已添加
- [ ] 网关进程正常运行
- [ ] 可以在 QQ 中添加机器人并对话

## 🚀 下一步

配置完成后：
1. 重启 OpenClaw Gateway（如果需要）
2. 在 QQ 中搜索并添加机器人
3. 发送测试消息
4. 确认消息能够正常收发

## 📝 最佳实践

1. **始终先备份**再修改配置
2. **使用 JSON 工具**而不是文本工具
3. **修改后验证**配置是否正确
4. **小步测试**，确认每一步都正常
5. **记录变更**，方便回滚

---

创建时间：2026-03-02  
版本：1.0  
作者：AI Assistant
