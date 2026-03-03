# 文本转语音技能 (TTS)

> 将文本转换为自然的语音，支持多种语言和声音

## 📋 技能信息

- **名称**: Text-to-Speech (TTS)
- **类型**: 语音合成
- **触发词**: 朗读、语音、读出来、说、播报、TTS

## 🚀 使用方法

### 在对话中使用
当用户需要将文本转换为语音时：
- "把这句话读出来"
- "用语音告诉我"
- "朗读这段文字"
- "生成语音"

### 示例
```
用户：用语音说"你好，欢迎使用 OpenClaw"
助手：🔊 [生成语音并播放]
     语音："你好，欢迎使用 OpenClaw"
     声音：默认
     时长：2.3 秒
```

## 📦 支持的 TTS 服务

### 1. ElevenLabs（推荐，高质量）
```bash
npm install elevenlabs
```

```javascript
const { ElevenLabsClient } = require('elevenlabs');

const client = new ElevenLabsClient({
  apiKey: 'YOUR_API_KEY'
});

async function textToSpeech(text, voice = 'default') {
  const audio = await client.textToSpeech.convert(voice, {
    text: text,
    model_id: 'eleven_multilingual_v2',
    voice_settings: {
      stability: 0.5,
      similarity_boost: 0.5
    }
  });
  
  return audio; // 返回音频数据
}
```

### 2. Google Cloud TTS
```javascript
const textToSpeech = require('@google-cloud/text-to-speech');
const client = new textToSpeech.TextToSpeechClient();

async function synthesizeText(text) {
  const [response] = await client.synthesizeSpeech({
    input: { text },
    voice: { languageCode: 'zh-CN', name: 'zh-CN-Wavenet-D' },
    audioConfig: { audioEncoding: 'MP3' },
  });
  
  return response.audioContent;
}
```

### 3. Azure Cognitive Services
```javascript
const sdk = require('microsoft-cognitiveservices-speech-sdk');

function synthesizeSpeech(text, subscriptionKey, region) {
  const speechConfig = sdk.SpeechConfig.fromSubscription(subscriptionKey, region);
  speechConfig.speechSynthesisLanguage = 'zh-CN';
  speechConfig.speechSynthesisVoiceName = 'zh-CN-XiaoxiaoNeural';
  
  return new Promise((resolve, reject) => {
    const synthesizer = new sdk.SpeechSynthesizer(speechConfig);
    synthesizer.speakTextAsync(
      text,
      result => {
        resolve(result.audioData);
        synthesizer.close();
      },
      error => {
        reject(error);
        synthesizer.close();
      }
    );
  });
}
```

### 4. 百度语音（中文优化）
```javascript
const AipSpeechClient = require('baidu-aip-sdk').speech;

const client = new AipSpeechClient(APP_ID, API_KEY, SECRET_KEY);

async function baiduTTS(text) {
  const result = await client.text2audio(text, {
    lang: 'zh',
    ctp: 1,
    spd: 5, // 语速
    pit: 5, // 音调
    vol: 5  // 音量
  });
  
  return result.audio;
}
```

## 🌍 支持的声音

### 中文声音
- **xiaoyan**: 晓燕（女声，标准普通话）
- **yaji**: 雅琪（女声，温柔）
- **kangkang**: 康康（男声，稳重）

### 英文声音
- **nova**: 女性，温暖自然（推荐）
- **rachel**: 女性，专业清晰
- **josh**: 男性，深沉有力

### 多语言
- 支持中文、英文、日语、韩语等 30+ 种语言
- 支持多语言混合朗读

## 📊 配置选项

```json
{
  "tts": {
    "provider": "elevenlabs",
    "defaultVoice": "nova",
    "language": "zh-CN",
    "speed": 1.0,
    "pitch": 1.0,
    "volume": 1.0,
    "format": "mp3"
  }
}
```

## 💡 使用场景

### 1. 语音播报
```
用户：把这条消息读出来
内容：明天上午 10 点开会
助手：🔊 [播放语音]
```

### 2. 故事讲述
```
用户：给我讲个故事
助手：好的，从前有座山... 🔊 [语音播放]
```

### 3. 新闻播报
```
用户：播报今天的新闻
助手：🔊 [用新闻播报的声音朗读新闻内容]
```

### 4. 多语言朗读
```
用户：用英文说"Hello, how are you?"
助手：🔊 [英文发音]
```

## ⚠️ 注意事项

1. **API 费用**: 大多数 TTS 服务按字符计费
2. **音频格式**: 支持 MP3、WAV、OGG 等格式
3. **语速控制**: 根据内容调整语速
4. **发音准确**: 专有名词可能需要特殊处理
5. **缓存机制**: 常用文本可缓存减少费用

## 📚 推荐服务对比

| 服务 | 价格 | 质量 | 中文支持 | 免费额度 |
|------|------|------|----------|----------|
| ElevenLabs | 中 | ⭐⭐⭐⭐⭐ | 好 | 1 万字符/月 |
| Google TTS | 低 | ⭐⭐⭐⭐ | 很好 | 100 万字符/年 |
| Azure TTS | 中 | ⭐⭐⭐⭐ | 很好 | 50 万字符/月 |
| 百度语音 | 低 | ⭐⭐⭐ | 优秀 | 100 万字符/年 |

## 📝 版本历史

- **v1.0** (2026-03-02) - 初始版本
  - 支持多种 TTS 服务
  - 多语言支持
  - 语音质量选择

---

**许可证**: MIT  
**最后更新**: 2026-03-02  
**状态**: 📝 待安装
