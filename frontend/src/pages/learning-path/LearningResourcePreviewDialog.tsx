import { ExternalLink, FileText, Loader2, Quote, X } from 'lucide-react';
import { DocumentPreviewPanel } from '../../components/canvas/DocumentPreviewPanel';
import { MindmapPreviewPanel } from '../../components/canvas/MindmapPreviewPanel';
import { QuizAssessmentPanel } from '../../components/canvas/QuizAssessmentPanel';
import type { Resource } from '../../types';
import { sanitizeResourceContentForPreview } from '../../utils/resource-content-sanitizer';

type LearningResourcePreviewDialogProps = {
  detailContent: string;
  detailResource?: Resource | null;
  isLoading: boolean;
  onClose: () => void;
  previewResource?: Resource | null;
};

function resourceTypeLabel(resource?: Resource | null): string {
  const type = resource?.resource_type ?? resource?.type;
  const labels: Record<string, string> = {
    code_lab: '代码实验',
    diagram_pack: '教学图解包',
    lecture: '讲义',
    mindmap: '思维导图',
    quiz: '自测题',
    reading: '拓展阅读',
    video: '视频',
    misconception_card: '错题补救卡',
  };
  return labels[String(type ?? '')] ?? String(type ?? '资源');
}

function normalizedResourceType(resource?: Resource | null): string {
  return String(resource?.resource_type ?? resource?.type ?? '').trim();
}

function previewFilename(resource: Resource | null | undefined): string {
  const title = resource?.title?.trim() || 'resource';
  if (normalizedResourceType(resource) === 'code_lab') return `${title}.py`;
  return `${title}.md`;
}

function renderResourceCanvas(resource: Resource | null | undefined, content: string): JSX.Element {
  const resourceType = normalizedResourceType(resource);
  const title = resource?.title ?? '资源预览';
  const subtitle = resource?.summary || undefined;
  const safeContent = sanitizeResourceContentForPreview(content);

  if (resourceType === 'quiz') {
    return (
      <QuizAssessmentPanel
        title={title}
        subtitle={subtitle}
        content={safeContent}
        courseId={resource?.course_id}
        conceptId={resource?.concept_id}
        pathNodeId={resource?.path_node_id}
        resourceId={resource?.id}
        status="ready"
      />
    );
  }

  if (resourceType === 'mindmap') {
    return (
      <MindmapPreviewPanel
        filename={previewFilename(resource)}
        title={title}
        subtitle={subtitle}
        content={safeContent}
      />
    );
  }

  return (
    <DocumentPreviewPanel
      filename={previewFilename(resource)}
      title={title}
      subtitle={subtitle}
      content={safeContent || '暂无资源正文'}
      isMarkdown={resourceType !== 'code_lab'}
      scrollTargetId={null}
      status="ready"
      showToolbar={false}
    />
  );
}

/** 学习路径内复用资源生成画布预览，确保讲义、导图、测评题保持原有视觉效果。 */
export function LearningResourcePreviewDialog({
  detailContent,
  detailResource,
  isLoading,
  onClose,
  previewResource,
}: LearningResourcePreviewDialogProps): JSX.Element {
  const resource = detailResource ?? previewResource;
  const citations = detailResource?.citations ?? previewResource?.citations ?? [];
  const content = detailContent || detailResource?.content || previewResource?.content || '';

  return (
    <div className="learning-resource-preview" role="dialog" aria-modal="true" aria-label={`资源预览：${resource?.title ?? '学习资源'}`}>
      <div className="learning-resource-preview__panel">
        <header className="learning-resource-preview__header">
          <div className="learning-resource-preview__title">
            <div className="learning-resource-preview__badges">
              <span>{resourceTypeLabel(resource)}</span>
              <span>v{resource?.latest_version ?? 1}</span>
              {resource?.citation_coverage ? <span>{resource.citation_coverage}</span> : null}
            </div>
            <h2>{resource?.title ?? '资源预览'}</h2>
            <p>{resource?.summary || '暂无摘要，正文加载完成后可直接阅读。'}</p>
          </div>
          <div className="learning-resource-preview__actions">
            {resource?.id ? (
              <a href={`/resource-hall?preview=${resource.id}`} title="去资源大厅查看完整详情">
                <ExternalLink size={16} />
              </a>
            ) : null}
            <button type="button" onClick={onClose} title="关闭预览">
              <X size={17} />
            </button>
          </div>
        </header>

        <div className="learning-resource-preview__body">
          <main className="learning-resource-preview__canvas">
            {isLoading ? (
              <div className="learning-resource-preview__loading">
                <Loader2 className="animate-spin" size={18} />
                正在加载已生成资源
              </div>
            ) : (
              renderResourceCanvas(resource, content)
            )}
          </main>

          <aside className="learning-resource-preview__aside">
            <section>
              <h3>
                <FileText size={15} />
                资源信息
              </h3>
              <dl>
                <div>
                  <dt>难度</dt>
                  <dd>{resource?.difficulty_label ?? resource?.difficulty ?? '未标注'}</dd>
                </div>
                <div>
                  <dt>质量</dt>
                  <dd>{resource?.quality ?? resource?.quality_score ?? '待评估'}</dd>
                </div>
                <div>
                  <dt>知识点</dt>
                  <dd>{resource?.concept_title ?? '当前节点'}</dd>
                </div>
              </dl>
            </section>

            <section>
              <h3>
                <Quote size={15} />
                引用依据
              </h3>
              <div className="learning-resource-preview__citations">
                {citations.slice(0, 5).map((citation, index) => (
                  <article key={`${citation.source_title ?? citation.sourceTitle ?? 'source'}-${index}`}>
                    <strong>{citation.source_title ?? citation.sourceTitle ?? '课程资料'}</strong>
                    <p>{citation.snippet}</p>
                  </article>
                ))}
                {citations.length === 0 ? <p className="learning-resource-preview__muted">暂无引用依据。</p> : null}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}
