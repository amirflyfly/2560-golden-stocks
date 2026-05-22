import { DataTable } from './DataTable';
import { StatusBadge } from './StatusBadge';

const STATUS_LABELS = {
  passed: '满足上线前置条件',
  warning: '可内部试运行，不建议正式上线',
  blocked: '不可上线',
  unknown: '待补充证据，不可正式上线',
};

const GATE_LABELS = {
  readiness: 'Readiness',
  repository_backends: 'Repository Backend',
  live_broker_safe: 'Live Broker 安全',
  production_evidence: 'Production Evidence',
  deploy_preflight: 'Deploy Preflight',
  repo_hygiene: 'Repo Hygiene',
  legacy_policy_doc: 'Legacy Policy',
};

function gateTone(gate = {}) {
  if (gate.ok === false || gate.status === 'blocked') return 'danger';
  if (gate.status === 'warning' || gate.status === 'unknown') return 'warning';
  return 'success';
}

function statusTone(status) {
  if (status === 'passed') return 'success';
  if (status === 'blocked') return 'danger';
  return 'warning';
}

function gateItems(launchCheck = {}) {
  return Object.entries(launchCheck.gates || {}).map(([name, gate]) => ({ name, ...(gate || {}) }));
}

function safeEvidencePath(value) {
  const text = String(value || '');
  if (!text) return '-';
  return text.replace(/(password|token|secret|key)=([^&\s]+)/gi, '$1=***');
}

export function LaunchGatePanel({ launchCheck, error = '', onCopy, className = '' }) {
  if (!launchCheck) {
    return <div className={`empty ${className}`.trim()}>{error || '上线检查暂不可用。'}</div>;
  }

  const status = launchCheck.status || (launchCheck.ok ? 'passed' : 'blocked');
  const items = gateItems(launchCheck);
  const failedCount = launchCheck.counts?.failed ?? items.filter((item) => item.ok === false).length;

  return (
    <section className={`launch-gate-panel ${className}`.trim()} data-testid="launch-gate-panel">
      <div className="launch-gate-summary">
        <div>
          <p className="eyebrow">Launch Gate</p>
          <h2>{STATUS_LABELS[status] || status}</h2>
          <p className="muted">{launchCheck.summary || '上线门禁检查结果'}</p>
          {launchCheck.next_action ? <p className="muted"><strong>下一步：</strong>{launchCheck.next_action}</p> : null}
        </div>
        <div className="launch-gate-status-box">
          <StatusBadge tone={statusTone(status)}>{STATUS_LABELS[status] || status}</StatusBadge>
          <strong>{failedCount}</strong>
          <span>失败门禁</span>
        </div>
      </div>
      <DataTable
        className="compact-table launch-gate-table"
        columns={[
          { label: '门禁', render: (item) => <strong>{GATE_LABELS[item.name] || item.name}</strong> },
          { label: '状态', render: (item) => <StatusBadge tone={gateTone(item)}>{item.ok === false ? '失败' : '通过'}</StatusBadge> },
          { label: '摘要', render: (item) => item.summary || '-' },
          { label: '计数', render: (item) => `${item.counts?.failed ?? 0}/${item.counts?.total ?? item.checks?.length ?? 0}` },
          { label: '证据', render: (item) => <span className="small-text">{safeEvidencePath(item.evidence_path)}</span> },
          { label: '下一步', render: (item) => <span className="small-text">{item.next_action || '保持观察并按 runbook 复核。'}</span> },
        ]}
        rows={items}
        getKey={(item) => item.name}
        emptyText="暂无上线门禁明细。"
      />
      <div className="row-actions section-gap">
        <button type="button" className="btn-secondary" onClick={() => onCopy?.(launchCheck)}>复制上线验收摘要</button>
      </div>
    </section>
  );
}
