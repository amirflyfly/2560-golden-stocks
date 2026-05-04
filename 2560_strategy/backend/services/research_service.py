from datetime import datetime, timedelta
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from backend.repositories import picks_repo, settings_repo
from backend.services.stock_data_service import get_stock_data_service


POSITIVE_KEYWORDS = [
    '涨停', '突破', '放量', '强势', '龙头', '回踩', '新高', '主升', '连板', '修复', '反包', '高开'
]
NEGATIVE_KEYWORDS = [
    '冲高回落', '炸板', '放量滞涨', '破位', '兑现', '减持', '风险', '分歧', '退潮', '承压', '套牢'
]

ROLE_NAME_MAP = {
    'technical_analyst': '技术分析员',
    'sentiment_analyst': '情绪分析员',
    'risk_officer': '风险官',
    'decision_officer': '决策官',
}


class BaseResearchEngine:
    name = 'base'
    display_name = '基础引擎'

    def analyze(self, pick: Dict[str, Any], analysis_date: str = None) -> Dict[str, Any]:
        raise NotImplementedError


class RuleResearchEngine(BaseResearchEngine):
    name = 'rule'
    display_name = '规则研究引擎'

    def analyze(self, pick: Dict[str, Any], analysis_date: str = None) -> Dict[str, Any]:
        return _analyze_pick_with_rule_engine(pick, analysis_date=analysis_date)


class AgentResearchEngine(BaseResearchEngine):
    name = 'agent'
    display_name = 'Agent研究引擎'

    def analyze(self, pick: Dict[str, Any], analysis_date: str = None) -> Dict[str, Any]:
        return _analyze_pick_with_agent_engine(pick, analysis_date=analysis_date)


ENGINE_REGISTRY = {
    'rule': RuleResearchEngine(),
    'agent': AgentResearchEngine(),
}
DEFAULT_ENGINE = 'rule'


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == '':
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _keyword_score(text: str) -> float:
    score = 50.0
    payload = (text or '').lower()
    for keyword in POSITIVE_KEYWORDS:
        if keyword.lower() in payload:
            score += 8
    for keyword in NEGATIVE_KEYWORDS:
        if keyword.lower() in payload:
            score -= 10
    return _clip(score)


