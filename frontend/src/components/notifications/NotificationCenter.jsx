import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';

const POLL_MS = 45000;

function normalizeNotification(item, index = 0) {
  const read = Boolean(item.read || item.read_at || item.status === 'read');
  return {
    ...item,
    id: item.id || item.notification_id || `${item.rule_id || 'notification'}-${item.created_at || index}`,
    title: item.title || item.name || item.rule_name || '提醒通知',
    body: item.body || item.message || item.description || item.summary || '',
    tone: item.tone || item.severity || item.level || 'info',
    scope: item.scope || item.target || item.metadata?.scope || '',
    channel: item.channel || item.channels?.[0] || 'in_app',
    created_at: item.created_at || item.triggered_at || item.updated_at || '',
    read,
  };
}

function normalizePayload(payload) {
  const items = Array.isArray(payload) ? payload : payload?.items || payload?.notifications || [];
  const notifications = items.map(normalizeNotification);
  const unreadCount = payload?.unread_count ?? notifications.filter((item) => !item.read).length;
  return {
    items: notifications,
    unreadCount,
    workerStatus: payload?.worker_status || payload?.status || '',
    lastEvaluatedAt: payload?.last_evaluated_at || payload?.evaluated_at || '',
    nextRunAt: payload?.next_run_at || payload?.next_evaluation_at || '',
  };
}

function formatTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function NotificationCenter({ authz }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState('');
  const [meta, setMeta] = useState({ workerStatus: '', lastEvaluatedAt: '', nextRunAt: '' });

  async function loadNotifications({ quiet = false } = {}) {
    if (authz?.loading) return;
    if (!quiet) setLoading(true);
    try {
      const payload = await api.notifications({ page: 1, page_size: 20 });
      const normalized = normalizePayload(payload);
      setItems(normalized.items);
      setUnreadCount(normalized.unreadCount);
      setMeta({
        workerStatus: normalized.workerStatus,
        lastEvaluatedAt: normalized.lastEvaluatedAt,
        nextRunAt: normalized.nextRunAt,
      });
      setError('');
    } catch (err) {
      setError(`通知接口未就绪或暂不可用：${err.message}`);
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => {
    loadNotifications({ quiet: true });
    const timer = window.setInterval(() => {
      loadNotifications({ quiet: true });
    }, POLL_MS);
    const refresh = () => loadNotifications({ quiet: true });
    window.addEventListener('notifications:refresh', refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('notifications:refresh', refresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authz?.loading, authz?.role, authz?.user_id]);

  async function evaluateNow() {
    setEvaluating(true);
    try {
      const payload = await api.evaluateNotifications({ source: 'notification_center', channel: 'in_app' });
      const normalized = normalizePayload(payload);
      if (normalized.items.length || payload?.unread_count != null) {
        setItems(normalized.items);
        setUnreadCount(normalized.unreadCount);
        setMeta({
          workerStatus: normalized.workerStatus || meta.workerStatus,
          lastEvaluatedAt: normalized.lastEvaluatedAt || new Date().toISOString(),
          nextRunAt: normalized.nextRunAt || meta.nextRunAt,
        });
      } else {
        await loadNotifications({ quiet: true });
      }
      setError('');
    } catch (err) {
      setError(`无法触发立即评估：${err.message}`);
    } finally {
      setEvaluating(false);
    }
  }

  async function markRead(notificationId) {
    const previousItems = items;
    const previousUnread = unreadCount;
    setItems((prev) => prev.map((item) => (item.id === notificationId ? { ...item, read: true, read_at: new Date().toISOString() } : item)));
    setUnreadCount((prev) => Math.max(0, prev - 1));
    try {
      await api.markNotificationRead(notificationId);
    } catch (err) {
      setItems(previousItems);
      setUnreadCount(previousUnread);
      setError(`标记已读失败：${err.message}`);
    }
  }

  const unreadItems = useMemo(() => items.filter((item) => !item.read), [items]);
  const visibleItems = open ? items : unreadItems;

  return (
    <div className="notification-center">
      <button
        type="button"
        className={unreadCount ? 'notification-trigger has-unread' : 'notification-trigger'}
        aria-expanded={open}
        aria-label={`通知中心，${unreadCount} 条未读`}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="notification-bell" aria-hidden="true">!</span>
        <span>通知</span>
        {unreadCount ? <strong>{unreadCount > 99 ? '99+' : unreadCount}</strong> : null}
      </button>

      {open ? (
        <div className="notification-panel" role="dialog" aria-label="通知中心">
          <div className="notification-panel-head">
            <div>
              <h2>通知中心</h2>
              <p>服务端 worker 定时评估提醒规则，站内通知在这里投递。</p>
            </div>
            <button type="button" className="btn-secondary" onClick={() => loadNotifications()} disabled={loading}>
              {loading ? '刷新中...' : '刷新'}
            </button>
          </div>

          <div className="notification-meta">
            <span>未读 {unreadCount}</span>
            <span>worker {meta.workerStatus || 'pending'}</span>
            <span>上次评估 {formatTime(meta.lastEvaluatedAt)}</span>
            <span>下次计划 {formatTime(meta.nextRunAt)}</span>
          </div>

          <div className="notification-actions">
            <button type="button" onClick={evaluateNow} disabled={evaluating}>
              {evaluating ? '评估中...' : '立即评估'}
            </button>
            <span className="muted">接口不可用时，页面仍保留本地回退提醒。</span>
          </div>

          {error ? <div className="alert warning notification-error">{error}</div> : null}

          <div className="notification-list">
            {visibleItems.length ? visibleItems.map((item) => (
              <article className={item.read ? 'notification-item read' : 'notification-item'} key={item.id}>
                <div>
                  <div className="notification-title-row">
                    <strong>{item.title}</strong>
                    <span className={`notification-tone ${item.tone}`}>{item.tone}</span>
                  </div>
                  {item.body ? <p>{item.body}</p> : null}
                  <small>{item.scope || item.channel} · {formatTime(item.created_at)}</small>
                </div>
                {!item.read ? (
                  <button type="button" className="btn-secondary" onClick={() => markRead(item.id)}>已读</button>
                ) : null}
              </article>
            )) : (
              <div className="empty compact-empty">暂无未读通知。</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
