# Agent Council - 多 Agent 协作

> 协调多个 AI Agent 共同完成复杂任务

## 📋 技能信息
- **名称**: Agent Council
- **类型**: 多 Agent 协作
- **触发词**: agent 协作、多 agent、协作、council、多智能体

## 🚀 功能特点
- 创建 Agent 委员会讨论复杂问题
- 协调多个专用 Agent 协同工作
- 汇总不同 Agent 的观点形成共识
- 适用于需要多角度分析的复杂任务

## 💡 使用示例
```
用户：启动 Agent Council 讨论这个技术问题
助手：🔄 正在组建 Agent Council...
     1. 创建技术专家 Agent
     2. 创建安全专家 Agent
     3. 创建用户体验专家 Agent
     4. 汇总讨论结果
```

## 📦 实现方式
```javascript
// 多 Agent 协作框架
class AgentCouncil {
  constructor() {
    this.agents = [];
    this.discussion = [];
  }
  
  addAgent(role, expertise) {
    this.agents.push({ role, expertise });
  }
  
  async discuss(topic) {
    const opinions = [];
    for (const agent of this.agents) {
      const opinion = await this.getAgentOpinion(agent, topic);
      opinions.push(opinion);
    }
    return this.synthesize(opinions);
  }
}
```

---
**状态**: ✅ 已安装  
**最后更新**: 2026-03-02
