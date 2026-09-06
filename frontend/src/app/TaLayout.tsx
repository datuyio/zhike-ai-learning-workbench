import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, FileText, CheckSquare, BarChart3, Users,
  BookOpen, Bell, LogOut, Bot,
} from "lucide-react";
import { useSessionStore } from "../stores/session.store";

const navItems = [
  { to: "/ta/dashboard", label: "工作台", icon: LayoutDashboard },
  { to: "/ta/ai-assistant", label: "AI 助手", icon: Bot },
  { to: "/ta/lesson-prep", label: "智能备课", icon: FileText },
  { to: "/ta/grading", label: "作业批改", icon: CheckSquare },
  { to: "/ta/diagnosis", label: "学情诊断", icon: BarChart3 },
  { to: "/ta/class-management", label: "班级管理", icon: Users },
  { to: "/ta/resource-review", label: "资源审核", icon: BookOpen },
  { to: "/ta/announcements", label: "公告通知", icon: Bell },
];

/**
 * 助教端工作台布局：左侧导航 + 顶部栏 + 主内容区。
 */
export function TaLayout(): JSX.Element {
  const navigate = useNavigate();
  const user = useSessionStore((state) => state.user);
  const clearSession = useSessionStore((state) => state.clearSession);

  function handleLogout(): void {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <div className="ta-shell flex h-dvh bg-zinc-50">
      {/* 左侧窄导航 */}
      <aside className="ta-shell__sidebar flex w-56 flex-col border-r border-zinc-200 bg-white">
        {/* Logo */}
        <div className="ta-shell__brand flex h-14 items-center gap-2 border-b border-zinc-100 px-4">
          <div className="ta-shell__brand-mark flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 text-xs font-bold text-white">
            T
          </div>
          <span className="ta-shell__brand-title text-sm font-semibold text-zinc-800">助教工作台</span>
        </div>

        {/* 导航菜单 */}
        <nav className="ta-shell__nav flex-1 space-y-1 px-2 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `ta-shell__nav-link flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-zinc-900 text-white"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                }`
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* 底部回到学生端 */}
        <div className="ta-shell__footer border-t border-zinc-100 p-3">
          <NavLink
            to="/dashboard"
            className="ta-shell__back-link flex items-center gap-2 rounded-md px-3 py-2 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700"
          >
            ← 返回学习端
          </NavLink>
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="ta-shell__main flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 */}
        <header className="ta-shell__topbar flex h-14 items-center justify-between border-b border-zinc-200 bg-white px-6">
          <h1 className="ta-shell__topbar-title text-sm font-medium text-zinc-500">智课 · 助教端</h1>
          <div className="ta-shell__account flex items-center gap-3 text-xs text-zinc-400">
            <span className="ta-shell__user-name">{user?.name ?? '助教'}</span>
            <button type="button" className="ta-shell__logout inline-flex items-center gap-1 rounded-md px-2 py-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700" onClick={handleLogout}>
              <LogOut size={13} /> 退出登录
            </button>
          </div>
        </header>

        {/* 页面内容 */}
        <div className="ta-shell__content flex-1 overflow-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
