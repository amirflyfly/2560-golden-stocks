import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { RiskDisclaimer } from '../components/common';

const defaultForm = {
  username: 'admin',
  password: '',
};

function bootstrapMessage(status) {
  if (!status) return '';
  if (status.has_users) {
    return status.dev_default_admin_available
      ? '本地开发库已初始化管理员，可使用 admin / admin123 登录。生产环境必须使用启动环境变量初始化的管理员账号。'
      : '管理员账号已存在，请使用已初始化的账号登录。';
  }
  if (status.production && !status.admin_init_configured) {
    return '生产环境还没有管理员账号。请设置 ADMIN_INIT_USERNAME 和长度至少 12 位的 ADMIN_INIT_PASSWORD 后重启后端。';
  }
  if (status.production) {
    return '后端已检测到初始化配置，但数据库仍没有管理员账号，请重启服务并检查迁移日志。';
  }
  return '本地开发库尚未发现用户，后端启动时会尝试创建默认管理员 admin / admin123。';
}

export function LoginPage({ onLogin, authError }) {
  const [form, setForm] = useState(defaultForm);
  const [bootstrap, setBootstrap] = useState(null);
  const [bootstrapError, setBootstrapError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState('');

  useEffect(() => {
    let alive = true;
    api.authBootstrap()
      .then((status) => {
        if (!alive) return;
        setBootstrap(status);
        setBootstrapError('');
      })
      .catch((error) => {
        if (!alive) return;
        setBootstrapError(error.message || '管理员初始化状态读取失败');
      });
    return () => {
      alive = false;
    };
  }, []);

  const blocked = useMemo(
    () => Boolean(bootstrap && !bootstrap.has_users && bootstrap.production && !bootstrap.admin_init_configured),
    [bootstrap],
  );
  const statusMessage = bootstrapMessage(bootstrap);

  async function handleSubmit(event) {
    event.preventDefault();
    if (blocked || submitting) return;
    setSubmitting(true);
    setLoginError('');
    try {
      await onLogin(form);
    } catch (error) {
      setLoginError(error.message || '登录失败');
    } finally {
      setSubmitting(false);
    }
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <main className="login-screen">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-copy">
          <p className="login-eyebrow">2560 Strategy</p>
          <h1 id="login-title">后台登录</h1>
          <p>登录后进入策略扫描、K 线研究、回测报表和生产监控工作台。</p>
        </div>

        <RiskDisclaimer variant="full" />

        {statusMessage ? <div className={`alert ${blocked ? 'warning' : 'success'}`}>{statusMessage}</div> : null}
        {bootstrapError ? <div className="alert warning">{bootstrapError}</div> : null}
        {authError && !loginError ? <div className="alert warning">{authError}</div> : null}
        {loginError ? <div className="alert">{loginError}</div> : null}

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="form-field" htmlFor="login-username">
            账号
            <input
              id="login-username"
              autoComplete="username"
              value={form.username}
              disabled={submitting || blocked}
              onChange={(event) => updateField('username', event.target.value)}
            />
          </label>
          <label className="form-field" htmlFor="login-password">
            密码
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={form.password}
              disabled={submitting || blocked}
              onChange={(event) => updateField('password', event.target.value)}
            />
          </label>
          <button className="btn-primary" type="submit" disabled={submitting || blocked || !form.username || !form.password}>
            {submitting ? '登录中' : '登录'}
          </button>
        </form>
      </section>
    </main>
  );
}
