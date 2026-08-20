import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BellRing,
  BookOpen,
  Brain,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Code2,
  Cpu,
  HelpCircle,
  History,
  Images,
  Layers,
  Megaphone,
  MessageSquareText,
  Route,
  School,
  ShieldCheck,
  Users,
  Wand2,
} from 'lucide-react';
import { knowledgeIntegrationCopy as kb } from '../config/knowledgeIntegration';
import type { CanvasType, WorkspaceMode, WorkspaceRole } from '../stores/ui.store';

export type CanvasMeta = {
  title: string;
  subtitle: string;
  signal: string;
  Icon: LucideIcon;
};

export type RouteCanvasRule = {
  test: (pathname: string) => boolean;
  canvas: CanvasType;
  role: WorkspaceRole;
  mode: WorkspaceMode;
};

export const canvasMeta: Record<CanvasType, CanvasMeta> = {
  dashboard: { title: 'AI 对话舱', subtitle: '纯粹对话流与课程上下文底座', signal: 'Standalone', Icon: MessageSquareText },
  chat: { title: 'AI 对话舱', subtitle: '长对话、课程检索与画像抽取', signal: 'Router Live', Icon: MessageSquareText },
  path: { title: '学习路径工作台', subtitle: '章节导航、节点详情与学习行动', signal: 'Path Node', Icon: Route },
  calendar: { title: '学习日历', subtitle: '按日期编排学习节点、复盘、资源与公告', signal: 'Calendar', Icon: CalendarDays },
  workshop: { title: '资源工坊画布', subtitle: '资源生成 Agent、引用核验与版本沉淀', signal: 'Generation', Icon: Wand2 },
  assessment: { title: '练习评估画布', subtitle: '评分、错题归因与路径补救闭环', signal: 'Evaluation', Icon: CheckCircle2 },
  hall: { title: '资源大厅画布', subtitle: '社区资源筛选、复用与审核流转', signal: 'Resource Grid', Icon: Users },
  profile: { title: '学情画像画布', subtitle: '六维星轨、特征文字流与证据链', signal: 'Profile', Icon: Brain },
  announcements: { title: '公告中心', subtitle: '重要提醒、维护通知与历史公告沉淀', signal: 'Notice', Icon: Megaphone },
  settings: { title: '个人设置画布', subtitle: '账号、偏好与课程配置', signal: 'Account', Icon: ShieldCheck },
  builder: { title: '课程建设画布', subtitle: '章节、知识点与课程图谱编排', signal: 'Course Builder', Icon: Route },
  knowledge: { title: '知识大本营画布', subtitle: kb.workspaceKnowledgeSubtitle, signal: 'Knowledge Base', Icon: Layers },
  gateway: { title: '网关中心', subtitle: kb.gatewaySubtitle, signal: 'Gateway', Icon: Cpu },
  review: { title: '资源审核画布', subtitle: '社区资源合规、质量与精选治理', signal: 'Review', Icon: ShieldCheck },
  monitoring: { title: '云原生运维舱', subtitle: '云端资产、链路回调、成本额度与安全拒答', signal: 'Cloud Ops', Icon: Activity },
  announcementAdmin: { title: '公告发布后台', subtitle: '按优先级配置顶部条、弹窗、卡片与 Toast', signal: 'Notice Ops', Icon: Megaphone },
  appearance: { title: '界面设置', subtitle: '登录背景媒体、焦点、滤镜与遮罩预览', signal: 'Appearance', Icon: Images },
  assignments: { title: '课程作业', subtitle: '查看作业要求并在线提交作答', signal: 'Homework', Icon: ClipboardList },
  quizzes: { title: '随堂测验', subtitle: '在线作答客观题与即时判分', signal: 'Quiz', Icon: HelpCircle },
  notifications: { title: '消息通知', subtitle: '助教提醒与作业测验通知收件箱', signal: 'Inbox', Icon: BellRing },
  classes: { title: '我的班级', subtitle: '凭邀请码入班，查看班级信息与师生名单', signal: 'Class', Icon: School },
  history: { title: '会话历史', subtitle: '按课程隔离的历史对话轴', signal: 'History', Icon: History },
  sandbox: { title: '在线编程实验', subtitle: '编写、运行和测试代码，AI 助手解答问题', signal: 'Sandbox', Icon: Code2 },
  curriculum: { title: '课程体系', subtitle: '计算机与人工智能课程地图与开源资料目录', signal: 'Curriculum', Icon: BookOpen },
};

