#!/usr/bin/env node
/**
 * DuckDuckGo 搜索技能
 * 使用 DuckDuckGo 进行网页搜索（完全免费，无需 API Key）
 * 
 * 用法：node duckduckgo-search.js <搜索关键词>
 * 示例：node duckduckgo-search.js OpenClaw AI
 */

const https = require('https');
const http = require('http');

async function search(query, options = {}) {
  const {
    maxResults = 10,
    region = 'wt-wt', // 所有地区
    safeSearch = 'moderate'
  } = options;

  // DuckDuckGo HTML 搜索接口
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    
    const req = client.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const results = parseResults(data, maxResults);
          resolve(results);
        } catch (error) {
          reject(error);
        }
      });
    });
    
    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('搜索超时'));
    });
  });
}

function parseResults(html, maxResults) {
  const results = [];
  
  // 解析 DuckDuckGo HTML 搜索结果
  const lines = html.split('\n');
  let currentResult = null;
  
  for (const line of lines) {
    // 查找结果链接
    const linkMatch = line.match(/<a class="result__a" href="([^"]+)"[^>]*>([^<]+)<\/a>/i);
    if (linkMatch) {
      if (currentResult) {
        results.push(currentResult);
        if (results.length >= maxResults) break;
      }
      currentResult = {
        title: linkMatch[2].trim(),
        url: linkMatch[1].replace(/&amp;/g, '&'),
        snippet: ''
      };
    }
    
    // 查找摘要
    if (currentResult && line.includes('result__snippet')) {
      const snippetMatch = line.match(/>([^<]*)</);
      if (snippetMatch) {
        currentResult.snippet = snippetMatch[1].trim();
      }
    }
  }
  
  // 添加最后一个结果
  if (currentResult && results.length < maxResults) {
    results.push(currentResult);
  }
  
  return results;
}

// 命令行执行
async function main() {
  const args = process.argv.slice(2);
  
  if (args.length === 0) {
    console.log('DuckDuckGo 搜索技能');
    console.log('用法：node duckduckgo-search.js <搜索关键词>');
    console.log('示例：node duckduckgo-search.js OpenClaw AI');
    console.log('\n触发词：搜索、搜索网页、查一下、帮我搜、百度一下、谷歌搜索');
    process.exit(0);
  }
  
  const query = args.join(' ');
  console.log(`🔍 正在搜索：${query}\n`);
  
  try {
    const results = await search(query, { maxResults: 10 });
    
    if (results.length === 0) {
      console.log('未找到相关结果');
      return;
    }
    
    console.log(`找到 ${results.length} 条结果：\n`);
    
    results.forEach((result, index) => {
      console.log(`${index + 1}. ${result.title}`);
      console.log(`   ${result.url}`);
      if (result.snippet) {
        console.log(`   ${result.snippet}`);
      }
      console.log('');
    });
  } catch (error) {
    console.error('搜索失败:', error.message);
    process.exit(1);
  }
}

// 导出模块
module.exports = { search };

// 如果直接运行则执行 main
if (require.main === module) {
  main();
}