def _recent_hist(code: str, analysis_date: str) -> pd.DataFrame:
    stock_data = get_stock_data_service()
    start_date = (datetime.strptime(analysis_date, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
    df = stock_data.get_stock_hist(code, start_date, analysis_date, adjust='qfq')
    if df is None or df.empty:
        return pd.DataFrame()
    return df.tail(60).copy()


def _resolve_engine_name(engine: str = None) -> str:
    candidate = (engine or os.environ.get('RESEARCH_ENGINE') or DEFAULT_ENGINE).strip().lower()
    return candidate if candidate in ENGINE_REGISTRY else DEFAULT_ENGINE


def get_research_engine(engine: str = None) -> BaseResearchEngine:
    return ENGINE_REGISTRY[_resolve_engine_name(engine)]


def list_research_engines() -> List[Dict[str, Any]]:
    return [
        {
            'name': item.name,
            'display_name': item.display_name,
            'is_default': item.name == DEFAULT_ENGINE,
        }
        for item in ENGINE_REGISTRY.values()
    ]


def _build_summary(metrics: Dict[str, Any]) -> str:
    trend_text = '趋势偏强' if metrics['technical_score'] >= 65 else '趋势一般' if metrics['technical_score'] >= 45 else '趋势偏弱'
    volume_text = '量能活跃' if metrics['capital_score'] >= 65 else '量能平稳' if metrics['capital_score'] >= 45 else '量能不足'
    sentiment_text = '题材情绪正向' if metrics['sentiment_score'] >= 60 else '情绪中性' if metrics['sentiment_score'] >= 45 else '情绪承压'
    risk_text = '风险可控' if metrics['risk_score'] <= 40 else '注意波动' if metrics['risk_score'] <= 60 else '风险偏高'
    return (
        f"{trend_text}，{volume_text}，{sentiment_text}，{risk_text}；"
        f"综合评分 {metrics['research_score']:.1f}，"
        f"价格位置 {metrics['price_position']:.1f}% ，量比 {metrics['volume_ratio']:.2f}。"
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendor_tradingagents_root() -> Path:
    value = (os.environ.get('TRADINGAGENTS_ASHARE_DIR') or '').strip()
    if value:
        return Path(value).expanduser().resolve()
    return _repo_root() / 'vendor' / 'TradingAgents-AShare'


def _normalize_agent_ticker(code: str) -> str:
    clean = str(code or '').strip()
    if not clean:
        return ''
    if clean.startswith(('sh', 'sz', 'bj')):
        return clean
    if clean.startswith(('600', '601', '603', '605', '688', '689', '900')):
        return f'sh{clean}'
    if clean.startswith(('000', '001', '002', '003', '200', '300', '301')):
        return f'sz{clean}'
    if clean.startswith(('430', '830', '831', '832', '833', '835', '836', '837', '838', '839', '870', '871', '872', '873', '874', '875', '876', '877', '878', '879', '880', '881', '882', '883', '884', '885', '886', '887', '888', '889')):
        return f'bj{clean}'
    return clean


def _build_agent_query(pick: Dict[str, Any], analysis_date: str) -> str:
    signal = str(pick.get('signal') or '').strip()
    reason_tag = str(pick.get('reason_tag') or '').strip()
    note = str(pick.get('note') or '').strip()
    prediction_reason = str(pick.get('prediction_reason') or '').strip()
    context = '；'.join([item for item in [signal, reason_tag, note, prediction_reason] if item]) or '无额外备注'
    ticker = _normalize_agent_ticker(pick.get('code', ''))
    name = str(pick.get('name') or ticker or '该标的').strip()
    return (
        f'请基于 {analysis_date} 之前可获得的A股数据，分析 {name}({ticker}) 的短线交易机会。'
        f'重点给出市场、情绪、新闻、基本面、宏观、主力资金、量价结构结论，'
        f'并输出最终交易决策、投资计划、风险提示。附加背景：{context}。'
    )


def _extract_agent_role_view(role: str, name: str, text: str, default_score: float, positive_keywords: List[str], negative_keywords: List[str]) -> Dict[str, Any]:
    payload = str(text or '').strip() or f'{name}暂无明确输出。'
    score = default_score
    for keyword in positive_keywords:
        if keyword in payload:
            score += 4
    for keyword in negative_keywords:
        if keyword in payload:
            score -= 5
    score = round(_clip(score), 2)
    stance = '中性'
    if score >= 68:
        stance = '积极'
    elif score <= 42:
        stance = '谨慎'
    return {
        'role': role,
        'name': name,
        'stance': stance,
        'score': score,
        'view': payload,
    }


def _score_agent_decision(decision: str, plan: str, base_metrics: Dict[str, Any]) -> Dict[str, float]:
    payload = f"{decision or ''} {plan or ''}"
    research_score = _safe_float(base_metrics.get('research_score'))
    risk_score = _safe_float(base_metrics.get('risk_score'))
    if any(keyword in payload for keyword in ['强烈买入', '买入', '增持', '看多', '做多', '关注低吸']):
        research_score += 12
        risk_score -= 8
    if any(keyword in payload for keyword in ['持有', '观察', '等待', '中性']):
        research_score += 2
    if any(keyword in payload for keyword in ['卖出', '减仓', '回避', '谨慎', '高风险', '止损']):
        research_score -= 10
        risk_score += 12
    return {
        'research_score': round(_clip(research_score), 2),
        'risk_score': round(_clip(risk_score), 2),
    }


def _build_agent_outputs(pick: Dict[str, Any], analysis_date: str, result: Dict[str, Any], base_metrics: Dict[str, Any]) -> Dict[str, Any]:
    short_term = result.get('short_term', {}) if isinstance(result, dict) else {}
    decision = str(short_term.get('final_trade_decision') or '').strip()
    plan = str(short_term.get('investment_plan') or '').strip()
    market_report = str(short_term.get('market_report') or '').strip()
    sentiment_report = str(short_term.get('sentiment_report') or '').strip()
    news_report = str(short_term.get('news_report') or '').strip()
    fundamentals_report = str(short_term.get('fundamentals_report') or '').strip()
    macro_report = str(short_term.get('macro_report') or '').strip()
    smart_money_report = str(short_term.get('smart_money_report') or '').strip()
    volume_price_report = str(short_term.get('volume_price_report') or '').strip()
    analyst_traces = short_term.get('analyst_traces', []) if isinstance(short_term.get('analyst_traces', []), list) else []

    score_patch = _score_agent_decision(decision, plan, base_metrics)
    technical_view = '；'.join([item for item in [market_report, volume_price_report] if item]) or '量价与市场分析暂无输出。'
    sentiment_view = '；'.join([item for item in [sentiment_report, news_report, macro_report] if item]) or '情绪与新闻分析暂无输出。'
    risk_view = '；'.join([item for item in [smart_money_report, fundamentals_report, plan] if item]) or '风险与资金分析暂无输出。'
    decision_view = '；'.join([item for item in [decision, plan] if item]) or '交易决策暂无输出。'

    role_views = [
        _extract_agent_role_view('technical_analyst', ROLE_NAME_MAP['technical_analyst'], technical_view, _safe_float(base_metrics.get('technical_score')) + 4, ['突破', '放量', '支撑', '走强', '修复', '强势'], ['破位', '滞涨', '承压', '回落', '走弱']),
        _extract_agent_role_view('sentiment_analyst', ROLE_NAME_MAP['sentiment_analyst'], sentiment_view, _safe_float(base_metrics.get('sentiment_score')) + 3, ['催化', '积极', '改善', '回暖', '利好'], ['分歧', '偏弱', '利空', '回落', '退潮']),
        _extract_agent_role_view('risk_officer', ROLE_NAME_MAP['risk_officer'], risk_view, max(0, 100 - score_patch['risk_score']), ['可控', '支撑', '安全边际', '承接'], ['风险', '止损', '减仓', '回避', '波动']),
        _extract_agent_role_view('decision_officer', ROLE_NAME_MAP['decision_officer'], decision_view, score_patch['research_score'], ['买入', '增持', '关注', '跟踪'], ['卖出', '回避', '减仓', '观望']),
    ]

    bullish_points = []
    caution_points = []
    decision_basis = []
    for text in [market_report, sentiment_report, news_report, fundamentals_report, macro_report, smart_money_report, volume_price_report, plan]:
        snippet = str(text or '').strip()
        if not snippet:
            continue
        if any(keyword in snippet for keyword in ['买入', '增持', '看多', '改善', '走强', '支撑', '放量', '催化']):
            bullish_points.append(snippet[:88])
        if any(keyword in snippet for keyword in ['卖出', '减仓', '回避', '风险', '承压', '回落', '止损', '分歧']):
            caution_points.append(snippet[:88])
        if len(decision_basis) < 4:
            decision_basis.append(snippet[:88])

    bullish_points = bullish_points[:4]
    caution_points = caution_points[:4]
    conflict_level = '低'
    if bullish_points and caution_points:
        conflict_level = '高' if len(bullish_points) >= 2 and len(caution_points) >= 2 else '中'

    final_action = '建议继续观察'
    confidence = '低'
    decision_payload = f'{decision} {plan}'
    if any(keyword in decision_payload for keyword in ['强烈买入', '买入', '增持', '看多']):
        final_action = '建议重点跟踪'
        confidence = '高' if score_patch['risk_score'] <= 48 else '中'
    elif any(keyword in decision_payload for keyword in ['持有', '观察', '等待', '关注']):
        final_action = '建议保留自选'
        confidence = '中'
    elif any(keyword in decision_payload for keyword in ['卖出', '减仓', '回避']):
        final_action = '建议继续观察'
        confidence = '低'

    research_summary = '；'.join([item for item in [decision, plan, market_report, sentiment_report] if item][:4]) or _build_summary(base_metrics)
    debate_summary = ' | '.join([item['name'] + '：' + item['view'] for item in role_views])

    return {
        'analysis_status': 'done',
        'technical_score': round(max(_safe_float(base_metrics.get('technical_score')), _safe_float(role_views[0].get('score'))), 2),
        'sentiment_score': round(max(_safe_float(base_metrics.get('sentiment_score')), _safe_float(role_views[1].get('score'))), 2),
        'capital_score': round(max(_safe_float(base_metrics.get('capital_score')), _safe_float(base_metrics.get('capital_score')) + 3), 2),
        'risk_score': score_patch['risk_score'],
        'research_score': score_patch['research_score'],
        'research_updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_analysis_date': analysis_date,
        'price_position': round(_safe_float(base_metrics.get('price_position')), 2),
        'volume_ratio': round(_safe_float(base_metrics.get('volume_ratio')), 2),
        'trend_bias': 'bullish' if score_patch['research_score'] >= 65 else 'neutral' if score_patch['research_score'] >= 45 else 'bearish',
        'research_summary': research_summary,
        'engine_mode': 'agent',
        'engine_display_name': ENGINE_REGISTRY['agent'].display_name,
        'engine_status': 'ready',
        'engine_note': '已通过 TradingAgents-AShare 编排输出多角色研究结果。',
        'role_views': role_views,
        'consensus': {
            'final_action': final_action,
            'confidence': confidence,
            'summary': debate_summary,
        },
        'debate_panel': {
            'bullish_points': bullish_points,
            'caution_points': caution_points,
            'decision_basis': decision_basis or [decision_view[:88]],
            'conflict_level': conflict_level,
            'final_conclusion': decision or plan or 'TradingAgents-AShare 已完成综合裁决。',
        },
        'final_action': final_action,
        'confidence': confidence,
        'debate_summary': debate_summary,
        'watch_flag': 1 if final_action != '建议继续观察' else int(pick.get('watch_flag') or 0),
        'watch_reason': research_summary if final_action != '建议继续观察' else (pick.get('watch_reason') or ''),
        'agent_raw': {
            'decision': decision,
            'plan': plan,
            'market_report': market_report,
            'sentiment_report': sentiment_report,
            'news_report': news_report,
            'fundamentals_report': fundamentals_report,
            'macro_report': macro_report,
            'smart_money_report': smart_money_report,
            'volume_price_report': volume_price_report,
            'analyst_traces': analyst_traces,
        },
        'analyst_traces': analyst_traces,
    }


def _run_tradingagents_analysis(pick: Dict[str, Any], analysis_date: str) -> Dict[str, Any]:
    root = _vendor_tradingagents_root()
    if not root.exists():
        raise FileNotFoundError(f'TradingAgents-AShare 目录不存在: {root}')

    tradingagents_path = root / 'tradingagents'
    if not tradingagents_path.exists():
        raise FileNotFoundError(f'TradingAgents-AShare 缺少 tradingagents 包目录: {tradingagents_path}')

    pyproject_path = root / 'pyproject.toml'
    if pyproject_path.exists() and sys.version_info < (3, 10):
        raise RuntimeError('TradingAgents-AShare 需要 Python >= 3.10')

    path_value = str(root)
    remove_after = False
    if path_value not in sys.path:
        sys.path.insert(0, path_value)
        remove_after = True

    try:
        graph_module = importlib.import_module('tradingagents.graph')
        config_module = importlib.import_module('tradingagents.default_config')
        trading_graph_cls = getattr(graph_module, 'TradingAgentsGraph')
        default_config = dict(getattr(config_module, 'DEFAULT_CONFIG', {}))
        saved_config = settings_repo.get_tradingagents_runtime_config()

        provider = (
            saved_config.get('llm_provider')
            or os.environ.get('TRADINGAGENTS_PROVIDER')
            or ('openai' if os.environ.get('OPENAI_API_KEY') else '')
            or default_config.get('llm_provider')
            or ''
        ).strip()
        api_key = (
            saved_config.get('api_key')
            or os.environ.get('TRADINGAGENTS_API_KEY')
            or (os.environ.get('OPENAI_API_KEY') if provider == 'openai' else '')
            or default_config.get('api_key')
            or ''
        ).strip()
        if not provider:
            raise RuntimeError('缺少 TRADINGAGENTS_PROVIDER 环境变量或页面配置')
        if not api_key:
            raise RuntimeError('缺少 TRADINGAGENTS_API_KEY 环境变量或页面配置')

        config = dict(default_config)
        config['project_dir'] = str(root)
        config['results_dir'] = str((_repo_root() / 'data' / 'tradingagents_results').resolve())
        config['llm_provider'] = provider
        config['api_key'] = api_key
        backend_url = (
            saved_config.get('backend_url')
            or os.environ.get('TRADINGAGENTS_BASE_URL')
            or (os.environ.get('OPENAI_BASE_URL') if provider == 'openai' else '')
            or ''
        ).strip()
        if backend_url:
            config['backend_url'] = backend_url
        config['deep_think_llm'] = (
            saved_config.get('deep_think_llm')
            or os.environ.get('TRADINGAGENTS_DEEP_MODEL')
            or config.get('deep_think_llm')
        )
        config['quick_think_llm'] = (
            saved_config.get('quick_think_llm')
            or os.environ.get('TRADINGAGENTS_QUICK_MODEL')
            or config.get('quick_think_llm')
        )
        config['max_debate_rounds'] = int(
            saved_config.get('max_debate_rounds')
            or os.environ.get('TRADINGAGENTS_MAX_DEBATE')
            or config.get('max_debate_rounds')
            or 2
        )
        config['max_risk_discuss_rounds'] = int(
            saved_config.get('max_risk_discuss_rounds')
            or os.environ.get('TRADINGAGENTS_MAX_RISK_DEBATE')
            or config.get('max_risk_discuss_rounds')
            or 1
        )

        graph = trading_graph_cls(debug=False, config=config)
        ticker = _normalize_agent_ticker(pick.get('code', ''))
        query = _build_agent_query(pick, analysis_date)
        thread_id = f"watch-{pick.get('id') or ticker}-{analysis_date}"
        return asyncio.run(
            graph.propagate_async(
                company_name=ticker,
                trade_date=analysis_date,
                query=query,
                thread_id=thread_id,
            )
        )
    finally:
        if remove_after:
            try:
                sys.path.remove(path_value)
            except ValueError:
                pass


def _build_role_views(pick: Dict[str, Any], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    technical_score = _safe_float(metrics.get('technical_score'))
    sentiment_score = _safe_float(metrics.get('sentiment_score'))
    capital_score = _safe_float(metrics.get('capital_score'))
    risk_score = _safe_float(metrics.get('risk_score'))
    research_score = _safe_float(metrics.get('research_score'))
    price_position = _safe_float(metrics.get('price_position'))
    volume_ratio = _safe_float(metrics.get('volume_ratio'))

    technical_stance = '看多' if technical_score >= 65 else '中性' if technical_score >= 45 else '谨慎'
    technical_view = (
        f"技术分析员认为 {pick.get('name', '')} 当前{technical_stance}，"
        f"技术分 {technical_score:.1f}，价格位置 {price_position:.1f}% ，量比 {volume_ratio:.2f}。"
    )

    sentiment_stance = '积极' if sentiment_score >= 60 else '平衡' if sentiment_score >= 45 else '偏弱'
    sentiment_view = (
        f"情绪分析员判断题材与信号文本反馈{sentiment_stance}，"
        f"情绪分 {sentiment_score:.1f}，当前信号为 {pick.get('signal', '') or '无明显信号'}。"
    )

    risk_stance = '可控' if risk_score <= 40 else '需控制仓位' if risk_score <= 60 else '偏高'
    risk_view = (
        f"风险官评估波动风险{risk_stance}，风险分 {risk_score:.1f}，"
        f"建议{'常规跟踪' if risk_score <= 40 else '轻仓观察' if risk_score <= 60 else '暂不激进参与'}。"
    )

    decision_score = research_score - risk_score * 0.15 + capital_score * 0.1
    if decision_score >= 62:
        decision_action = '加入自选并连续跟踪'
    elif decision_score >= 48:
        decision_action = '保留观察等待确认'
    else:
        decision_action = '暂列观察名单外'
    decision_view = (
        f"决策官综合技术、情绪、资金与风险后给出结论：{decision_action}，"
        f"综合研究分 {research_score:.1f}。"
    )

    return [
        {'role': 'technical_analyst', 'name': '技术分析员', 'stance': technical_stance, 'score': round(technical_score, 2), 'view': technical_view},
        {'role': 'sentiment_analyst', 'name': '情绪分析员', 'stance': sentiment_stance, 'score': round(sentiment_score, 2), 'view': sentiment_view},
        {'role': 'risk_officer', 'name': '风险官', 'stance': risk_stance, 'score': round(max(0, 100 - risk_score), 2), 'view': risk_view},
        {'role': 'decision_officer', 'name': '决策官', 'stance': decision_action, 'score': round(research_score, 2), 'view': decision_view},
    ]


def _build_debate_panel(role_views: List[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
    role_map = {item.get('role'): item for item in role_views}
    technical = role_map.get('technical_analyst', {})
    sentiment = role_map.get('sentiment_analyst', {})
    risk = role_map.get('risk_officer', {})
    decision = role_map.get('decision_officer', {})

    research_score = _safe_float(metrics.get('research_score'))
    risk_score = _safe_float(metrics.get('risk_score'))
    price_position = _safe_float(metrics.get('price_position'))
    volume_ratio = _safe_float(metrics.get('volume_ratio'))

    bullish_points = []
    caution_points = []
    decision_basis = []

    if _safe_float(technical.get('score')) >= 65:
        bullish_points.append('技术形态维持在偏强区间，趋势分析支持继续跟踪。')
    elif _safe_float(technical.get('score')) >= 45:
        bullish_points.append('技术面未明显走坏，但仍需要等待进一步确认。')
    else:
        caution_points.append('技术分偏弱，说明趋势结构还不够稳定。')

    if _safe_float(sentiment.get('score')) >= 60:
        bullish_points.append('情绪分析显示题材与信号反馈偏积极，具备继续发酵条件。')
    elif _safe_float(sentiment.get('score')) < 45:
        caution_points.append('题材情绪与文本信号偏弱，缺少持续催化。')
    else:
        decision_basis.append('情绪处于中性区，需结合后续资金承接判断。')

    if volume_ratio >= 1.2:
        bullish_points.append(f'当前量比 {volume_ratio:.2f}，资金活跃度对走势形成支持。')
    elif volume_ratio <= 0.85:
        caution_points.append(f'当前量比 {volume_ratio:.2f}，量能不足意味着上行动力偏弱。')
    else:
        decision_basis.append(f'量比 {volume_ratio:.2f} 处于平衡区，更多取决于后续放量确认。')

    if risk_score <= 40:
        decision_basis.append('风险官认为波动风险仍可控，可以保持常规跟踪。')
    elif risk_score <= 60:
        caution_points.append('风险官建议控制仓位，说明追高容错率有限。')
    else:
        caution_points.append('风险分偏高，波动与回撤压力较大。')

    if price_position >= 88:
        caution_points.append(f'价格位置已达 {price_position:.1f}%，短线存在高位承压风险。')
    elif price_position <= 35:
        bullish_points.append(f'价格位置仅 {price_position:.1f}%，若趋势修复存在较好性价比。')
    else:
        decision_basis.append(f'价格位置 {price_position:.1f}% 处于中段，适合等待方向进一步明确。')

    conflict_level = '低'
    if bullish_points and caution_points:
        conflict_level = '高' if len(caution_points) >= 2 and len(bullish_points) >= 2 else '中'

    decision_basis.append(decision.get('view', '决策官暂未给出明确意见。'))
    final_conclusion = '多头论据占优，但风险提示仍需纳入执行纪律。' if research_score >= 60 and risk_score <= 58 else '当前多空分歧仍在，适合观察而非激进动作。'

    return {
        'bullish_points': bullish_points,
        'caution_points': caution_points,
        'decision_basis': decision_basis,
        'conflict_level': conflict_level,
        'final_conclusion': final_conclusion,
    }


def _build_role_consensus(role_views: List[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
    research_score = _safe_float(metrics.get('research_score'))
    risk_score = _safe_float(metrics.get('risk_score'))
    if research_score >= 72 and risk_score <= 45:
        final_action = '建议重点跟踪'
        confidence = '高'
    elif research_score >= 55 and risk_score <= 60:
        final_action = '建议保留自选'
        confidence = '中'
    else:
        final_action = '建议继续观察'
        confidence = '低'

    summary = ' | '.join([f"{item['name']}：{item['view']}" for item in role_views])
    return {
        'final_action': final_action,
        'confidence': confidence,
        'summary': summary,
    }


def _serialize_snapshot(metrics: Dict[str, Any]) -> str:
    snapshot = {
        'analysis_status': metrics.get('analysis_status', ''),
        'research_updated_at': metrics.get('research_updated_at', ''),
        'last_analysis_date': metrics.get('last_analysis_date', ''),
        'trend_bias': metrics.get('trend_bias', ''),
        'price_position': _safe_float(metrics.get('price_position')),
        'volume_ratio': _safe_float(metrics.get('volume_ratio')),
        'technical_score': _safe_float(metrics.get('technical_score')),
        'sentiment_score': _safe_float(metrics.get('sentiment_score')),
        'capital_score': _safe_float(metrics.get('capital_score')),
        'risk_score': _safe_float(metrics.get('risk_score')),
        'research_score': _safe_float(metrics.get('research_score')),
        'research_summary': metrics.get('research_summary', ''),
        'final_action': metrics.get('final_action', ''),
        'confidence': metrics.get('confidence', ''),
        'debate_summary': metrics.get('debate_summary', ''),
        'role_views': metrics.get('role_views', []),
        'consensus': metrics.get('consensus', {}),
        'debate_panel': metrics.get('debate_panel', {}),
        'engine_mode': metrics.get('engine_mode', DEFAULT_ENGINE),
        'engine_display_name': metrics.get('engine_display_name', ''),
        'engine_status': metrics.get('engine_status', 'ready'),
        'engine_note': metrics.get('engine_note', ''),
        'agent_raw': metrics.get('agent_raw', {}),
        'analyst_traces': metrics.get('analyst_traces', []),
    }
    return json.dumps(snapshot, ensure_ascii=False)


def _deserialize_snapshot(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    text = str(payload or '').strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {'value': data}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {'legacy_text': text}


def _attach_role_outputs(pick: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    role_views = _build_role_views(pick, metrics)
    consensus = _build_role_consensus(role_views, metrics)
    debate_panel = _build_debate_panel(role_views, metrics)
    metrics['role_views'] = role_views
    metrics['consensus'] = consensus
    metrics['debate_panel'] = debate_panel
    metrics['final_action'] = consensus.get('final_action', '')
    metrics['confidence'] = consensus.get('confidence', '')
    metrics['debate_summary'] = consensus.get('summary', '')
    metrics['data_snapshot'] = _serialize_snapshot(metrics)
    metrics['snapshot'] = _deserialize_snapshot(metrics.get('data_snapshot', ''))
    return metrics


def _analyze_pick_with_agent_engine(pick: Dict[str, Any], analysis_date: str = None) -> Dict[str, Any]:
    analysis_date = (analysis_date or datetime.now().strftime('%Y-%m-%d')).strip()
    code = (pick.get('code') or '').strip()
    if not code:
        return {
            'analysis_status': 'failed',
            'research_summary': '缺少股票代码，无法分析',
            'engine_mode': 'agent',
            'engine_display_name': ENGINE_REGISTRY['agent'].display_name,
            'engine_status': 'failed',
            'engine_note': '缺少股票代码',
            'data_snapshot': _serialize_snapshot({
                'analysis_status': 'failed',
                'research_summary': '缺少股票代码，无法分析',
                'engine_mode': 'agent',
                'engine_display_name': ENGINE_REGISTRY['agent'].display_name,
                'engine_status': 'failed',
                'engine_note': '缺少股票代码',
            }),
        }

    base_metrics = _analyze_pick_with_rule_engine(pick, analysis_date=analysis_date)
    try:
        agent_result = _run_tradingagents_analysis(pick, analysis_date)
        metrics = _build_agent_outputs(pick, analysis_date, agent_result, base_metrics)
    except Exception as exc:
        metrics = dict(base_metrics)
        metrics['engine_mode'] = 'agent'
        metrics['engine_display_name'] = ENGINE_REGISTRY['agent'].display_name
        metrics['engine_status'] = 'degraded_rule'
        metrics['engine_note'] = f'TradingAgents-AShare 调用失败，已降级为规则引擎：{exc}'
        metrics['debate_summary'] = f"{metrics.get('debate_summary', '')} | Agent 编排失败后已自动回退规则结果。".strip(' |')
        metrics['data_snapshot'] = _serialize_snapshot(metrics)
        metrics['snapshot'] = _deserialize_snapshot(metrics.get('data_snapshot', ''))
        return metrics

    metrics['data_snapshot'] = _serialize_snapshot(metrics)
    metrics['snapshot'] = _deserialize_snapshot(metrics.get('data_snapshot', ''))
    return metrics


def _analyze_pick_with_rule_engine(pick: Dict[str, Any], analysis_date: str = None) -> Dict[str, Any]:
    analysis_date = (analysis_date or datetime.now().strftime('%Y-%m-%d')).strip()
    code = (pick.get('code') or '').strip()
    if not code:
        return {
            'analysis_status': 'failed',
            'research_summary': '缺少股票代码，无法分析',
            'engine_mode': 'rule',
            'engine_display_name': ENGINE_REGISTRY['rule'].display_name,
            'engine_status': 'failed',
            'engine_note': '缺少股票代码',
        }

    hist_df = _recent_hist(code, analysis_date)
    signal_text = ' '.join([
        str(pick.get('signal') or ''),
        str(pick.get('reason_tag') or ''),
        str(pick.get('note') or ''),
        str(pick.get('prediction_reason') or ''),
    ])

    if hist_df.empty or len(hist_df) < 10:
        sentiment_score = _keyword_score(signal_text)
        research_score = round(sentiment_score * 0.6, 2)
        risk_score = round(100 - sentiment_score, 2)
        fallback = {
            'analysis_status': 'partial',
            'technical_score': 0.0,
            'sentiment_score': round(sentiment_score, 2),
            'capital_score': 0.0,
            'risk_score': round(risk_score, 2),
            'research_score': research_score,
            'research_summary': f'历史行情不足，基于文本信号得到初步评分 {research_score:.1f}',
            'research_updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_analysis_date': analysis_date,
            'price_position': 0.0,
            'volume_ratio': 0.0,
            'trend_bias': 'unknown',
            'engine_mode': 'rule',
            'engine_display_name': ENGINE_REGISTRY['rule'].display_name,
            'engine_status': 'ready',
            'engine_note': '规则引擎已执行，历史行情不足时采用文本信号降级分析。',
        }
        fallback['watch_flag'] = 1 if fallback['research_score'] >= 35 and fallback['risk_score'] <= 70 else int(pick.get('watch_flag') or 0)
        fallback['watch_reason'] = fallback['research_summary'] if fallback['watch_flag'] else ''
        return _attach_role_outputs(pick, fallback)

    latest = hist_df.iloc[-1]
    close = _safe_float(latest.get('close'))
    ma5 = hist_df['close'].tail(5).mean()
    ma10 = hist_df['close'].tail(10).mean()
    ma20 = hist_df['close'].tail(20).mean()
    ma60 = hist_df['close'].mean()
    vol20 = hist_df['volume'].tail(20).mean() or 0
    latest_vol = _safe_float(latest.get('volume'))
    volume_ratio = latest_vol / vol20 if vol20 else 0
    recent_high = hist_df['high'].tail(20).max()
    recent_low = hist_df['low'].tail(20).min()
    amplitude = ((recent_high - recent_low) / recent_low) if recent_low else 0
    price_position = ((close - recent_low) / (recent_high - recent_low) * 100) if recent_high > recent_low else 50
    momentum_5 = ((close - _safe_float(hist_df.iloc[-5].get('close'))) / _safe_float(hist_df.iloc[-5].get('close'))) if len(hist_df) >= 5 and _safe_float(hist_df.iloc[-5].get('close')) else 0

    trend_points = 35
    if close >= ma5:
        trend_points += 12
    if close >= ma10:
        trend_points += 12
    if close >= ma20:
        trend_points += 16
    if close >= ma60:
        trend_points += 10
    if momentum_5 > 0.03:
        trend_points += 10
    elif momentum_5 < -0.03:
        trend_points -= 12
    technical_score = _clip(trend_points)

    capital_points = 40 + min(volume_ratio, 3.0) * 15
    if price_position >= 70:
        capital_points += 8
    if latest_vol < vol20 * 0.8:
        capital_points -= 8
    capital_score = _clip(capital_points)

    sentiment_score = _keyword_score(signal_text)

    risk_points = 35.0
    if price_position >= 92:
        risk_points += 18
    if amplitude >= 0.25:
        risk_points += 15
    if close < ma20:
        risk_points += 12
    if momentum_5 < -0.05:
        risk_points += 12
    if '首板' in signal_text and volume_ratio > 2:
        risk_points += 6
    risk_score = _clip(risk_points)

    research_score = _clip(technical_score * 0.35 + capital_score * 0.25 + sentiment_score * 0.2 + (100 - risk_score) * 0.2)
    trend_bias = 'bullish' if research_score >= 65 else 'neutral' if research_score >= 45 else 'bearish'

    metrics = {
        'analysis_status': 'done',
        'technical_score': round(technical_score, 2),
        'sentiment_score': round(sentiment_score, 2),
        'capital_score': round(capital_score, 2),
        'risk_score': round(risk_score, 2),
        'research_score': round(research_score, 2),
        'research_updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_analysis_date': analysis_date,
        'price_position': round(price_position, 2),
        'volume_ratio': round(volume_ratio, 2),
        'trend_bias': trend_bias,
        'engine_mode': 'rule',
        'engine_display_name': ENGINE_REGISTRY['rule'].display_name,
        'engine_status': 'ready',
        'engine_note': '规则引擎已执行，输出可直接被未来 Agent 引擎替换。',
    }
    metrics['research_summary'] = _build_summary(metrics)
    metrics['watch_flag'] = 1 if metrics['research_score'] >= 60 and metrics['risk_score'] <= 58 else int(pick.get('watch_flag') or 0)
    metrics['watch_reason'] = metrics['research_summary'] if metrics['watch_flag'] else (pick.get('watch_reason') or '')
    return _attach_role_outputs(pick, metrics)


def _normalize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(report)
    snapshot = _deserialize_snapshot(item.get('data_snapshot', ''))
    item['snapshot'] = snapshot
    item['role_views'] = snapshot.get('role_views', []) if isinstance(snapshot, dict) else []
    item['consensus'] = snapshot.get('consensus', {}) if isinstance(snapshot, dict) else {}
    item['debate_summary'] = snapshot.get('debate_summary', '') if isinstance(snapshot, dict) else ''
    item['debate_panel'] = snapshot.get('debate_panel', {}) if isinstance(snapshot, dict) else {}
    item['engine_mode'] = snapshot.get('engine_mode', DEFAULT_ENGINE) if isinstance(snapshot, dict) else DEFAULT_ENGINE
    item['engine_display_name'] = snapshot.get('engine_display_name', '') if isinstance(snapshot, dict) else ''
    item['engine_status'] = snapshot.get('engine_status', 'ready') if isinstance(snapshot, dict) else 'ready'
    item['engine_note'] = snapshot.get('engine_note', '') if isinstance(snapshot, dict) else ''
    item['agent_raw'] = snapshot.get('agent_raw', {}) if isinstance(snapshot, dict) else {}
    item['analyst_traces'] = snapshot.get('analyst_traces', []) if isinstance(snapshot, dict) else []
    return item


def _build_report_archive(report: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = report.get('snapshot', {}) or {}
    role_views = report.get('role_views', []) or snapshot.get('role_views', []) or []
    consensus = report.get('consensus', {}) or snapshot.get('consensus', {}) or {}
    debate_panel = report.get('debate_panel', {}) or snapshot.get('debate_panel', {}) or {}
    return {
        'analysis_date': report.get('analysis_date', ''),
        'summary': report.get('research_summary', ''),
        'action': report.get('action_suggestion', '') or snapshot.get('final_action', ''),
        'confidence': report.get('risk_warning', '') or snapshot.get('confidence', ''),
        'scores': {
            'total': _safe_float(report.get('total_score')),
            'technical': _safe_float(report.get('technical_score')),
            'sentiment': _safe_float(report.get('momentum_score')),
            'risk': _safe_float(report.get('risk_score')),
            'capital': _safe_float(report.get('liquidity_score')),
        },
        'snapshot': snapshot,
        'role_views': role_views,
        'consensus': consensus,
        'debate_panel': debate_panel,
        'engine_mode': report.get('engine_mode', DEFAULT_ENGINE),
        'engine_display_name': report.get('engine_display_name', ''),
        'engine_status': report.get('engine_status', 'ready'),
        'engine_note': report.get('engine_note', ''),
        'agent_raw': report.get('agent_raw', {}) or snapshot.get('agent_raw', {}),
        'analyst_traces': report.get('analyst_traces', []) or snapshot.get('analyst_traces', []),
    }


def analyze_pick_payload(pick: Dict[str, Any], analysis_date: str = None, engine: str = None) -> Dict[str, Any]:
    resolved_engine = get_research_engine(engine)
    metrics = resolved_engine.analyze(pick, analysis_date=analysis_date)
    metrics['engine_mode'] = metrics.get('engine_mode') or resolved_engine.name
    metrics['engine_display_name'] = metrics.get('engine_display_name') or resolved_engine.display_name
    metrics['engine_status'] = metrics.get('engine_status', 'ready')
    metrics['engine_note'] = metrics.get('engine_note', '')
    metrics['snapshot'] = _deserialize_snapshot(metrics.get('data_snapshot', ''))
    return metrics


def analyze_pick_by_id(rid: int, analysis_date: str = None, engine: str = None) -> Dict[str, Any]:
    pick = picks_repo.get_pick_by_id(rid)
    if not pick:
        return {'success': False, 'message': '记录不存在'}
    resolved_name = _resolve_engine_name(engine)
    metrics = analyze_pick_payload(pick, analysis_date=analysis_date, engine=resolved_name)
    picks_repo.update_research_snapshot(rid, metrics)
    refreshed = picks_repo.get_pick_by_id(rid)
    return {'success': True, 'pick': refreshed, 'analysis': metrics, 'engine': resolved_name, 'engines': list_research_engines()}


def analyze_watchlist(limit: int = 30, analysis_date: str = None, engine: str = None) -> Dict[str, Any]:
    rows = picks_repo.list_watch_picks(limit=limit)
    analyzed = []
    resolved_name = _resolve_engine_name(engine)
    for row in rows:
        metrics = analyze_pick_payload(row, analysis_date=analysis_date, engine=resolved_name)
        picks_repo.update_research_snapshot(row['id'], metrics)
        analyzed.append({
            'id': row['id'],
            'code': row.get('code', ''),
            'name': row.get('name', ''),
            'research_score': metrics.get('research_score', 0),
            'risk_score': metrics.get('risk_score', 0),
            'watch_flag': metrics.get('watch_flag', 0),
            'research_summary': metrics.get('research_summary', ''),
            'final_action': metrics.get('final_action', ''),
            'confidence': metrics.get('confidence', ''),
            'engine_mode': metrics.get('engine_mode', resolved_name),
            'engine_status': metrics.get('engine_status', 'ready'),
        })
    return {
        'success': True,
        'count': len(analyzed),
        'analysis_date': analysis_date or datetime.now().strftime('%Y-%m-%d'),
        'items': analyzed,
        'engine': resolved_name,
        'engines': list_research_engines(),
    }


def analyze_recent_picks(limit: int = 20, analysis_date: str = None, engine: str = None) -> Dict[str, Any]:
    rows = picks_repo.list_recent_for_analysis(limit=limit)
    analyzed = []
    resolved_name = _resolve_engine_name(engine)
    for row in rows:
        metrics = analyze_pick_payload(row, analysis_date=analysis_date, engine=resolved_name)
        picks_repo.update_research_snapshot(row['id'], metrics)
        analyzed.append({
            'id': row['id'],
            'code': row.get('code', ''),
            'name': row.get('name', ''),
            'research_score': metrics.get('research_score', 0),
            'final_action': metrics.get('final_action', ''),
            'confidence': metrics.get('confidence', ''),
            'engine_mode': metrics.get('engine_mode', resolved_name),
            'engine_status': metrics.get('engine_status', 'ready'),
        })
    return {
        'success': True,
        'count': len(analyzed),
        'items': analyzed,
        'engine': resolved_name,
        'engines': list_research_engines(),
    }


def build_watchlist_detail(rid: int, engine: str = None) -> Dict[str, Any]:
    pick = picks_repo.get_pick_by_id(rid)
    if not pick:
        return {'success': False, 'message': '记录不存在'}
    resolved_name = _resolve_engine_name(engine)
    reports = [_normalize_report(report) for report in picks_repo.get_research_reports_by_pick(rid, limit=20)]
    latest_analysis = analyze_pick_payload(pick, analysis_date=datetime.now().strftime('%Y-%m-%d'), engine=resolved_name)
    latest_analysis['snapshot'] = _deserialize_snapshot(latest_analysis.get('data_snapshot', ''))
    archives = [_build_report_archive(report) for report in reports]
    return {
        'success': True,
        'pick': pick,
        'latest_analysis': latest_analysis,
        'reports': reports,
        'archives': archives,
        'engine': resolved_name,
        'engines': list_research_engines(),
    }
