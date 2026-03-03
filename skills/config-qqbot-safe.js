#!/usr/bin/env node
/**
 * QQ Bot 配置脚本
 * 安全地为 OpenClaw 添加 QQ Bot 频道配置
 * 
 * 用法: node config-qqbot-safe.js <appId> <appSecret> [token]
 */

const fs = require('fs');
const path = require('path');

const CONFIG_PATH = path.join(process.env.HOME || '/home/node', '.openclaw', 'openclaw.json');
const BACKUP_PATH = CONFIG_PATH + '.backup';

function main() {
  const [appId, appSecret, token = ''] = process.argv.slice(2);
  
  if (!appId || !appSecret) {
    console.error('❌ 用法：node config-qqbot-safe.js <appId> <appSecret> [token]');
    console.error('示例：node config-qqbot-safe.js 102886849 BHNTZgnu18FMUcks08GPYhqz8HRblv5F ZxoDOfDwSDhyGCzXbwVVIKZ2yChuE7BM');
    process.exit(1);
  }
  
  try {
    // 1. 读取当前配置
    console.log('📖 读取当前配置...');
    const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    
    // 2. 创建备份
    console.log('💾 创建备份...');
    fs.writeFileSync(BACKUP_PATH, JSON.stringify(config, null, 2));
    console.log(`   备份位置：${BACKUP_PATH}`);
    
    // 3. 添加/更新 QQ Bot 配置
    console.log('⚙️  配置 QQ Bot...');
    config.channels = config.channels || {};
    config.channels.qqbot = {
      enabled: true,
      appId: appId,
      clientSecret: appSecret,
      token: token
    };
    
    // 4. 验证配置
    console.log('✅ 验证配置...');
    const validatedConfig = JSON.parse(JSON.stringify(config)); // 确保可序列化
    
    // 5. 写入配置
    console.log('💾 保存配置...');
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    
    // 6. 验证写入成功
    const writtenConfig = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    if (!writtenConfig.channels.qqbot) {
      throw new Error('写入后验证失败：QQ Bot 配置不存在');
    }
    
    console.log('\n✅ QQ Bot 配置成功！');
    console.log(`   AppID: ${appId}`);
    console.log(`   状态：已启用`);
    console.log(`   备份：${BACKUP_PATH}`);
    console.log('\n⚠️  提示：可能需要重启 OpenClaw Gateway 使配置生效');
    console.log('   命令：kill <gateway-pid> 或使用 pm2 restart openclaw');
    
  } catch (error) {
    console.error('\n❌ 配置失败:', error.message);
    
    // 尝试从备份恢复
    if (fs.existsSync(BACKUP_PATH)) {
      console.log('\n🔄 检测到错误，尝试从备份恢复...');
      try {
        fs.copyFileSync(BACKUP_PATH, CONFIG_PATH);
        console.log('✅ 已恢复到之前的配置');
      } catch (recoverError) {
        console.error('❌ 恢复失败:', recoverError.message);
      }
    }
    
    process.exit(1);
  }
}

main();
