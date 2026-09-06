import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  Brain,
  CheckCircle2,
  Eye,
  EyeOff,
  GraduationCap,
  KeyRound,
  Loader2,
  LockKeyhole,
  Mail,
  Network,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import { useAppearance } from '../../hooks/useAppearance';
import { buildWorkspaceAppearanceStyle, buildWorkspaceBackgroundLayerStyle } from '../../config/appearance';
import { useSessionStore } from '../../stores/session.store';
import logoUrl from '../../assets/zhike-logo.svg';

type AuthMode = 'login' | 'register';

type PasswordRequirement = {
  label: string;
  passed: boolean;
};

const DEFAULT_DEV_LOGIN_EMAIL = import.meta.env.VITE_DEV_LOGIN_EMAIL ?? 'admin@example.edu.cn';
const productStats = [
  { label: '全栈私有化', value: '数据不出校' },
  { label: '可信问答', value: '有据可循' },
  { label: '学教管闭环', value: '持续进化' },
] as const;

const capabilityCards = [
  { title: '本地 AI 底座', text: '本地微调模型、Embedding、向量库与混合检索协同运行，适配校园数据边界。', Icon: BookOpenCheck },
  { title: '低幻觉问答', text: '引用核验、低置信拒答与结构化校验，把回答建立在课程证据上。', Icon: Network },
  { title: '闭环式成长', text: '画像、路径、资源生成和助教诊断联动，让学习与教学持续校准。', Icon: Brain },
] as const;

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function buildPasswordRequirements(password: string): PasswordRequirement[] {
  return [
    { label: '至少 8 位字符', passed: password.length >= 8 },
    { label: '包含字母', passed: /[A-Za-z]/.test(password) },
    { label: '包含数字或符号', passed: /[\d\W_]/.test(password) },
  ];
}

function getPasswordStrength(password: string): number {
  const requirements = buildPasswordRequirements(password);
  return requirements.filter((item) => item.passed).length;
}

function getTargetLabel(pathname: string): string {
  if (pathname === '/dashboard') return 'AI 学习空间';
  if (pathname === '/ta') return '助教工作台';
  if (pathname.startsWith('/admin')) return '管理工作台';
  if (pathname.startsWith('/learning-path')) return '学习路径';
  return '刚才访问的页面';
}

/**
 * 按账号角色决定登录后的落点：
 * 教师（ta）进入助教工作台，其余角色沿用原先要访问的页面。
 */
function resolveAuthTarget(role: string | undefined, fallback: string): string {
  if (role === 'ta') return '/ta';
  return fallback;
}

function preserveDataModeParam(target: string, search: string): string {
  const params = new URLSearchParams(search);
  const mock = params.get('mock');
  if (mock !== '1' && mock !== '0' || /[?&]mock=/.test(target)) return target;
  const hashIndex = target.indexOf('#');
  const base = hashIndex >= 0 ? target.slice(0, hashIndex) : target;
  const hash = hashIndex >= 0 ? target.slice(hashIndex) : '';
  return `${base}${base.includes('?') ? '&' : '?'}mock=${mock}${hash}`;
}

