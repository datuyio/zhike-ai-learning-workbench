import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Bell,
  CalendarDays,
  ChevronDown,
  GraduationCap,
  LogOut,
  PanelLeft,
  Settings,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import logoUrl from '../../assets/zhike-logo.svg';
import { useGlobalPageHeaderState } from '../../context/GlobalPageHeaderContext';
import { useCourseAiContext } from '../../hooks/useCourseAiContext';
import { useCourseContextStore } from '../../stores/course-context.store';
import { useSessionStore } from '../../stores/session.store';
import { useUiStore, type WorkspaceRole } from '../../stores/ui.store';
import { resolveUserDisplayName } from '../../utils/user-display';
import { CourseSwitcher } from '../shared/CourseSwitcher';

const roleOptions: Array<{ role: WorkspaceRole; label: string; helper: string; Icon: typeof GraduationCap }> = [
  { role: 'student', label: '用户模式', helper: '路径、工坊、画像', Icon: GraduationCap },
  { role: 'admin', label: '管理员模式', helper: '知识、网关、监控', Icon: ShieldCheck },
];

/**
 * 工作台统一顶栏：Notion 风格全宽导航，左侧 Logo + 面包屑，右侧全局操作。
 */
export function GlobalHeader(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const user = useSessionStore((state) => state.user);
  const clearSession = useSessionStore((state) => state.clearSession);
  const setGeneralMode = useCourseContextStore((state) => state.setGeneralMode);
  const currentCourseId = useCourseContextStore((state) => state.currentCourseId);
  const learningScope = useCourseContextStore((state) => state.learningScope);
  const currentRole = useUiStore((state) => state.currentRole);
  const setCurrentRole = useUiStore((state) => state.setCurrentRole);
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const openCanvas = useUiStore((state) => state.openCanvas);
  const closeCanvas = useUiStore((state) => state.closeCanvas);
  const closeHistoryWorkspace = useUiStore((state) => state.closeHistoryWorkspace);
  const { title, primaryAction } = useGlobalPageHeaderState();
  const displayName = resolveUserDisplayName(user?.name);
  const canAccessAdmin = user?.role === 'admin';
  const announcementSummaryQuery = useQuery({
    queryKey: ['announcement-summary'],
    queryFn: () => api.announcementSummary(),
    enabled: Boolean(user),
    staleTime: 30_000,
    retry: 1,
  });
  const unreadAnnouncements = announcementSummaryQuery.data?.unread_count ?? 0;
  const isCourseMode = learningScope === 'course' && Boolean(currentCourseId);
  const isSidebarVisible = !sidebarCollapsed;

  useEffect(() => {
    if (!isAccountMenuOpen) return undefined;

    function closeOnOutsideClick(event: MouseEvent) {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setIsAccountMenuOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsAccountMenuOpen(false);
      }
    }

    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isAccountMenuOpen]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key !== '\\') return;
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return;
      event.preventDefault();
      toggleSidebar();
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleSidebar]);

  function handleRoleChange(role: WorkspaceRole) {
    if (role === 'admin' && !canAccessAdmin) return;
    setCurrentRole(role);
    openCanvas(role === 'admin' ? 'gateway' : 'path');
    navigate(role === 'admin' ? '/admin/model-gateway' : '/learning-path');
  }

  async function handleLogout() {
    if (isLoggingOut) return;

    setIsLoggingOut(true);
    try {
      await api.logout();
    } catch {
      // 即使服务端会话已失效，本地会话清理仍然必须执行。
    } finally {
      queryClient.clear();
      clearSession();
      setGeneralMode();
      setIsAccountMenuOpen(false);
      setIsLoggingOut(false);
      navigate('/login', { replace: true });
    }
  }

  useCourseAiContext(isCourseMode ? currentCourseId : '');

  return (
    <header className="global-header integrated-header">
      <div className="global-header__inner">
        <div className="global-header__leading">
          <button
            type="button"
            className={`global-header__sidebar-toggle${isSidebarVisible ? ' global-header__sidebar-toggle--active' : ''}`}
            aria-label={isSidebarVisible ? '收起侧边栏' : '展开侧边栏'}
            aria-pressed={isSidebarVisible}
            aria-keyshortcuts="Control+\\"
            title={isSidebarVisible ? '收起侧边栏 (Ctrl+\\)' : '展开侧边栏 (Ctrl+\\)'}
            onClick={toggleSidebar}
          >
            <PanelLeft size={18} strokeWidth={2} />
          </button>

          <NavLink
            to="/dashboard"
            className="global-header__logo"
            title="智课未来工作台"
            onClick={() => {
              closeHistoryWorkspace();
              closeCanvas();
              navigate('/dashboard');
            }}
          >
            <img src={logoUrl} alt="智课未来" />
          </NavLink>

          <nav className="global-header__breadcrumb" aria-label="当前页面">
            <span className="global-header__breadcrumb-workspace">智课未来</span>
            <span className="global-header__breadcrumb-sep" aria-hidden="true">
              /
            </span>
            <span className="global-header__breadcrumb-current" aria-current="page">
              {title}
            </span>
          </nav>
        </div>

        <div className="global-header__context">
          <CourseSwitcher variant="header" />
        </div>

        <div className="global-header__actions">
          {primaryAction ? <div className="global-header__primary-action">{primaryAction}</div> : null}

          {canAccessAdmin && (
            <div className="role-switch global-header__role-switch" aria-label="角色切换">
              {roleOptions.map(({ role, label, helper, Icon }) => {
                const active = currentRole === role;
                return (
                  <button
                    key={role}
                    type="button"
                    className={`role-switch__item ${active ? 'role-switch__item--active' : ''}`}
                    title={helper}
                    onClick={() => handleRoleChange(role)}
                  >
                    <Icon size={16} />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          )}

          <button
            className="global-header__icon-button hidden md:grid"
            type="button"
            title="学习日历"
            onClick={() => {
              setCurrentRole('student');
              openCanvas('calendar');
              navigate('/calendar');
            }}
          >
            <CalendarDays size={18} />
          </button>

          <button
            className="global-header__icon-button global-header__icon-button--notice hidden md:grid"
            type="button"
            title={unreadAnnouncements > 0 ? `公告：${unreadAnnouncements} 条未读` : '公告中心'}
            onClick={() => navigate('/announcements')}
          >
            <Bell size={18} />
            {unreadAnnouncements > 0 && (
              <span className="global-header__icon-badge">{unreadAnnouncements > 9 ? '9+' : unreadAnnouncements}</span>
            )}
          </button>

          <button
            className="global-header__icon-button hidden md:grid"
            type="button"
            title="个人设置"
            onClick={() => {
              openCanvas('settings');
              navigate('/personal-settings');
            }}
          >
            <Settings size={18} />
          </button>

          <div ref={accountMenuRef} className="global-header__account">
            <button
              type="button"
              className="global-header__avatar-button"
              aria-haspopup="menu"
              aria-expanded={isAccountMenuOpen}
              aria-label={`账号菜单：${displayName}`}
              onClick={() => setIsAccountMenuOpen((value) => !value)}
            >
              <span className="global-header__avatar">{displayName.slice(0, 1)}</span>
              <ChevronDown className={`global-header__avatar-chevron ${isAccountMenuOpen ? 'global-header__avatar-chevron--open' : ''}`} size={14} />
            </button>

            {isAccountMenuOpen && (
              <div className="global-header__account-menu" role="menu">
                <button
                  type="button"
                  className="global-header__account-menu-item"
                  role="menuitem"
                  onClick={() => {
                    setIsAccountMenuOpen(false);
                    openCanvas('settings');
                    navigate('/personal-settings');
                  }}
                >
                  <UserRound size={16} />
                  账号设置
                </button>
                <button
                  type="button"
                  className="global-header__account-menu-item global-header__account-menu-item--danger"
                  role="menuitem"
                  disabled={isLoggingOut}
                  onClick={handleLogout}
                >
                  <LogOut size={16} />
                  {isLoggingOut ? '正在退出' : '退出登录'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
