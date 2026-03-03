# DuckDuckGo 搜索技能

> 使用 DuckDuckGo 进行网页搜索（完全免费，无需 API Key）

## 📋 技能信息

- **名称**: DuckDuckGo Search
- **来源**: @sliverp
- **类型**: 网页搜索
- **API 需求**: 无需 API Key
- **触发词**: 搜索、搜索网页、查一下、帮我搜、百度一下、谷歌搜索、duckduckgo

## 🚀 使用方法

### 在对话中使用
当用户说以下任一触发词时，使用此技能：
- "搜索 XXX"
- "帮我搜一下 XXX"
- "查一下 XXX"
- "XXX 的相关信息"
- "百度一下 XXX"
- "谷歌搜索 XXX"

### 示例
```
用户：搜索 OpenClaw AI
助手：[使用 DuckDuckGo 搜索技能查找相关信息]
```

## 📦 安装

### 方法 1：从 ClawHub 安装（推荐）
```bash
openclaw skills install @sliverp/duckduckgo-search
```

### 方法 2：手动安装
```bash
# 克隆或下载技能文件
git clone https://github.com/sliverp/duckduckgo-search.git
cd duckduckgo-search

# 复制到技能目录
cp duckduckgo-search.js ~/.openclaw/workspace/skills/
cp duckduckgo-search.md ~/.openclaw/workspace/skills/
```

### 方法 3：使用现有实现
如果系统已集成 DuckDuckGo 搜索，可以直接使用内置功能。

## ⚙️ 配置（可选）

在 `~/.openclaw/openclaw.json` 中添加：

```json
{
  "skills": {
    "duckduckgo-search": {
      "enabled": true,
      "maxResults": 10,
      "region": "wt-wt",
      "safeSearch": "moderate"
    }
  }
}
```

## 🔧 技术实现

### Node.js 实现示例
```javascript
const https = require('https');

async function duckduckgoSearch(query, options = {}) {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        // 解析 HTML 获取搜索结果
        const results = parseDuckDuckGoResults(data, options.maxResults || 10);
        resolve(results);
      });
    }).on('error', reject);
  });
}
```

### 使用第三方库
```bash
npm install duck-duck-scrape
```

```javascript
const { search } = require('duck-duck-scrape');

const results = await search('OpenClaw AI', { limit: 10 });
console.log(results.results);
```

## 📊 功能特点

- ✅ 完全免费，无需 API Key
- ✅ 保护隐私，不追踪用户
- ✅ 支持多语言搜索
- ✅ 可自定义搜索结果数量
- ✅ 支持安全搜索过滤

## 🌍 触发词列表

以下词语会触发此技能：

| 触发词 | 说明 |
|--------|------|
| 搜索 | 通用搜索指令 |
| 搜索网页 | 明确网页搜索 |
| 查一下 | 口语化搜索 |
| 帮我搜 | 口语化搜索 |
| 百度一下 | 搜索代称 |
| 谷歌搜索 | 搜索代称 |
| duckduckgo | 指定引擎 |

## ⚠️ 注意事项

1. **网络依赖**: 需要可访问 DuckDuckGo
2. **结果限制**: HTML 接口返回结果数量有限
3. **速率限制**: 避免频繁搜索请求
4. **隐私保护**: DuckDuckGo 不追踪用户，但仍需注意搜索内容

## 🐛 故障排除

### 搜索失败
- 检查网络连接
- 确认 DuckDuckGo 可访问性
- 尝试使用代理

### 结果为空
- 更换搜索关键词
- 调整搜索地区设置
- 检查是否触发反爬虫机制

## 📚 相关资源

- [DuckDuckGo 官网](https://duckduckgo.com)
- [DuckDuckGo HTML Search](https://html.duckduckgo.com/html/)
- [duck-duck-scrape (npm)](https://www.npmjs.com/package/duck-duck-scrape)
- [OpenClaw Skills 文档](https://docs.openclaw.ai/skills)

## 📝 版本历史

- **v1.0** (2026-03-02) - 初始版本
  - 基础搜索功能
  - 支持中文触发词
  - 无需 API Key

---

**技能来源**: @sliverp  
**许可证**: MIT  
**最后更新**: 2026-03-02  
**状态**: ✅ 已安装
