import type { PathNodeStatus } from '../types';

export type DashboardIconKey =
  | 'ask'
  | 'assessment'
  | 'lab'
  | 'lesson'
  | 'profile'
  | 'route'
  | 'sparkles'
  | 'trophy';

export type DashboardStepKind = 'lesson' | 'quiz' | 'lab';

export const dashboardExperienceConfig = {
  coldStartThresholdPercent: 5,
  dailyPlanStepCount: 3,
  estimatedMinutes: 20,
  routes: {
    aiRoom: '/ai-room',
    assessment: '/assessment',
    learningPath: '/learning-path',
    learningProfile: '/learning-profile',
  },
  copy: {
    pageBadge: '今日学习驾驶舱',
    pageTitle: '今天从这一关开始',
    pageSubtitle: 'AI 已结合课程知识、学习画像和资源状态，整理出最值得推进的一步。',
    courseFocusPrefix: '当前焦点：',
    selectedCourseTitle: '请选择一门课程',
    selectedCourseDescription: '选择后，AI 会把今天最该做的讲义、题单和实验排成一条清晰的学习流。',
    courseFocusFallback: '等待路径初始化',
    currentKnowledgeFallback: '当前知识点',
    defaultLessonTitle: '今日第一节',
    firstPathAction: '生成我的第一条学习路径',
    completedAction: '复盘今日成果',
    continueActionPrefix: '继续今日学习：',
    planReadyPrefix: 'AI 已编排今日',
    planReadySuffix: '步',
    heroFallbackTitle: '准备开始学习',
    heroDescription:
      'AI 已为你准备好今天最适合的 {stepCount} 个轻量任务，预计耗时 {minutes} 分钟。先完成当前关卡，题单与实验会按表现继续校准。',
    assistantTitle: 'AI 伴学助手',
    assistantDescription: '我会跟踪资料检索、资源生成和难度变化，把复杂流程压成清晰行动。',
    guideTitle: '今日任务流',
    guideDescription: '讲义、题单、实验排成同一条线，当前步骤完成后再解锁下一步。',
    fullPathAction: '查看完整路径',
    emptyPath: '暂无路径节点，请先生成学习路径。',
    nodePrefix: '节点',
    activeStepLabel: '当前正在进行中',
    lockedStepLabel: '待解锁',
    enterAction: '进入',
    previewAction: '预览',
    growthTitle: '成长见证舱',
    progressTitle: '学习状态轻快照',
    growthDescription: '完成前几关后，这里会点亮你的专属学情树。',
    progressDescription: '只展示对下一步有帮助的掌握度、风险和进展。',
    journeyTitle: '新的学习旅程已准备好',
    journeyDescription: '先不展示雷达和宏观数字。等你完成前几步，画像报告会自然长出来。',
    resourceKindFallback: '资源',
    countUnit: '个',
  },
  statusMeta: {
    mastered: { label: '已通关', badge: 'bg-emerald-50 text-emerald-700', tone: 'done' },
    learning: { label: '当前进行中', badge: 'bg-blue-50 text-blue-700', tone: 'current' },
    review: { label: '需要复盘', badge: 'bg-amber-50 text-amber-700', tone: 'current' },
    not_started: { label: '待解锁', badge: 'bg-slate-100 text-slate-500', tone: 'locked' },
    needs_remedial: { label: 'AI 已降阶', badge: 'bg-rose-50 text-rose-700', tone: 'current' },
  } satisfies Record<PathNodeStatus, { label: string; badge: string; tone: 'done' | 'current' | 'locked' }>,
  metricCards: [
    { key: 'pathCompletion', label: '路径进度', iconKey: 'route' },
    { key: 'completedCount', label: '已通关', iconKey: 'trophy' },
    { key: 'focusCount', label: '待关注', iconKey: 'sparkles' },
  ],
  focusStatuses: ['learning', 'review', 'needs_remedial'] satisfies PathNodeStatus[],
  currentNodePriority: ['learning', 'review', 'needs_remedial', 'not_started'] satisfies PathNodeStatus[],
  resourceKinds: [
    { label: '题单', keywords: ['quiz', 'question', '题', '测'] },
    { label: '实验', keywords: ['code', 'lab', '实验'] },
    { label: '精讲', keywords: ['video', 'lecture', '讲义', '精讲'] },
  ],
  guideSteps: [
    {
      key: 'lesson',
      iconKey: 'lesson',
      status: 'current',
      nodeSource: 'current',
      resourceKeywords: ['lecture', 'video', '讲义', '精讲'],
      fallbackSuffix: '精讲',
      helperFallback: '先用一份轻量讲义把概念走通，不要求一次吃透。',
      route: 'aiRoom',
    },
    {
      key: 'quiz',
      iconKey: 'assessment',
      status: 'locked',
      nodeSource: 'current',
      resourceKeywords: ['quiz', 'question', '题', '测评'],
      fallbackSuffix: 'AI 智能题单',
      helperFallback: '做 5 道题确认关键概念，系统会自动记录错因。',
      route: 'assessment',
    },
    {
      key: 'lab',
      iconKey: 'lab',
      status: 'locked',
      nodeSource: 'nextOrCurrent',
      resourceKeywords: ['code', 'lab', '实验'],
      fallbackSuffix: '代码微实验',
      helperFallback: '把刚学的知识放进一段可运行的小实验里验证。',
      route: 'aiRoom',
    },
  ] satisfies Array<{
    key: DashboardStepKind;
    iconKey: DashboardIconKey;
    status: 'current' | 'locked';
    nodeSource: 'current' | 'nextOrCurrent';
    resourceKeywords: string[];
    fallbackSuffix: string;
    helperFallback: string;
    route: 'aiRoom' | 'assessment';
  }>,
  coach: {
    riskKeys: ['risk', '风险'],
    coldStartLines: [
      '我已经把今天的内容压成 {stepCount} 个轻量任务，先从当前关卡开始就好。',
      '后面的题单和实验会按你的表现自动解锁，不需要先研究整张路径图。',
      '完成当前关卡后，我会把下一关难度重新校准。',
    ],
    activeLines: {
      focus: '{title} 是今天的主线，我会先带你过最小可完成任务。',
      risk: '画像提示：{risk}，所以题单会先从低压练习开始。',
      normal: '画像已接入，我会根据最近表现微调任务顺序。',
      action: '你只需要点蓝色按钮，资料、题目和实验我会在流程里依次递上来。',
    },
  },
  secondaryLinks: [
    { label: 'AI 提问', to: '/ai-room', iconKey: 'ask' },
    { label: '练习评估', to: '/assessment', iconKey: 'assessment' },
    { label: '画像报告', to: '/learning-profile', iconKey: 'profile' },
  ],
  journeyMilestones: ['讲义', '题单', '实验'],
} as const;

export function formatDashboardCopy(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}