export const routeCanvasRules: RouteCanvasRule[] = [
  { test: (pathname) => pathname.startsWith('/admin/course-builder'), canvas: 'builder', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/knowledge-base') || pathname.startsWith('/admin/chatdoc-config'), canvas: 'knowledge', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/model-gateway'), canvas: 'gateway', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/resource-review'), canvas: 'review', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/operations-monitoring'), canvas: 'monitoring', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/announcements'), canvas: 'announcementAdmin', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/admin/interface-settings'), canvas: 'appearance', role: 'admin', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/learning-path'), canvas: 'path', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/calendar'), canvas: 'calendar', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/resource-workshop'), canvas: 'dashboard', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/assessment'), canvas: 'assessment', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/resource-hall'), canvas: 'hall', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/learning-profile'), canvas: 'profile', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/announcements'), canvas: 'announcements', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/classes'), canvas: 'classes', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/assignments'), canvas: 'assignments', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/quizzes'), canvas: 'quizzes', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/notifications'), canvas: 'notifications', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/personal-settings'), canvas: 'settings', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/sandbox') || pathname.startsWith('/dev/code-sandbox'), canvas: 'sandbox', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/curriculum'), canvas: 'curriculum', role: 'student', mode: 'overlay' },
  { test: (pathname) => pathname.startsWith('/ai-room'), canvas: 'chat', role: 'student', mode: 'standalone' },
  { test: (pathname) => pathname.startsWith('/dashboard'), canvas: 'dashboard', role: 'student', mode: 'standalone' },
];

/** 采用 OverlayPageShell 破窗布局的学生端 overlay 画布类型，详见 docs/layout-spec.md 第 2.8 节。 */
export const brokenWindowCanvasTypes = new Set<CanvasType>([
  'path',
  'calendar',
  'hall',
  'profile',
  'announcements',
  'classes',
  'assignments',
  'quizzes',
  'notifications',
  'curriculum',
]);

/** 判断当前画布是否属于五个破窗 overlay 页面。 */
export function isBrokenWindowCanvas(canvas: CanvasType): boolean {
  return brokenWindowCanvasTypes.has(canvas);
}

const fallbackRouteRule: RouteCanvasRule = {
  test: () => true,
  canvas: 'dashboard',
  role: 'student',
  mode: 'standalone',
};

const studentRoutePrefixes = [
  '/learning-path',
  '/calendar',
  '/assessment',
  '/resource-hall',
  '/learning-profile',
  '/announcements',
  '/classes',
  '/assignments',
  '/quizzes',
  '/notifications',
  '/personal-settings',
  '/sandbox',
  '/curriculum',
] as const;

/** 按当前路径解析工作台画布类型、角色和展示模式。 */
export function resolveCanvas(pathname: string): RouteCanvasRule {
  return routeCanvasRules.find((rule) => rule.test(pathname)) ?? fallbackRouteRule;
}

/** 根据明确的管理或学生路由推导工作台角色；不确定时保持现有角色。 */
export function roleFromWorkspacePath(pathname: string): WorkspaceRole | null {
  if (pathname.startsWith('/admin')) {
    return 'admin';
  }
  if (studentRoutePrefixes.some((prefix) => pathname.startsWith(prefix))) {
    return 'student';
  }
  return null;
}

/** 进入明确角色路由时同步工作台角色，普通对话页不主动覆盖用户上下文。 */
export function syncWorkspaceRoleFromPath(pathname: string, setCurrentRole: (role: WorkspaceRole) => void): void {
  const role = roleFromWorkspacePath(pathname);
  if (role) {
    setCurrentRole(role);
  }
}
