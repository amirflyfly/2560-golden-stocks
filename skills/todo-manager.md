# 待办事项管理技能

> 帮助用户管理待办事项、任务清单和日常计划

## 📋 技能信息

- **名称**: Todo List Manager
- **类型**: 生产力工具
- **触发词**: 待办、todo、任务、清单、提醒我、记得、计划

## 🚀 使用方法

### 在对话中使用
当用户提到以下任一触发词时，使用此技能：
- "添加一个待办事项"
- "我的任务清单"
- "提醒我明天开会"
- "今天要做的事情"
- "删除第三个任务"

### 示例
```
用户：添加一个待办：明天下午 3 点开会
助手：✅ 已添加待办事项：明天下午 3 点开会

用户：我的待办清单
助手：
📋 你的待办事项：
1. [ ] 明天下午 3 点开会
2. [ ] 购买 groceries
3. [x] 完成报告

用户：完成第 2 个
助手：✅ 已标记"购买 groceries"为完成
```

## 📦 数据存储

### 方法 1：JSON 文件存储（推荐）
```javascript
const fs = require('fs');
const path = require('path');

const TODO_FILE = path.join(process.env.HOME || process.env.USERPROFILE, '.openclaw', 'todo.json');

class TodoManager {
  constructor() {
    this.todos = this.load();
  }
  
  load() {
    try {
      if (fs.existsSync(TODO_FILE)) {
        return JSON.parse(fs.readFileSync(TODO_FILE, 'utf8'));
      }
    } catch (e) {
      console.error('加载待办事项失败:', e.message);
    }
    return { items: [], nextId: 1 };
  }
  
  save() {
    fs.writeFileSync(TODO_FILE, JSON.stringify(this.todos, null, 2));
  }
  
  add(text, priority = 'normal', dueDate = null) {
    const item = {
      id: this.todos.nextId++,
      text,
      completed: false,
      priority,
      dueDate,
      createdAt: new Date().toISOString()
    };
    this.todos.items.push(item);
    this.save();
    return item;
  }
  
  list(filter = 'all') {
    let items = this.todos.items;
    if (filter === 'active') {
      items = items.filter(i => !i.completed);
    } else if (filter === 'completed') {
      items = items.filter(i => i.completed);
    }
    return items;
  }
  
  complete(id) {
    const item = this.todos.items.find(i => i.id === id);
    if (item) {
      item.completed = true;
      item.completedAt = new Date().toISOString();
      this.save();
      return item;
    }
    return null;
  }
  
  remove(id) {
    const index = this.todos.items.findIndex(i => i.id === id);
    if (index !== -1) {
      this.todos.items.splice(index, 1);
      this.save();
      return true;
    }
    return false;
  }
  
  clear() {
    this.todos.items = [];
    this.save();
  }
}

module.exports = TodoManager;
```

### 方法 2：Markdown 文件存储
```javascript
// 存储为 todo.md 格式
- [ ] 待办事项 1
- [ ] 待办事项 2
- [x] 已完成事项
```

## 🔧 功能列表

### 核心功能
- ✅ 添加待办事项
- ✅ 查看待办清单
- ✅ 标记为完成
- ✅ 删除待办事项
- ✅ 清空已完成
- ✅ 按优先级排序
- ✅ 按日期筛选

### 高级功能
- ⏰ 到期提醒
- 🏷️ 分类/标签
- 📅 重复任务
- 📊 完成统计
- 🔍 搜索任务
- 📤 导出/导入

## 📊 数据格式

```json
{
  "items": [
    {
      "id": 1,
      "text": "明天下午 3 点开会",
      "completed": false,
      "priority": "high",
      "dueDate": "2026-03-03T15:00:00Z",
      "category": "工作",
      "createdAt": "2026-03-02T10:00:00Z"
    },
    {
      "id": 2,
      "text": "购买 groceries",
      "completed": true,
      "priority": "normal",
      "completedAt": "2026-03-02T18:00:00Z",
      "createdAt": "2026-03-02T09:00:00Z"
    }
  ],
  "nextId": 3
}
```

## 🌍 触发词列表

| 触发词 | 说明 |
|--------|------|
| 待办 | 通用待办事项 |
| todo | 待办事项 |
| 任务 | 任务管理 |
| 清单 | 查看清单 |
| 提醒我 | 设置提醒 |
| 记得 | 提醒功能 |
| 计划 | 计划安排 |
| 待办事项 | 完整触发词 |

## 💡 使用示例

### 添加任务
```
用户：添加待办：下午 5 点前提交报告
助手：✅ 已添加：下午 5 点前提交报告 (#1)

用户：提醒我明天早上 9 点开会
助手：✅ 已设置提醒：明天早上 9 点开会 (#2)
```

### 查看任务
```
用户：我的待办清单
助手：
📋 待办事项 (2 个未完成):

🔴 高优先级:
1. [ ] 下午 5 点前提交报告 (#1)

⚪ 普通优先级:
2. [ ] 明天早上 9 点开会 (#2)
```

### 完成任务
```
用户：完成第 1 个
助手：✅ 已完成：下午 5 点前提交报告

用户：完成 #2
助手：✅ 已完成：明天早上 9 点开会
```

### 删除任务
```
用户：删除第 3 个
助手：✅ 已删除任务

用户：清空已完成的
助手：✅ 已清空所有已完成的任务
```

## 📱 高级用法

### 按分类查看
```
用户：工作相关的待办
助手：显示所有标记为"工作"分类的任务
```

### 按日期筛选
```
用户：今天的任务
助手：显示今天到期的任务

用户：这周的计划
助手：显示本周所有任务
```

### 统计信息
```
用户：我的完成情况
助手：
📊 本周统计:
- 完成任务：12 个
- 进行中：3 个
- 完成率：80%
```

## ⚠️ 注意事项

1. **数据持久化**: 确保数据保存到文件
2. **定期备份**: 防止数据丢失
3. **隐私保护**: 敏感信息加密存储
4. **清理机制**: 定期清理过期任务

## 📚 扩展建议

### 与其他工具集成
- 📧 邮件提醒
- 💬 微信/Telegram 通知
- 📅 日历同步
- 🔔 系统通知

### 数据同步
- ☁️ 云端同步
- 🔄 多设备同步
- 📤 导出为 CSV/JSON
- 📥 从其他工具导入

## 📝 版本历史

- **v1.0** (2026-03-02) - 初始版本
  - 基础增删改查
  - 优先级管理
  - 完成状态跟踪

---

**许可证**: MIT  
**最后更新**: 2026-03-02  
**状态**: 📝 待安装
