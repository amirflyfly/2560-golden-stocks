# QQ Bot 配置技能

## 目的
安全地配置 QQ Bot 频道，避免直接修改配置文件导致网关崩溃。

## 安装插件
```bash
npm install @sliverp/qqbot@latest
```

## 配置步骤

### 1. 读取当前配置
```bash
cat ~/.openclaw/openclaw.json
```

### 2. 备份配置文件（重要！）
```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup
```

### 3. 使用 Node.js 脚本安全添加配置
创建一个临时脚本 `add-qqbot.js`：

```javascript
const fs = require('fs');
const path = require('path');

const configPath = path.join(process.env.HOME || process.env.USERPROFILE, '.openclaw', 'openclaw.json');

try {
  // 读取当前配置
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  
  // 备份配置
  fs.writeFileSync(configPath + '.backup', JSON.stringify(config, null, 2));
  
  // 添加或更新 qqbot 配置
  config.channels = config.channels || {};
  config.channels.qqbot = {
    enabled: true,
    appId: process.argv[2] || 'YOUR_APP_ID',
    clientSecret: process.argv[3] || 'YOUR_APP_SECRET',
    token: process.argv[4] || ''
  };
  
  // 写回配置
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  
  console.log('✅ QQ Bot 配置成功添加');
  console.log(`AppID: ${config.channels.qqbot.appId}`);
  console.log(`备份文件：${configPath}.backup`);
} catch (error) {
  console.error('❌ 配置失败:', error.message);
  process.exit(1);
}
```

### 4. 运行脚本
```bash
node add-qqbot.js 102886849 BHNTZgnu18FMUcks08GPYhqz8HRblv5F ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM
```

### 5. 验证配置
```bash
cat ~/.openclaw/openclaw.json | grep -A 5 '"qqbot"'
```

### 6. 重启网关（如果需要）
```bash
# 找到网关进程
ps aux | grep openclaw-gateway

# 重启（让配置生效）
kill <PID>
# 或者让系统自动重启
```

## 快速命令（一键配置）
```bash
# 一键配置 QQ Bot（包含备份）
cat > /tmp/config-qqbot.js << 'EOF'
const fs = require('fs');
const configPath = '/home/node/.openclaw/openclaw.json';
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
fs.writeFileSync(configPath + '.backup', JSON.stringify(config, null, 2));
config.channels.qqbot = {
  enabled: true,
  appId: process.argv[2],
  clientSecret: process.argv[3],
  token: process.argv[4] || ''
};
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log('✅ 配置成功！备份已保存');
EOF

node /tmp/config-qqbot.js 102886849 BHNTZgnu18FMUcks08GPYhqz8HRblv5F ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM
```

## 故障恢复
如果配置错误导致网关无法启动：
```bash
# 恢复备份
cp ~/.openclaw/openclaw.json.backup ~/.openclaw/openclaw.json

# 重启网关
# （根据部署方式重启）
```

## 注意事项
1. **永远先备份**再修改配置
2. 使用 JSON 解析工具而不是 sed 等文本工具
3. 修改后验证 JSON 格式是否正确
4. 网关进程会热重载配置，无需重启（某些情况下）
