import { useCallback, useEffect, useRef } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BellRing,
  BookOpen,
  BookOpenCheck,
  CalendarDays,
  ClipboardList,
  Code2,
  Compass,
  Cpu,
  HelpCircle,
  History,
  Layers,
  Megaphone,
  Palette,
  School,
  ShieldCheck,
  Trash2,
  UserCircle,
  Users,
} from 'lucide-react';
import { knowledgeIntegrationCopy as kb } from '../../config/knowledgeIntegration';
import { useSessionStore } from '../../stores/session.store';
import { useUiStore, type CanvasType } from '../../stores/ui.store';

type DockItem = {
  to: string;
  label: string;
  helper: string;
  canvas: CanvasType;
  Icon: LucideIcon;
};

type DockMenuGroup = {
  items: DockItem[];
};

/** 左侧 Dock 唯一选中项（互斥） */
type DockSelection = 'history' | 'recycle' | string;

const historyDockItem = {
  label: '会话历史',
  helper: '按课程隔离历史轴',
  Icon: History,
} as const;

const studentMenuGroups: DockMenuGroup[] = [
  {
    items: [
      { to: '/learning-path', label: '学习路径', helper: '章节路径与学习行动工作台', canvas: 'path', Icon: Compass },
      { to: '/calendar', label: '学习日历', helper: '按日期安排学习、复盘与资源', canvas: 'calendar', Icon: CalendarDays },
      { to: '/curriculum', label: '课程体系', helper: '计算机与人工智能课程地图', canvas: 'curriculum', Icon: BookOpen },
    ],
  },
  {
    items: [{ to: '/resource-hall', label: '资源大厅', helper: '社区资源网格', canvas: 'hall', Icon: Users }],
  },
  {
    items: [{ to: '/sandbox', label: '代码沙箱', helper: '在线编程实验与 AI 代码辅导', canvas: 'sandbox', Icon: Code2 }],
  },
  {
    items: [
      { to: '/learning-profile', label: '学情画像', helper: '六维星轨与特征文字流', canvas: 'profile', Icon: UserCircle },
      { to: '/announcements', label: '公告中心', helper: '系统通知与历史公告', canvas: 'announcements', Icon: Megaphone },
    ],
  },
  {
    items: [
      { to: '/classes', label: '我的班级', helper: '凭邀请码加入班级', canvas: 'classes', Icon: School },
      { to: '/assignments', label: '课程作业', helper: '作业要求与在线提交', canvas: 'assignments', Icon: ClipboardList },
      { to: '/quizzes', label: '随堂测验', helper: '在线作答与即时判分', canvas: 'quizzes', Icon: HelpCircle },
      { to: '/notifications', label: '消息通知', helper: '助教提醒收件箱', canvas: 'notifications', Icon: BellRing },
    ],
  },
];

const knowledgeBasePath = '/admin/knowledge-base';

const adminMenuGroups: DockMenuGroup[] = [
  {
    items: [{ to: knowledgeBasePath, label: '知识大本营', helper: kb.sidebarKnowledgeHelper, canvas: 'knowledge', Icon: Layers }],
  },
  {
    items: [
      { to: '/admin/model-gateway', label: '网关中心', helper: 'Chat · 知识向量化密钥', canvas: 'gateway', Icon: Cpu },
      { to: '/admin/resource-review', label: '资源审核', helper: '合规审查面板', canvas: 'review', Icon: ShieldCheck },
      { to: '/admin/operations-monitoring', label: '云原生运维舱', helper: '成本 · 回调 · 拒答', canvas: 'monitoring', Icon: Activity },
    ],
  },
  {
    items: [
      { to: '/admin/announcements', label: '公告发布', helper: '顶部条 · 弹窗 · Toast', canvas: 'announcementAdmin', Icon: Megaphone },
      { to: '/admin/interface-settings', label: '界面设置', helper: '登录背景 · 预览调整', canvas: 'appearance', Icon: Palette },
    ],
  },
];

function flattenMenuGroups(groups: DockMenuGroup[]): DockItem[] {
  return groups.flatMap((group) => group.items);
}

function renderDockItemLabel(item: DockItem) {
  return (
    <>
      <span className="float-dock__item-icon" aria-hidden="true">
        <item.Icon size={20} />
      </span>
      <span className="float-dock__item-label">{item.label}</span>
    </>
  );
}

