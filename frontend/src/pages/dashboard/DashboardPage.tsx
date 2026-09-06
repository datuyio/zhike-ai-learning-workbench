import { useMemo } from 'react';
import {
  ArrowRight,
  BookOpenCheck,
  Bot,
  Check,
  CircleDot,
  ClipboardCheck,
  Code2,
  Lock,
  MessageCircleQuestion,
  PlayCircle,
  Route,
  Sparkles,
  Trophy,
  UserRound,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { useCourseContextStore } from '../../stores/course-context.store';
import { useCourseQueries } from '../../hooks/useCourseData';
import { dashboardExperienceConfig, formatDashboardCopy, type DashboardIconKey } from '../../config/dashboard';
import type { CourseProfile, PathNode, Resource } from '../../types';

const config = dashboardExperienceConfig;
const copy = config.copy;
const iconMap: Record<DashboardIconKey, typeof Route> = {
  ask: MessageCircleQuestion,
  assessment: ClipboardCheck,
  lab: Code2,
  lesson: BookOpenCheck,
  profile: UserRound,
  route: Route,
  sparkles: Sparkles,
  trophy: Trophy,
};

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function getStatusMeta(status?: string) {
  return config.statusMeta[status as keyof typeof config.statusMeta] ?? config.statusMeta.not_started;
}

function getStudyRoomLink(node?: PathNode | null) {
  if (!node?.concept_id) return config.routes.aiRoom;
  return `${config.routes.aiRoom}?concept=${encodeURIComponent(node.concept_id)}`;
}

function resourceKind(resource?: Resource) {
  const raw = `${resource?.resource_type ?? ''} ${resource?.type ?? ''} ${resource?.title ?? ''}`.toLowerCase();
  const matched = config.resourceKinds.find((kind) => kind.keywords.some((keyword) => raw.includes(keyword)));
  return matched?.label ?? copy.resourceKindFallback;
}

function pickRelatedResources(currentNode: PathNode | undefined, resources: Resource[]) {
  if (!currentNode) return resources;
  const related = resources.filter((resource) => {
    if (resource.path_node_id && resource.path_node_id === currentNode.id) return true;
    if (resource.concept_id && resource.concept_id === currentNode.concept_id) return true;
    return false;
  });
  return related.length ? related : resources;
}

function findResource(resources: Resource[], keywords: readonly string[]) {
  return resources.find((resource) => {
    const haystack = `${resource.resource_type} ${resource.type ?? ''} ${resource.title}`.toLowerCase();
    return keywords.some((keyword) => haystack.includes(keyword));
  });
}

function buildGuideSteps(currentNode: PathNode | undefined, nextNode: PathNode | undefined, resources: Resource[]) {
  const currentTitle = currentNode?.title ?? copy.defaultLessonTitle;
  const relatedResources = pickRelatedResources(currentNode, resources);

  return config.guideSteps.map((step) => {
    const matchedResource = findResource(relatedResources, step.resourceKeywords);
    const titleNode = step.nodeSource === 'nextOrCurrent' ? (nextNode ?? currentNode) : currentNode;
    const title = titleNode?.title ?? currentTitle;
    const suffix = matchedResource ? resourceKind(matchedResource) : step.fallbackSuffix;
    const to = step.route === 'aiRoom' ? getStudyRoomLink(currentNode) : config.routes[step.route];
    return {
      key: step.key,
      title: `${title} · ${suffix}`,
      helper: matchedResource?.summary ?? step.helperFallback,
      status: step.status,
      iconKey: step.iconKey,
      to,
    };
  });
}

function buildCoachLines(profile: CourseProfile | undefined, currentNode: PathNode | undefined, isColdStart: boolean) {
  if (isColdStart) {
    return config.coach.coldStartLines.map((line) => formatDashboardCopy(line, { stepCount: config.dailyPlanStepCount }));
  }

  const risk = profile?.dimensions?.find((item) => config.coach.riskKeys.some((key) => item.key.includes(key) || item.name.includes(key)));
  return [
    formatDashboardCopy(config.coach.activeLines.focus, { title: currentNode?.title ?? copy.currentKnowledgeFallback }),
    risk?.label
      ? formatDashboardCopy(config.coach.activeLines.risk, { risk: risk.label })
      : config.coach.activeLines.normal,
    config.coach.activeLines.action,
  ];
}

function PathStatusIcon({ status }: { status?: string }) {
  const meta = getStatusMeta(status);
  if (meta.tone === 'done') return <Check size={17} strokeWidth={3} />;
  if (meta.tone === 'current') return <CircleDot size={17} className="animate-pulse" strokeWidth={3} />;
  return <Lock size={15} />;
}

function JourneyIllustration() {
  return (
    <div className="dashboard-journey-illustration relative min-h-[220px] overflow-hidden rounded-lg border border-[#E6ECF7] bg-[linear-gradient(135deg,#F8FBFF,#FFFFFF_54%,#FFF8EF)] p-6">
      <div className="dashboard-journey-illustration__ring absolute left-8 top-8 h-24 w-24 rounded-full border border-[#DDE8FF] bg-white/70" />
      <div className="dashboard-journey-illustration__ring dashboard-journey-illustration__ring--warm absolute bottom-8 right-10 h-28 w-28 rounded-full border border-[#FFE3C2] bg-[#FFF4E5]/70" />
      <div className="relative mx-auto flex max-w-sm flex-col items-center text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#111827] text-white shadow-[0_18px_42px_rgba(17,24,39,0.18)]">
          <Route size={28} />
        </div>
        <div className="mt-5 text-lg font-bold text-[#111827]">{copy.journeyTitle}</div>
        <p className="mt-2 text-sm leading-6 text-[#667085]">{copy.journeyDescription}</p>
        <div className="mt-6 grid w-full grid-cols-3 gap-2">
          {config.journeyMilestones.map((item, index) => (
            <div key={item} className="dashboard-milestone rounded-lg border border-white bg-white/80 px-3 py-2 text-xs font-semibold text-[#344054] shadow-[0_12px_32px_rgba(15,23,42,0.06)]">
              <span className="mr-1 text-[#2F6BFF]">{index + 1}</span>
              {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
function GeneralLearningDashboard() {
  const generalCards = [
    { title: '直接提问', description: '解释概念、解答学习疑问，不绑定课程知识库', to: '/dashboard', icon: MessageCircleQuestion },
    { title: '学习计划', description: '制定阶段性学习目标与复习安排', to: '/dashboard', icon: Route },
    { title: '资料生成', description: '在对话中生成讲义、题目或 Markdown 学习资料', to: '/ai-room', icon: Sparkles },
    { title: 'AI 学习舱', description: '进入完整对话界面，管理通用学习会话', to: '/ai-room', icon: Bot },
  ] as const;

  return (
    <div className="dashboard-home dashboard-home--general min-h-[calc(100vh-120px)] rounded-[28px] p-8">
      <div className="mx-auto max-w-4xl">
        <PageHeader
          title="通用学习助手"
          subtitle="不绑定具体课程，可直接提问、规划学习、生成资料。学习画像沉淀在全局 scope；如需课程 RAG、路径与资源任务，请在顶部选择课程。"
        />
        <PageHeaderToolbar className="!justify-start">
          <div className="dashboard-home__chip inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#2F6BFF] shadow-[0_10px_30px_rgba(47,107,255,0.08)]">
            <Sparkles size={14} />
            通用学习模式
          </div>
        </PageHeaderToolbar>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {generalCards.map(({ title, description, to, icon: Icon }) => (
            <Link
              key={title}
              to={to}
              className="dashboard-action-card rounded-2xl border border-[#E6ECF7] bg-white/90 p-5 shadow-[0_16px_44px_rgba(15,23,42,0.06)] transition will-change-transform hover:-translate-y-0.5 hover:border-[#D7E2FF]"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#EEF5FF] text-[#2F6BFF]">
                <Icon size={22} />
              </div>
              <h2 className="mt-4 text-lg font-bold text-[#111827]">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-[#667085]">{description}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DashboardPage(): JSX.Element {
  const { currentCourseId, learningScope } = useCourseContextStore();
  const isCourseMode = learningScope === 'course' && Boolean(currentCourseId);
  const { currentCourseTitle } = useCourseContextStore();
  const { path, mastery, resources, profile } = useCourseQueries();
  const nodes = path.data?.items ?? [];
  const resourceItems = resources.data?.items ?? [];
  const completedCount = nodes.filter((node) => node.status === 'mastered').length;
  const currentNode = config.currentNodePriority
    .map((status) => nodes.find((node) => node.status === status))
    .find(Boolean)
    ?? nodes.find((node) => node.status !== 'mastered')
    ?? nodes[0];
  const nextNode = nodes.find((node) => node.status === 'not_started') ?? nodes.find((node) => node.id !== currentNode?.id);
  const pathCompletion = nodes.length ? Math.round((completedCount / nodes.length) * 100) : mastery.data?.overall ?? 0;
  const overallMastery = clampPercent(mastery.data?.overall ?? pathCompletion);
  const isColdStart = clampPercent(pathCompletion) < config.coldStartThresholdPercent && overallMastery < config.coldStartThresholdPercent;
  const isCourseCompleted = nodes.length > 0 && completedCount === nodes.length;
  const guideSteps = useMemo(() => buildGuideSteps(currentNode, nextNode, resourceItems), [currentNode, nextNode, resourceItems]);
  const coachLines = useMemo(() => buildCoachLines(profile.data, currentNode, isColdStart), [profile.data, currentNode, isColdStart]);
  const focusCount = nodes.filter((node) => config.focusStatuses.some((status) => status === node.status)).length;
  const ctaLabel = isCourseCompleted
    ? copy.completedAction
    : currentNode
      ? `${copy.continueActionPrefix}${currentNode.title}`
      : copy.firstPathAction;
  const ctaTarget = currentNode ? getStudyRoomLink(currentNode) : config.routes.learningPath;
  const metricValues = {
    pathCompletion: `${clampPercent(pathCompletion)}%`,
    completedCount: `${completedCount}/${nodes.length || 0}`,
    focusCount: `${focusCount} ${copy.countUnit}`,
  };

  if (!isCourseMode) {
    return <GeneralLearningDashboard />;
  }

  return (
    <div className="dashboard-home dashboard-home--course relative mx-auto max-w-[1480px] space-y-5 rounded-[28px] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.12),_transparent_32%),linear-gradient(180deg,_rgba(255,255,255,0.96),_rgba(247,250,255,0.96))] p-5 shadow-[0_24px_72px_rgba(15,23,42,0.06)] md:p-7">
      <PageHeader title={copy.pageTitle} subtitle={copy.pageSubtitle} />
      <PageHeaderToolbar>
        <div className="dashboard-home__chip inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#2F6BFF] shadow-[0_10px_30px_rgba(47,107,255,0.08)]">
          <Sparkles size={14} />
          {copy.pageBadge}
        </div>
        <div className="dashboard-home__meta rounded-lg border border-slate-200/80 bg-white/85 px-4 py-3 text-sm text-[#667085] shadow-[0_12px_32px_rgba(15,23,42,0.04)]">
          <span className="font-semibold text-[#111827]">{currentCourseTitle}</span>
          <span className="mx-2 text-[#D0D5DD]">/</span>
          {copy.courseFocusPrefix}{currentNode?.title ?? copy.courseFocusFallback}
        </div>
      </PageHeaderToolbar>

      <section className="dashboard-home__hero-card overflow-hidden rounded-[22px] border border-[#D7E2FF] bg-[linear-gradient(135deg,#FFFFFF,#F5F9FF_54%,#EEF5FF)] shadow-[0_28px_90px_rgba(47,107,255,0.12)]">
        {path.isError ? (
          <div className="p-8">
            <ErrorState />
          </div>
        ) : (
          <div
            className="grid gap-5 p-5 md:p-6"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))' }}
          >
            <div className="flex min-w-0 flex-col justify-between gap-6">
              <div>
                <div className="dashboard-home__ready-pill inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                  <Zap size={14} />
                  {copy.planReadyPrefix} {config.dailyPlanStepCount} {copy.planReadySuffix}
                </div>
                <div
                  className="mt-5 grid gap-4 lg:items-end"
                  style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))' }}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#2F6BFF]">{currentCourseTitle}</p>
                    <h2 className="mt-2 text-[clamp(28px,4vw,46px)] font-black leading-tight text-[#111827]">{currentNode?.title ?? copy.heroFallbackTitle}</h2>
                    <p className="mt-4 max-w-3xl text-base leading-7 text-[#667085]">
                      {formatDashboardCopy(copy.heroDescription, { stepCount: config.dailyPlanStepCount, minutes: config.estimatedMinutes })}
                    </p>
                  </div>
                  <Link
                    to={ctaTarget}
                    className="dashboard-home__primary-action group inline-flex min-h-16 items-center justify-center gap-3 rounded-lg bg-[#2F6BFF] px-7 py-4 text-base font-bold text-white shadow-[0_18px_42px_rgba(47,107,255,0.34)] transition hover:-translate-y-0.5 hover:bg-[#245BDE] focus:outline-none focus:ring-4 focus:ring-[#2F6BFF]/20"
                  >
                    <PlayCircle size={22} />
                    <span className="text-left">{ctaLabel}</span>
                    <ArrowRight size={21} className="transition group-hover:translate-x-1" />
                  </Link>
                </div>
              </div>

              {!isColdStart && (
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                  {config.metricCards.map(({ key, label, iconKey }) => {
                    const Icon = iconMap[iconKey];
                    return (
                    <div key={label} className="dashboard-metric-card rounded-lg border border-white bg-white/78 px-4 py-3 shadow-[0_12px_32px_rgba(15,23,42,0.05)]">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#EEF5FF] text-[#2F6BFF]">
                          <Icon size={18} />
                        </div>
                        <div>
                          <div className="text-xs font-medium text-[#667085]">{label}</div>
                          <div className="mt-0.5 text-lg font-black text-[#111827]">{metricValues[key]}</div>
                        </div>
                      </div>
                    </div>
                  )})}
                </div>
              )}
            </div>

            <div className="dashboard-coach-card rounded-lg border border-white bg-white/78 p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.78)]">
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#111827] text-white">
                  <Bot size={23} />
                </div>
                <div>
                  <div className="text-base font-bold text-[#111827]">{copy.assistantTitle}</div>
                  <p className="mt-1 text-sm leading-6 text-[#667085]">{copy.assistantDescription}</p>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {coachLines.map((line) => (
                  <div key={line} className="rounded-lg bg-[#F8FAFC] px-3 py-2 text-sm leading-6 text-[#344054]">
                    {line}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(520px, 100%), 1fr))' }}>
        <section className="rounded-lg border border-[#E6ECF7] bg-white/92 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.07)]">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold text-[#111827]">{copy.guideTitle}</h2>
              <p className="mt-1 text-sm text-[#667085]">{copy.guideDescription}</p>
            </div>
            <Link to={config.routes.learningPath} className="inline-flex items-center gap-1 text-sm font-semibold text-[#2F6BFF]">
              {copy.fullPathAction}
              <ArrowRight size={15} />
            </Link>
          </div>

          {path.isLoading && <LoadingState />}
          {!path.isLoading && nodes.length === 0 && <EmptyState label={copy.emptyPath} />}
          {nodes.length > 0 && (
            <div className="mt-5 space-y-3">
              {guideSteps.map((step, index) => {
                const Icon = iconMap[step.iconKey];
                const isCurrent = step.status === 'current';
                const isLocked = step.status === 'locked';
                return (
                  <div
                    key={step.key}
                    className={`dashboard-step-card relative grid items-center gap-3 rounded-lg border border-[#E6ECF7] bg-[#FBFCFF] p-4 ${isCurrent ? 'dashboard-step-card--current' : ''}`}
                    style={{ gridTemplateColumns: 'auto minmax(min(240px, 100%), 1fr) auto' }}
                  >
                    {index < guideSteps.length - 1 && <div className="absolute left-[31px] top-[56px] hidden h-[calc(100%-20px)] w-px bg-[#D7E2FF] sm:block" />}
                    <div
                      className={`relative z-10 flex h-11 w-11 items-center justify-center rounded-full ${
                        isCurrent
                          ? 'bg-[#2F6BFF] text-white ring-8 ring-[#EEF5FF]'
                          : isLocked
                            ? 'bg-slate-100 text-slate-400'
                            : 'bg-emerald-500 text-white'
                      }`}
                    >
                      <Icon size={18} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-bold text-[#111827]">{copy.nodePrefix} {index + 1}：{step.title}</div>
                        <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${isCurrent ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500'}`}>
                          {isCurrent ? copy.activeStepLabel : copy.lockedStepLabel}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm leading-6 text-[#667085]">{step.helper}</p>
                    </div>
                    <Link
                      to={step.to}
                      className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition ${
                        isCurrent
                          ? 'bg-[#111827] text-white hover:bg-[#2F6BFF]'
                          : 'border border-[#E6ECF7] bg-white text-[#667085] hover:bg-[#F8FAFC]'
                      }`}
                    >
                      {isCurrent ? copy.enterAction : copy.previewAction}
                      <ArrowRight size={15} />
                    </Link>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-[#E6ECF7] bg-white/92 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.07)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-[#111827]">{isColdStart ? copy.growthTitle : copy.progressTitle}</h2>
              <p className="mt-1 text-sm text-[#667085]">
                {isColdStart ? copy.growthDescription : copy.progressDescription}
              </p>
            </div>
            <PathStatusIcon status={currentNode?.status} />
          </div>

          <div className="mt-5">
            {isColdStart ? (
              <JourneyIllustration />
            ) : (
              <div className="space-y-3">
                {nodes.slice(0, 4).map((node) => {
                  const meta = getStatusMeta(node.status);
                  return (
                    <div key={node.id} className="dashboard-progress-card rounded-lg border border-[#E6ECF7] bg-[#FBFCFF] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-bold text-[#111827]">{node.title}</div>
                          <div className="mt-1 text-xs text-[#667085]">{meta.label}</div>
                        </div>
                        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${meta.badge}`}>
                          {clampPercent(node.mastery)}%
                        </span>
                      </div>
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#EEF2F7]">
                        <div className="dashboard-progress-card__bar h-full rounded-full bg-[#2F6BFF]" style={{ width: `${clampPercent(node.mastery)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>

      <section
        className="grid gap-3 rounded-lg bg-white/35 p-2"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}
      >
        {config.secondaryLinks.map(({ label, to, iconKey }) => {
          const Icon = iconMap[iconKey];
          return (
          <Link key={label} to={to} className="dashboard-secondary-link group flex items-center justify-between rounded-lg border border-white/60 bg-white/72 px-4 py-3 text-sm font-semibold text-[#344054] shadow-[0_8px_24px_rgba(15,23,42,0.025)] transition hover:-translate-y-0.5 hover:border-white hover:bg-white hover:text-[#2F6BFF] hover:shadow-[0_16px_38px_rgba(47,107,255,0.10)]">
            <span className="inline-flex items-center gap-2">
              <Icon size={17} className="text-[#2F6BFF]" />
              {label}
            </span>
            <ArrowRight size={15} className="text-[#98A2B3] transition group-hover:translate-x-1 group-hover:text-[#2F6BFF]" />
          </Link>
        )})}
      </section>
    </div>
  );
}
