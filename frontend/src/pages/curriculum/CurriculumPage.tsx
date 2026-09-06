import { useMemo, useState } from 'react';
import {
  ArrowUpRight,
  BookOpen,
  Braces,
  BrainCircuit,
  Compass,
  Cpu,
  Database,
  Globe,
  GraduationCap,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import curriculumCatalogJson from '../../data/curriculumCatalog.json';

type CurriculumResource = {
  id: string;
  title: string;
  repo: string;
  url: string;
  license: string;
  stars: number;
  description: string;
  resourceType: string;
  difficulty: string;
  zhikeModules: string[];
  usage: string;
};

type CurriculumStage = {
  stage: string;
  title: string;
  goal: string;
  durationWeeks: number;
  resources: CurriculumResource[];
};

type CurriculumTrack = {
  id: string;
  title: string;
  description: string;
  icon: string;
  color: string;
  stages: CurriculumStage[];
};

type CurriculumCatalog = {
  schemaVersion: string;
  updatedAt: string;
  scope: string;
  tracks: CurriculumTrack[];
  closedLoop: Record<string, string>;
};

const catalog = curriculumCatalogJson as unknown as CurriculumCatalog;

const trackIcons: Record<string, LucideIcon> = {
  Cpu,
  Braces,
  Globe,
  Database,
  BrainCircuit,
  Sparkles,
  Compass,
};

const resourceTypeLabels: Record<string, string> = {
  course: '课程',
  lecture: '讲义',
  reading: '阅读',
  reference: '参考',
  quiz: '题库',
  project: '项目',
  code_lab: '代码实验',
};

const difficultyLabels: Record<string, string> = {
  basic: '初级',
  medium: '中级',
  advanced: '进阶',
};

const moduleLabels: Record<string, string> = {
  'learning-path': '学习路径',
  'resource-hall': '资源大厅',
  'knowledge-base': '知识库',
  assessment: '练习评估',
  'code-lab': '代码实验',
  'course-builder': '课程建设',
};

function formatStars(stars: number): string {
  if (stars >= 10000) return `${(stars / 10000).toFixed(1)} 万`;
  return stars.toString();
}

function CurriculumResourceCard({ resource }: { resource: CurriculumResource }): JSX.Element {
  return (
    <article className="curriculum-resource-card">
      <div className="curriculum-resource-card__top">
        <div className="curriculum-resource-card__title-wrap">
          <h3>{resource.title}</h3>
          <p>{resource.description}</p>
        </div>
        <a className="curriculum-resource-card__link" href={resource.url} target="_blank" rel="noreferrer" title="打开 GitHub 仓库">
          <ArrowUpRight size={18} />
        </a>
      </div>

      <div className="curriculum-resource-card__meta">
        <span className="curriculum-meta-pill">{resourceTypeLabels[resource.resourceType] ?? resource.resourceType}</span>
        <span className="curriculum-meta-pill">{difficultyLabels[resource.difficulty] ?? resource.difficulty}</span>
        <span className="curriculum-meta-pill">{resource.license}</span>
        <span className="curriculum-meta-pill curriculum-meta-pill--stars">{formatStars(resource.stars)} Stars</span>
      </div>

      <div className="curriculum-resource-card__modules">
        {resource.zhikeModules.map((moduleKey) => (
          <span key={moduleKey} className="curriculum-module-tag">
            {moduleLabels[moduleKey] ?? moduleKey}
          </span>
        ))}
      </div>

      <p className="curriculum-resource-card__usage">{resource.usage}</p>
    </article>
  );
}

function CurriculumStageSection({ stage }: { stage: CurriculumStage }): JSX.Element {
  return (
    <section className="curriculum-stage" aria-label={stage.title}>
      <header className="curriculum-stage__head">
        <div>
          <span className="curriculum-stage__label">{stage.stage}</span>
          <h2>{stage.title}</h2>
          <p>{stage.goal}</p>
        </div>
        {stage.durationWeeks > 0 && <span className="curriculum-stage__duration">约 {stage.durationWeeks} 周</span>}
      </header>
      <div className="curriculum-resource-grid">
        {stage.resources.map((resource) => (
          <CurriculumResourceCard key={resource.id} resource={resource} />
        ))}
      </div>
    </section>
  );
}

export function CurriculumPage(): JSX.Element {
  const [activeTrackId, setActiveTrackId] = useState(catalog.tracks[0]?.id ?? '');
  const activeTrack = useMemo(
    () => catalog.tracks.find((track) => track.id === activeTrackId) ?? catalog.tracks[0],
    [activeTrackId],
  );

  const activeResourceCount = useMemo(
    () => activeTrack?.stages.reduce((total, stage) => total + stage.resources.length, 0) ?? 0,
    [activeTrack],
  );

  const loopEntries = useMemo(
    () => [
      { key: 'learn', title: '学', content: catalog.closedLoop.learn },
      { key: 'practice', title: '练', content: catalog.closedLoop.practice },
      { key: 'assess', title: '测', content: catalog.closedLoop.assess },
      { key: 'reflect', title: '评', content: catalog.closedLoop.reflect },
      { key: 'accumulate', title: '沉淀', content: catalog.closedLoop.accumulate },
    ],
    [],
  );

  if (!activeTrack) {
    return (
      <OverlayPageShell
        pageClassName="curriculum-page"
        title="课程体系"
        subtitle="计算机与人工智能课程地图与开源资料目录。"
      >
        <p className="rounded-md border border-dashed border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          暂无课程体系数据
        </p>
      </OverlayPageShell>
    );
  }

  const TrackIcon = trackIcons[activeTrack.icon] ?? BookOpen;

  return (
    <OverlayPageShell
      pageClassName="curriculum-page"
      title="课程体系"
      subtitle="计算机与人工智能的完整学习地图，按主线、阶段与开源资料组织，可直接进入对应智课模块学习。"
    >
      <PageHeaderToolbar variant="tabs" className="curriculum-filter-bar">
        {catalog.tracks.map((track) => (
          <button
            key={track.id}
            type="button"
            className={track.id === activeTrack.id ? 'is-active' : ''}
            onClick={() => setActiveTrackId(track.id)}
          >
            {track.title}
          </button>
        ))}
      </PageHeaderToolbar>

      <section className="curriculum-track-intro" aria-label="当前主线">
        <div className="curriculum-track-intro__icon" aria-hidden="true">
          <TrackIcon size={24} />
        </div>
        <div className="curriculum-track-intro__body">
          <p>{activeTrack.description}</p>
          <span>
            {activeTrack.stages.length} 个阶段 · {activeResourceCount} 项资料
          </span>
        </div>
      </section>

      <div className="curriculum-stage-list">
        {activeTrack.stages.map((stage) => (
          <CurriculumStageSection key={`${activeTrack.id}-${stage.stage}`} stage={stage} />
        ))}
      </div>

      <section className="curriculum-closed-loop" aria-label="学习闭环">
        <header className="curriculum-closed-loop__head">
          <GraduationCap size={18} />
          <span>学练测评沉淀闭环</span>
        </header>
        <div className="curriculum-closed-loop__grid">
          {loopEntries.map((entry) => (
            <div key={entry.key} className="curriculum-loop-item">
              <strong>{entry.title}</strong>
              <p>{entry.content}</p>
            </div>
          ))}
        </div>
      </section>
    </OverlayPageShell>
  );
}
