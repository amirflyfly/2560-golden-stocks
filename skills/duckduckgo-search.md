# DuckDuckGo 搜索技能

## 描述
使用 DuckDuckGo 进行网页搜索（完全免费，无需 API Key）。当用户需要进行网页搜索、查找信息、搜索新闻或任何需要搜索引擎的任务时使用此技能。

## 触发词
搜索、搜索网页、查一下、帮我搜、百度一下、谷歌搜索、duckduckgo

## 安装方式

### 方法一：作为 OpenClaw 技能包
```bash
# 克隆技能仓库（如果有）
git clone https://github.com/sliverp/duckduckgo-search.git
cd duckduckgo-search
openclaw skills install .
```

### 方法二：手动安装
将相关文件复制到技能目录：
```bash
cp -r duckduckgo-search/* ~/.openclaw/workspace/skills/
```

## 使用示例

### 基本搜索
```
搜索：今天天气怎么样
```

### 查找信息
```
帮我搜一下 Node.js 最新版本
```

### 搜索新闻
```
搜索最近的科技新闻
```

## 配置（可选）

如果需要自定义搜索参数，可以在配置中添加：

```json
{
  "skills": {
    "duckduckgo-search": {
      "maxResults": 10,
      "region": "cn-zh",
      "safeSearch": "moderate"
    }
  }
}
```

## 依赖

- Node.js 18+
- `got` 或 `axios`（用于 HTTP 请求）
- `cheerio`（用于解析 HTML，可选）

## 代码实现

以下是一个简单的 DuckDuckGo 搜索实现示例：

```javascript
// skills/duckduckgo-search.js
const https = require('https');

async function search(query, options = {}) {
  const {
    maxResults = 10,
    region = 'cn-zh',
    safeSearch = 'moderate'
  } = options;

  // DuckDuckGo HTML 搜索
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        // 解析搜索结果
        const results = parseResults(data, maxResults);
        resolve(results);
      });
    }).on('error', reject);
  });
}

function parseResults(html, maxResults) {
  // 简单的 HTML 解析
  const results = [];
  const resultRegex = /<a class="result__a" href="([^"]+)">([^<]+)<\/a>/g;
  let match;
  let count = 0;
  
  while ((match = resultRegex.exec(html)) && count < maxResults) {
    results.push({
      title: match[2],
      url: match[1],
      snippet: ''
    });
    count++;
  }
  
  return results;
}

module.exports = { search };
```

## 使用技能

在 OpenClaw 中调用：
```javascript
const duckduckgo = require('./skills/duckduckgo-search');

const results = await duckduckgo.search('OpenClaw AI', {
  maxResults: 5
});

console.log(results);
```

## 注意事项

1. **隐私保护**：DuckDuckGo 注重隐私，不会追踪用户
2. **免费使用**：无需 API Key，完全免费
3. **搜索结果**：返回的结果数量可能有限制
4. **地区设置**：可以根据需要调整搜索地区

## 故障排除

### 搜索失败
- 检查网络连接
- 确认 DuckDuckGo 是否可访问
- 尝试更换搜索关键词

### 结果为空
- 尝试更通用的搜索词
- 检查地区设置是否合适

## 参考资料

- [DuckDuckGo 官方文档](https://duckduckgo.com)
- [DuckDuckGo HTML Search](https://html.duckduckgo.com/html/)
- [OpenClaw Skills](https://docs.openclaw.ai/skills)

---

**技能来源**: @sliverp  
**许可证**: MIT  
**最后更新**: 2026-03-02