function AuthDynamicScene(): JSX.Element {
  return (
    <div className="auth-page__dynamic-layer" aria-hidden="true">
      <div className="auth-page__grid-flow" />
      <div className="auth-page__learning-hub">
        <div className="auth-page__orbit auth-page__orbit--outer" />
        <div className="auth-page__orbit auth-page__orbit--middle" />
        <div className="auth-page__orbit auth-page__orbit--inner" />
        <div className="auth-page__hub-core">
          <span>AI</span>
          <strong>可信学伴</strong>
        </div>
        <span className="auth-page__hub-node auth-page__hub-node--course">课程库</span>
        <span className="auth-page__hub-node auth-page__hub-node--rag">RAG</span>
        <span className="auth-page__hub-node auth-page__hub-node--profile">画像</span>
        <span className="auth-page__hub-node auth-page__hub-node--agent">Agent</span>
      </div>
      <div className="auth-page__data-panel auth-page__data-panel--top">
        <span>本地模型</span>
        <strong>QLoRA</strong>
        <i />
      </div>
      <div className="auth-page__data-panel auth-page__data-panel--middle">
        <span>引用核验</span>
        <strong>低幻觉问答</strong>
        <i />
      </div>
      <div className="auth-page__data-panel auth-page__data-panel--bottom">
        <span>学习路径</span>
        <strong>实时校准</strong>
        <i />
      </div>
      <div className="auth-page__signal-lines">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

/** 渲染产品介绍与账号登录注册联动页面。 */
export function AuthPage({ mode }: { mode: AuthMode }): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const token = useSessionStore((state) => state.token);
  const sessionUser = useSessionStore((state) => state.user);
  const setSession = useSessionStore((state) => state.setSession);
  const demoCredentials = api.demoAuthSession();
  const isRegister = mode === 'register';
  const [name, setName] = useState(demoCredentials?.user.name ?? '');
  // 真实场景下登录与注册均不预填邮箱，避免误导用户
  const [email, setEmail] = useState(demoCredentials?.email ?? '');
  const [password, setPassword] = useState(demoCredentials?.password ?? '');
  const [confirmPassword, setConfirmPassword] = useState(demoCredentials?.password ?? '');
  const [role, setRole] = useState<'student' | 'ta'>('student');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard';
  const postAuthTarget = preserveDataModeParam(from, location.search);
  const loginPath = preserveDataModeParam('/login', location.search);
  const registerPath = preserveDataModeParam('/register', location.search);
  const title = isRegister ? '创建学习账号' : '登录智课未来';
  const subtitle = isRegister
    ? '选择学生或教师身份，注册后进入对应角色的学习与教学工作台。'
    : `登录后继续进入${getTargetLabel(from)}。`;
  const passwordRequirements = useMemo(() => buildPasswordRequirements(password), [password]);
  const passwordStrength = getPasswordStrength(password);
  const passwordStrengthLabel = ['待完善', '基础', '良好', '稳健'][passwordStrength] ?? '待完善';
  const canUseDemo = Boolean(demoCredentials);
  // 用户级外观主题优先于管理员 login_background 配置：
  // 若用户在个人设置启用了自定义主题，登录页也跟随。
  // 用户主题激活时：main 自身不再注入背景样式，由独立 fixed 背景层承载，
  // 避免背景样式干扰 auth-page 内部 absolute/flex 定位。
  const appearance = useAppearance();
  const userThemeActive = appearance.bgMode !== 'default';
  const appearanceStyle = useMemo(
    () => buildWorkspaceAppearanceStyle(appearance),
    [appearance],
  );
  const backgroundLayerStyle = useMemo(
    () => buildWorkspaceBackgroundLayerStyle(appearance),
    [appearance],
  );
  const mergedBackgroundStyle = userThemeActive ? appearanceStyle : undefined;

  useEffect(() => {
    setError('');
  }, [mode]);

  if (token) {
    return <Navigate to={resolveAuthTarget(sessionUser?.role, postAuthTarget)} replace />;
  }

  function validateForm(trimmedEmail: string): boolean {
    if (!trimmedEmail) {
      setError('请输入邮箱。');
      return false;
    }
    if (!isValidEmail(trimmedEmail)) {
      setError('请输入有效的邮箱地址。');
      return false;
    }
    if (!isRegister) return true;
    if (!name.trim()) {
      setError('请输入姓名。');
      return false;
    }
    if (password.length < 8) {
      setError('请使用至少 8 位密码。');
      return false;
    }
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致。');
      return false;
    }
    return true;
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError('');
    const trimmedEmail = email.trim().toLowerCase();
    if (!validateForm(trimmedEmail)) return;

    setSubmitting(true);
    try {
      const response = isRegister
        ? await api.register({ name: name.trim(), email: trimmedEmail, password, role })
        : await api.login({ email: trimmedEmail, password });
      setSession(response.access_token, response.user);
      navigate(resolveAuthTarget(response.user.role, postAuthTarget), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '认证失败，请稍后重试。');
    } finally {
      setSubmitting(false);
    }
  }

  function useDemoSession(): void {
    const demo = api.demoAuthSession();
    if (!demo) return;
    setSession(demo.token, demo.user);
    navigate(resolveAuthTarget(demo.user.role, postAuthTarget), { replace: true });
  }

  function fillDemoCredentials(): void {
    setEmail(demoCredentials?.email ?? DEFAULT_DEV_LOGIN_EMAIL);
    setPassword(demoCredentials?.password ?? '');
    setConfirmPassword(demoCredentials?.password ?? '');
  }

  return (
    <main
      className={`auth-page relative min-h-dvh overflow-hidden ${userThemeActive ? 'auth-page--user-themed' : 'bg-white'} text-neutral-950`}
      style={mergedBackgroundStyle}
      data-theme={userThemeActive ? appearance.theme : undefined}
      data-bg-mode={userThemeActive ? appearance.bgMode : undefined}
    >
      {userThemeActive && (
        <div className="ai-workspace-background-layer" aria-hidden="true" style={backgroundLayerStyle} />
      )}
      <AuthDynamicScene />

      <div className="auth-page__content relative z-10 mx-auto flex min-h-dvh w-full max-w-7xl flex-col px-6 py-6 sm:px-8">
        <header className="auth-page__nav animate-fade-rise">
          <Link to={loginPath} className="auth-page__brand">
            <img src={logoUrl} alt="智课未来" className="h-10 w-10" />
            <span className="min-w-0">
              <span className="auth-page__brand-name auth-display block text-black">智课未来</span>
              <span className="block text-xs font-semibold text-neutral-500">可信 AI 学伴平台</span>
            </span>
          </Link>
          <div className="hidden items-center gap-2 sm:flex">
            <Link
              to={loginPath}
              state={{ from }}
              className={`auth-page__nav-link ${!isRegister ? 'is-active' : ''}`}
            >
              登录
            </Link>
            <Link
              to={registerPath}
              state={{ from }}
              className={`auth-page__nav-link ${isRegister ? 'is-active' : ''}`}
            >
              创建账号
            </Link>
          </div>
        </header>

        <section className="auth-page__layout">
          <div className="auth-page__hero">
            <div className="auth-page__eyebrow animate-fade-rise">
              <Sparkles size={16} />
              私有化 · 可信问答 · 学练评闭环
            </div>
            <h1 className="auth-page__headline auth-display animate-fade-rise">
              <span>私有化 AI 学伴，</span>
              <em>懂课程，会进化。</em>
            </h1>
            <p className="auth-page__description animate-fade-rise-delay">
              以本地 AI、混合检索、多智能体编排和学情画像为底座，把问答、路径、资源生成与教学诊断串成可信闭环。
            </p>

            <div className="auth-page__stats animate-fade-rise-delay">
              {productStats.map((item) => (
                <div key={item.label} className="auth-page__stat-card">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>

            <div id="capabilities" className="auth-page__capabilities animate-fade-rise-delay-2">
              {capabilityCards.map(({ title: cardTitle, text, Icon }) => (
                <article key={cardTitle} className="auth-page__capability-card">
                  <div>
                    <Icon size={18} />
                  </div>
                  <h2>{cardTitle}</h2>
                  <p>{text}</p>
                </article>
              ))}
            </div>
          </div>

          <section className="auth-page__panel" aria-label="账号认证">
            <form
              id="auth-form"
              onSubmit={(event) => void submit(event)}
              className="auth-page__form animate-fade-rise-delay-2"
              noValidate
            >
              <div className="auth-page__mode-tabs" aria-label="登录注册切换">
                <Link
                  to={loginPath}
                  state={{ from }}
                  className={`auth-page__mode-tab ${!isRegister ? 'is-active' : ''}`}
                >
                  <KeyRound size={16} />
                  登录
                </Link>
                <Link
                  to={registerPath}
                  state={{ from }}
                  className={`auth-page__mode-tab ${isRegister ? 'is-active' : ''}`}
                >
                  <UserRound size={16} />
                  注册
                </Link>
              </div>

              <div>
                <p className="auth-page__form-kicker">账号入口</p>
                <h2 className="auth-page__form-title auth-display mt-2 text-black">{title}</h2>
                <p className="mt-3 text-sm leading-6 text-neutral-500">{subtitle}</p>
              </div>

              <div className="mt-6 space-y-4">
                {isRegister && (
                  <>
                    <label className="block" htmlFor="auth-name">
                      <span className="auth-page__label">姓名</span>
                      <span className="relative block">
                        <UserRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                        <input
                          id="auth-name"
                          className="input h-12 w-full rounded-lg pl-12"
                          value={name}
                          autoComplete="name"
                          onChange={(event) => setName(event.target.value)}
                          placeholder="请输入真实姓名"
                        />
                      </span>
                    </label>

                    <div>
                      <span className="auth-page__label">注册身份</span>
                      <div className="mt-2 grid grid-cols-2 gap-2" role="radiogroup" aria-label="注册身份">
                        <button
                          type="button"
                          role="radio"
                          aria-checked={role === 'student'}
                          className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-semibold transition-colors ${role === 'student' ? 'border-black bg-black text-white' : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-400'}`}
                          onClick={() => setRole('student')}
                        >
                          <GraduationCap size={16} /> 学生
                        </button>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={role === 'ta'}
                          className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-semibold transition-colors ${role === 'ta' ? 'border-black bg-black text-white' : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-400'}`}
                          onClick={() => setRole('ta')}
                        >
                          <Users size={16} /> 教师
                        </button>
                      </div>
                      <p className="mt-1.5 text-xs leading-5 text-neutral-400">
                        {role === 'ta' ? '教师注册后可创建班级、发布作业测验并管理学生。' : '学生注册后可通过班级邀请码加入老师创建的班级。'}
                      </p>
                    </div>
                  </>
                )}

                <label className="block" htmlFor="auth-email">
                  <span className="auth-page__label">邮箱</span>
                  <span className="relative block">
                    <Mail className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                    <input
                      id="auth-email"
                      className="input h-12 w-full rounded-lg pl-12"
                      type="email"
                      value={email}
                      autoComplete="email"
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="name@example.edu.cn"
                    />
                  </span>
                </label>

                <label className="block" htmlFor="auth-password">
                  <span className="auth-page__label">密码</span>
                  <span className="relative block">
                    <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                    <input
                      id="auth-password"
                      className="input h-12 w-full rounded-lg pl-12 pr-12"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      autoComplete={isRegister ? 'new-password' : 'current-password'}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder={isRegister ? '至少 8 位，包含字母和数字或符号' : '请输入密码'}
                    />
                    <button
                      type="button"
                      className="auth-page__icon-button absolute right-2 top-1/2 -translate-y-1/2"
                      onClick={() => setShowPassword((value) => !value)}
                      aria-label={showPassword ? '隐藏密码' : '显示密码'}
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </span>
                </label>

                {isRegister && (
                  <>
                    <div className="auth-page__password-panel">
                      <div className="flex items-center justify-between gap-3 text-xs font-bold text-neutral-500">
                        <span>密码强度：{passwordStrengthLabel}</span>
                        <span>{passwordStrength}/3</span>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-1">
                        {[0, 1, 2].map((item) => (
                          <span
                            key={item}
                            className={`h-1.5 rounded-full ${item < passwordStrength ? 'bg-black' : 'bg-neutral-200'}`}
                          />
                        ))}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5">
                        {passwordRequirements.map((item) => (
                          <span key={item.label} className={`inline-flex items-center gap-2 text-xs font-semibold ${item.passed ? 'text-emerald-700' : 'text-neutral-400'}`}>
                            <CheckCircle2 size={14} />
                            {item.label}
                          </span>
                        ))}
                      </div>
                    </div>

                    <label className="block" htmlFor="auth-confirm-password">
                      <span className="auth-page__label">确认密码</span>
                      <input
                        id="auth-confirm-password"
                        className="input h-12 w-full rounded-lg"
                        type={showPassword ? 'text' : 'password'}
                        value={confirmPassword}
                        autoComplete="new-password"
                        onChange={(event) => setConfirmPassword(event.target.value)}
                        placeholder="再次输入密码"
                      />
                    </label>
                  </>
                )}
              </div>

              {error && (
                <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold leading-6 text-red-700" role="alert" aria-live="polite">
                  {error}
                </div>
              )}

              <button className="auth-page__submit" disabled={submitting}>
                {submitting ? <Loader2 className="animate-spin" size={18} /> : <ArrowRight size={18} />}
                {submitting ? '正在提交' : isRegister ? '注册并进入工作台' : '登录工作台'}
              </button>

              {canUseDemo && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    className="auth-page__secondary-button"
                    onClick={fillDemoCredentials}
                  >
                    <BadgeCheck size={16} />
                    体验账号
                  </button>
                  <button
                    type="button"
                    className="auth-page__secondary-button"
                    onClick={useDemoSession}
                  >
                    <ShieldCheck size={16} />
                    快速体验
                  </button>
                </div>
              )}
            </form>
          </section>
        </section>
      </div>
    </main>
  );
}