export function Sidebar(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useSessionStore((state) => state.user);
  const currentRole = useUiStore((state) => state.currentRole);
  const isHistoryPanelOpen = useUiStore((state) => state.isHistoryPanelOpen);
  const openCanvas = useUiStore((state) => state.openCanvas);
  const toggleHistoryWorkspace = useUiStore((state) => state.toggleHistoryWorkspace);
  const closeHistoryWorkspace = useUiStore((state) => state.closeHistoryWorkspace);
  const closeCanvas = useUiStore((state) => state.closeCanvas);
  const setCurrentRole = useUiStore((state) => state.setCurrentRole);
  const canAccessAdmin = user?.role === 'admin';
  const menuGroups = currentRole === 'admin' && canAccessAdmin ? adminMenuGroups : studentMenuGroups;
  const items = flattenMenuGroups(menuGroups);
  const historyActive = isHistoryPanelOpen;

  function isRouteActive(path: string) {
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  }

  function isRecyclePanelActive() {
    if (!isRouteActive(knowledgeBasePath)) return false;
    return new URLSearchParams(location.search).get('panel') === 'recycle';
  }

  function resolveDockSelection(): DockSelection | null {
    if (historyActive) return 'history';
    if (isRecyclePanelActive()) return 'recycle';
    const matched = items.find(({ to }) => isRouteActive(to));
    return matched?.to ?? null;
  }

  const dockSelection = resolveDockSelection();

  function collapseToDashboard() {
    navigate('/dashboard');
    closeCanvas();
    closeHistoryWorkspace();
  }

  function isDockRouteSelected(to: string) {
    return dockSelection === to;
  }

  function isSameRouteToggle(to: string) {
    if (!isRouteActive(to)) return false;
    if (to === knowledgeBasePath && isRecyclePanelActive()) return true;
    return true;
  }

  function handleDockItemClick(event: React.MouseEvent<HTMLAnchorElement>, to: string, canvas: CanvasType) {
    setCurrentRole(to.startsWith('/admin') ? 'admin' : 'student');
    closeHistoryWorkspace();

    if (isRecyclePanelActive() && to === knowledgeBasePath) {
      event.preventDefault();
      collapseToDashboard();
      return;
    }

    if (isSameRouteToggle(to)) {
      event.preventDefault();
      collapseToDashboard();
      return;
    }

    openCanvas(canvas);
  }

  function handleRecycleClick() {
    setCurrentRole('admin');
    closeHistoryWorkspace();

    if (isRecyclePanelActive()) {
      collapseToDashboard();
      return;
    }

    const params = isRouteActive(knowledgeBasePath) ? new URLSearchParams(location.search) : new URLSearchParams();
    params.set('panel', 'recycle');
    navigate({ pathname: knowledgeBasePath, search: `?${params.toString()}` });
    openCanvas('knowledge');
  }

  return (
    <div className="sidebar-dock">
      <aside className="left-sidebar float-dock floating-sidebar" aria-label="全局功能控制轴">
        <div className="float-dock__rail" data-role={currentRole}>
          {menuGroups.map((group, groupIndex) => (
            <div key={`dock-group-${groupIndex}`} className="float-dock__group">
              {group.items.map(({ to, label, helper, canvas, Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={`float-dock__item ${isDockRouteSelected(to) ? 'float-dock__item--active' : ''}`}
                  aria-label={label}
                  title={helper}
                  aria-current={isDockRouteSelected(to) ? 'page' : undefined}
                  onClick={(event) => handleDockItemClick(event, to, canvas)}
                >
                  {renderDockItemLabel({ to, label, helper, canvas, Icon })}
                </NavLink>
              ))}
            </div>
          ))}

          {canAccessAdmin && currentRole === 'admin' && (
            <div className="float-dock__group">
              <button
                type="button"
                className={`float-dock__item ${dockSelection === 'recycle' ? 'float-dock__item--active' : ''}`}
                aria-label="回收站"
                title="课程 · 文档 · 还原"
                aria-pressed={dockSelection === 'recycle'}
                onClick={handleRecycleClick}
              >
                <span className="float-dock__item-icon" aria-hidden="true">
                  <Trash2 size={20} />
                </span>
                <span className="float-dock__item-label">回收站</span>
              </button>
            </div>
          )}

          <div className="float-dock__group">
            <button
              type="button"
              className={`float-dock__item ${dockSelection === 'history' ? 'float-dock__item--active' : ''}`}
              aria-label={historyDockItem.label}
              title={currentRole === 'admin' && canAccessAdmin ? '全局或个人上下文' : historyDockItem.helper}
              aria-pressed={dockSelection === 'history'}
              onClick={() => {
                if (isHistoryPanelOpen) {
                  toggleHistoryWorkspace();
                  return;
                }
                navigate('/dashboard');
                closeCanvas();
                toggleHistoryWorkspace();
              }}
            >
              <span className="float-dock__item-icon" aria-hidden="true">
                <historyDockItem.Icon size={20} />
              </span>
              <span className="float-dock__item-label">{historyDockItem.label}</span>
            </button>
          </div>
        </div>

        {canAccessAdmin && (
          <NavLink
            to={currentRole === 'admin' ? '/learning-path' : '/admin/model-gateway'}
            className="float-dock__mode"
            title={currentRole === 'admin' ? '切换到用户模式' : '切换到管理员模式'}
            onClick={() => {
              const nextRole = currentRole === 'admin' ? 'student' : 'admin';
              setCurrentRole(nextRole);
              openCanvas(nextRole === 'admin' ? 'gateway' : 'path');
            }}
          >
            <BookOpenCheck size={18} />
            <span className="float-dock__mode-label">
              {currentRole === 'admin' ? '用户模式' : '管理员模式'}
            </span>
          </NavLink>
        )}
      </aside>
    </div>
  );
}
