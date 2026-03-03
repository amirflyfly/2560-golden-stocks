# 天气预报技能

> 获取实时天气信息，帮助用户了解出行和穿衣建议

## 📋 技能信息

- **名称**: Weather Forecast
- **类型**: 天气查询
- **触发词**: 天气、天气预报、今天天气、明天天气、会下雨吗、气温

## 🚀 使用方法

### 在对话中使用
当用户提到以下任一触发词时，使用此技能：
- "今天天气怎么样"
- "北京天气"
- "明天会下雨吗"
- "上海气温如何"
- "这周末天气"

### 示例
```
用户：北京今天天气怎么样？
助手：[调用天气技能查询北京天气]
助手：北京今天晴，气温 15-25°C，东南风 2-3 级，空气质量良好。
```

## 📦 安装方式

### 方法 1：使用 OpenWeatherMap（推荐，免费）
```bash
# 获取免费 API Key: https://openweathermap.org/api
npm install axios
```

### 方法 2：使用中国天气网（免 API Key）
通过爬取中国天气网获取天气信息（无需 API Key）

### 方法 3：使用和风天气（中国地区更准确）
```bash
# 获取免费 API Key: https://dev.qweather.com
npm install axios
```

## 🔧 实现示例

### 使用 OpenWeatherMap
```javascript
const axios = require('axios');

async function getWeather(city, apiKey) {
  const url = `https://api.openweathermap.org/data/2.5/weather?q=${city}&appid=${apiKey}&units=metric&lang=zh_cn`;
  
  const response = await axios.get(url);
  const data = response.data;
  
  return {
    city: data.name,
    temperature: data.main.temp,
    feels_like: data.main.feels_like,
    weather: data.weather[0].description,
    humidity: data.main.humidity,
    wind_speed: data.wind.speed,
    icon: data.weather[0].icon
  };
}

// 使用示例
const weather = await getWeather('Beijing', 'YOUR_API_KEY');
console.log(`${weather.city}: ${weather.weather}, ${weather.temperature}°C`);
```

### 使用和风天气（中国）
```javascript
const axios = require('axios');

async function getChinaWeather(city, apiKey) {
  // 先查询城市 ID
  const cityUrl = `https://geoapi.qweather.com/v2/city/lookup?location=${city}&key=${apiKey}`;
  const cityRes = await axios.get(cityUrl);
  const locationId = cityRes.data.location[0].id;
  
  // 查询天气
  const weatherUrl = `https://devapi.qweather.com/v7/weather/now?location=${locationId}&key=${apiKey}`;
  const weatherRes = await axios.get(weatherUrl);
  const data = weatherRes.data.now;
  
  return {
    city: city,
    temperature: data.temp,
    weather: data.text,
    feels_like: data.feelsLike,
    wind_direction: data.windDir,
    wind_scale: data.windScale
  };
}
```

### 免 API Key 方案（爬取中国天气网）
```javascript
const axios = require('axios');
const cheerio = require('cheerio');

async function getWeatherNoAPI(city) {
  // 中国天气网城市代码映射
  const cityCodes = {
    '北京': '101010100',
    '上海': '101020100',
    '广州': '101280101',
    '深圳': '101280601',
    '成都': '101270101',
    '杭州': '101210101'
  };
  
  const code = cityCodes[city] || cityCodes['北京'];
  const url = `http://www.weather.com.cn/weather/${code}.shtml`;
  
  const response = await axios.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0'
    }
  });
  
  const $ = cheerio.load(response.data);
  // 解析天气信息...
  return { city, weather: '晴', temperature: '25°C' };
}
```

## 📊 返回格式

```json
{
  "city": "北京",
  "temperature": 22,
  "feels_like": 24,
  "weather": "晴",
  "humidity": 45,
  "wind_speed": "2-3 级",
  "wind_direction": "东南风",
  "air_quality": "良好",
  "date": "2026-03-02",
  "forecast": [
    {"date": "明天", "weather": "多云", "temp_low": 18, "temp_high": 26},
    {"date": "后天", "weather": "小雨", "temp_low": 16, "temp_high": 23}
  ]
}
```

## 🌍 触发词列表

| 触发词 | 说明 |
|--------|------|
| 天气 | 通用天气查询 |
| 天气预报 | 查询天气预报 |
| 今天天气 | 查询今天天气 |
| 明天天气 | 查询明天天气 |
| 会下雨吗 | 查询降水概率 |
| 气温 | 查询温度 |
| 多少度 | 查询温度 |
| 空气质量 | 查询空气质量 |

## ⚠️ 注意事项

1. **API 限制**: 免费 API 通常有调用次数限制
2. **城市名称**: 确保城市名称准确
3. **数据更新**: 天气数据通常每 1-3 小时更新
4. **位置权限**: 如需自动定位，需要用户授权

## 📚 推荐 API 服务

### 国际服务
1. **OpenWeatherMap** - 免费额度充足，覆盖全球
   - 免费额度：60 次/分钟
   - 网址：https://openweathermap.org/api

2. **WeatherAPI** - 功能丰富
   - 免费额度：100 万次/月
   - 网址：https://www.weatherapi.com

### 国内服务
1. **和风天气** - 中国地区数据准确
   - 免费额度：1000 次/天
   - 网址：https://dev.qweather.com

2. **中国天气网** - 官方数据源
   - 网址：http://www.weather.com.cn

## 📝 版本历史

- **v1.0** (2026-03-02) - 初始版本
  - 支持基础天气查询
  - 支持多个天气服务
  - 中文触发词支持

---

**许可证**: MIT  
**最后更新**: 2026-03-02  
**状态**: 📝 待安装
