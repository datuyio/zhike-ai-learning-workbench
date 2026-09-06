import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BadgeCheck,
  BookOpen,
  BookmarkCheck,
  CalendarPlus,
  CheckCircle2,
  Upload,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import { useConfirm } from '../../context/ConfirmContext';
import { useCourseQueries } from '../../hooks/useCourseData';
import { useCourseContextStore } from '../../stores/course-context.store';
import {
  type ResourceHallScope,
} from '../../utils/resource-hall-scope';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { ResourceHallCardWall } from './ResourceHallCardWall';
import { ResourceHallFocusSection } from './ResourceHallFocusSection';
import { ResourceHallHero } from './ResourceHallHero';
import { ResourceHallPreviewDialog } from './ResourceHallPreviewDialog';
import { ResourceHallSidebar } from './ResourceHallSidebar';
import { ResourceUploadDialog } from './ResourceUploadDialog';
import {
  StatTile,
} from './ResourceHallWidgets';
import {
  fallbackDifficultyFilters,
  fallbackTypeFilters,
  type ResourceNotice,
} from './resourceHallConfig';
import {
  areAllDeletablePageResourcesSelected,
  countActiveResourceHallFilters,
  countUncitedResources,
  createVisibleResourceMap,
  getDeletablePageResourceIds,
  getDeletablePageResources,
  getSelectedPageResources,
  pruneSelectionToVisibleResources,
  toggleCurrentPageSelection as toggleCurrentPageSelectionState,
  toggleSelectedResourceId,
} from './resourceHallSelectors';
import { useResourceHallInteractions } from './useResourceHallInteractions';
import { useResourceHallPreview } from './useResourceHallPreview';
import {
  useResourceUploadDialog,
} from './useResourceUploadDialog';
import { useResourceHallDensity } from './useResourceHallDensity';
import { useResourceHallDeletion } from './useResourceHallDeletion';
import { useResourceHallMutations } from './useResourceHallMutations';

/** 资源大厅页面：聚合课程、通用、社区和个性化推荐资源。 */
export function ResourceHallPage(): JSX.Element {
  const confirm = useConfirm();
  const { courseId } = useCourseQueries({ includeResources: false });
  const { learningScope, currentCourseTitle } = useCourseContextStore();
  const hasCourse = learningScope === 'course' && Boolean(courseId);
  const currentCourseId = hasCourse ? courseId : null;
  const [resourceType, setResourceType] = useState('all');
  const [resourceDifficulty, setResourceDifficulty] = useState('all');
  const [resourceScope, setResourceScope] = useState<ResourceHallScope>(hasCourse ? 'course' : 'all');
  const [searchText, setSearchText] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const resetPage = useCallback((): void => setPage(1), []);
  const { densityProfile, pageSize, setPageSize } = useResourceHallDensity(resetPage);
  const [resourceNotice, setResourceNotice] = useState<ResourceNotice | null>(null);
  const [selectedResourceIds, setSelectedResourceIds] = useState<string[]>([]);
  const resourceUpload = useResourceUploadDialog({
    hasCourse,
    currentCourseId,
    onNoticeChange: setResourceNotice,
  });
  const hall = useQuery({
    queryKey: ['resource-hall', currentCourseId || 'general', resourceScope, resourceType, resourceDifficulty, debouncedSearch, page, pageSize],
    queryFn: () => api.resourceHall(currentCourseId, {
      q: debouncedSearch,
      scope: resourceScope,
      type: resourceType,
      difficulty: resourceDifficulty,
      page,
      pageSize,
    }),
    placeholderData: (previousData) => previousData,
  });
  const pagedResources = hall.data?.items ?? [];
  const pagination = hall.data?.pagination ?? {
    page,
    page_size: pageSize,
    total_items: 0,
    total_pages: 1,
    offset: 0,
    has_prev: false,
    has_next: false,
  };

  const typeOptions = hall.data?.filters.resource_types?.length ? hall.data.filters.resource_types : fallbackTypeFilters;
  const difficultyOptions = hall.data?.filters.difficulties?.length ? hall.data.filters.difficulties : fallbackDifficultyFilters;
  const featuredResources = useMemo(
    () => hall.data?.highlights.featured?.length
      ? hall.data.highlights.featured
      : pagedResources.filter((item) => item.is_featured).slice(0, 3),
    [hall.data?.highlights.featured, pagedResources],
  );
  const recommendedResources = useMemo(
    () => hall.data?.highlights.recommended?.length
      ? hall.data.highlights.recommended
      : pagedResources.filter((item) => item.is_recommended).slice(0, 4),
    [hall.data?.highlights.recommended, pagedResources],
  );
  const visibleFeaturedResources = useMemo(
    () => featuredResources.slice(0, densityProfile.featuredLimit),
    [densityProfile.featuredLimit, featuredResources],
  );
  const visibleRecommendedResources = useMemo(
    () => recommendedResources.slice(0, densityProfile.recommendedLimit),
    [densityProfile.recommendedLimit, recommendedResources],
  );
  const deletablePageResources = useMemo(
    () => getDeletablePageResources(pagedResources),
    [pagedResources],
  );
  const deletablePageResourceIds = useMemo(
    () => getDeletablePageResourceIds(pagedResources),
    [pagedResources],
  );
  const selectedPageResources = useMemo(
    () => getSelectedPageResources(pagedResources, selectedResourceIds),
    [pagedResources, selectedResourceIds],
  );
  const allDeletablePageSelected = areAllDeletablePageResourcesSelected(
    deletablePageResourceIds,
    selectedResourceIds,
  );
  const deletablePageResourceIdKey = deletablePageResourceIds.join('|');

  const preview = useResourceHallPreview({
    pagedResources,
    visibleFeaturedResources,
    visibleRecommendedResources,
    resourceScope,
  });

  const {
    updateResource,
    copyResource,
    submitResource,
    restoreVersion,
    deleteResource,
    batchDeleteResources,
    uploadResource,
  } = useResourceHallMutations({
    previewId: preview.previewId,
    onPreviewIdChange: preview.setPreviewId,
    onPreviewVersionChange: preview.setPreviewVersion,
    onEditingChange: preview.setIsEditing,
    onNoticeChange: setResourceNotice,
    onSelectedResourceIdsChange: setSelectedResourceIds,
    onResourceScopeChange: setResourceScope,
    onPageChange: setPage,
    onUploadSuccessReset: resourceUpload.resetAfterSuccess,
  });

  const hallInteractions = useResourceHallInteractions({
    previewId: preview.previewId,
    previewResource: preview.previewResource,
    onNoticeChange: setResourceNotice,
  });
  const {
    requestDeleteResource,
    requestBatchDeleteResources,
  } = useResourceHallDeletion({
    confirm,
    selectedPageResources,
    onNoticeChange: setResourceNotice,
    onDeleteResource: deleteResource.mutate,
    onBatchDeleteResources: batchDeleteResources.mutate,
  });
  const visibleResourceMap = useMemo(
    () => createVisibleResourceMap(
      [...pagedResources, ...visibleFeaturedResources, ...visibleRecommendedResources],
      preview.detail.data,
    ),
    [pagedResources, visibleFeaturedResources, visibleRecommendedResources, preview.detail.data],
  );
  const uncitedCount = countUncitedResources(pagedResources);
  const activeFilterCount = countActiveResourceHallFilters({
    resourceScope,
    defaultScope: hasCourse ? 'course' : 'all',
    resourceType,
    resourceDifficulty,
    debouncedSearch,
  });
  const activePreviewId = preview.previewId;
  useEffect(() => {
    setResourceScope(hasCourse ? 'course' : 'all');
    setPage(1);
  }, [courseId, hasCourse]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(searchText.trim());
      setPage(1);
    }, 320);
    return () => window.clearTimeout(timer);
  }, [searchText]);

  useEffect(() => {
    setPage(1);
  }, [currentCourseId, pageSize, resourceScope, resourceType, resourceDifficulty]);

  useEffect(() => {
    setSelectedResourceIds((items) => {
      return pruneSelectionToVisibleResources(items, deletablePageResourceIds);
    });
  }, [deletablePageResourceIdKey, deletablePageResourceIds]);

  useEffect(() => {
    if (hall.data?.pagination.page && hall.data.pagination.page !== page) {
      setPage(hall.data.pagination.page);
    }
  }, [hall.data?.pagination.page, page]);

  function openPreview(resourceId: string): void {
    preview.openPreview(resourceId);
    hallInteractions.clearCommentDraft();
  }

  function toggleResourceSelection(resourceId: string, selected: boolean): void {
    setSelectedResourceIds((items) => toggleSelectedResourceId(items, resourceId, selected));
  }

  function toggleCurrentPageSelection(): void {
    setSelectedResourceIds((items) => toggleCurrentPageSelectionState(items, deletablePageResourceIds));
  }

  return (
    <OverlayPageShell
      pageClassName="resource-hall-page min-h-full text-slate-950"
      title="资源大厅"
      subtitle={
        hasCourse
          ? `当前课程：${currentCourseTitle || courseId}。这里把课程资源、我的生成、社区共享和画像推荐放进同一条资源流。`
          : '当前为通用学习模式，可查看通用资源、我的生成和社区精选；选择课程后会出现课程资源与知识点绑定筛选。'
      }
      primaryAction={
        <button
          type="button"
          className="global-header__action-button"
          onClick={() => resourceUpload.openUploadDialog()}
        >
          <Upload size={15} />
          上传资源
        </button>
      }
    >
      <ResourceHallHero
        hasCourse={hasCourse}
        currentCourseTitle={currentCourseTitle}
        courseId={courseId}
        totalCount={hall.data?.stats.total ?? 0}
        savedOrPlannedCount={hallInteractions.savedOrPlannedResources.length}
        communityActivityCount={hallInteractions.communityActivities.length}
        featuredCount={hall.data?.stats.featured ?? 0}
        recommendedCount={hall.data?.stats.recommended ?? 0}
        searchText={searchText}
        typeOptions={typeOptions}
        difficultyOptions={difficultyOptions}
        resourceType={resourceType}
        resourceDifficulty={resourceDifficulty}
        activeFilterCount={activeFilterCount}
        uncitedCount={uncitedCount}
        onSearchTextChange={setSearchText}
        onResourceTypeChange={setResourceType}
        onResourceDifficultyChange={setResourceDifficulty}
        onClearFilters={() => {
          setSearchText('');
          setDebouncedSearch('');
          setResourceType('all');
          setResourceDifficulty('all');
          setResourceScope(hasCourse ? 'course' : 'all');
          setPage(1);
        }}
      />

      <div className="py-5">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <main className="min-w-0 space-y-5">
            <div className={densityProfile.statGridClassName}>
              <StatTile label="待学资源" value={hallInteractions.plannedCount} caption="已加入学习清单，适合继续研读" Icon={CalendarPlus} tone="amber" />
              <StatTile label="已完成" value={hallInteractions.completedCount} caption="你在本地标记完成的资源" Icon={CheckCircle2} tone="emerald" />
              <StatTile label="已收藏" value={hallInteractions.savedCount} caption="暂存但未排入待学计划" Icon={BookmarkCheck} tone="blue" />
              <StatTile label="证据覆盖" value={hall.data?.stats.with_citations ?? 0} caption="带引用依据，便于追溯学习" Icon={BadgeCheck} tone="slate" />
            </div>

            <ResourceHallFocusSection
              featuredResources={visibleFeaturedResources}
              recommendedResources={visibleRecommendedResources}
              onOpenPreview={openPreview}
            />

            <ResourceHallCardWall
              resources={pagedResources}
              isLoading={hall.isLoading}
              hasCourse={hasCourse}
              pagination={pagination}
              densityProfile={densityProfile}
              resourceScope={resourceScope}
              stats={hall.data?.stats}
              scopeFilters={hall.data?.filters.scopes}
              resourceNotice={resourceNotice}
              resourceInteractions={hallInteractions.resourceInteractions}
              deletablePageResources={deletablePageResources}
              selectedResourceIds={selectedResourceIds}
              selectedPageCount={selectedPageResources.length}
              allDeletablePageSelected={allDeletablePageSelected}
              deletePendingResourceId={deleteResource.isPending ? deleteResource.variables?.resourceId ?? null : null}
              batchDeletePending={batchDeleteResources.isPending}
              onScopeChange={setResourceScope}
              onToggleCurrentPageSelection={toggleCurrentPageSelection}
              onBatchDelete={() => void requestBatchDeleteResources()}
              onClearSelection={() => setSelectedResourceIds([])}
              onOpenPreview={openPreview}
              onDeleteResource={(resource) => void requestDeleteResource(resource)}
              onToggleResourceSelection={toggleResourceSelection}
              onPageChange={(nextPage) => setPage(Math.max(1, Math.min(nextPage, pagination.total_pages)))}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(nextPageSize);
                setPage(1);
              }}
            />
          </main>

          <ResourceHallSidebar
            plannedCount={hallInteractions.plannedCount}
            recommendedCount={hall.data?.stats.recommended ?? 0}
            uncitedCount={uncitedCount}
            savedOrPlannedResources={hallInteractions.savedOrPlannedResources}
            communityActivities={hallInteractions.communityActivities}
            visibleResourceMap={visibleResourceMap}
            onOpenPreview={openPreview}
            onShowRecommended={() => {
              setResourceScope('recommended');
              setPage(1);
            }}
            onFocusUncitedResources={() => {
              setResourceDifficulty('all');
              setResourceType('all');
              setPage(1);
            }}
            onUploadClick={resourceUpload.openUploadDialog}
          />
        </div>
      </div>

      {resourceUpload.uploadOpen && (
        <ResourceUploadDialog
          uploadDraft={resourceUpload.uploadDraft}
          uploadFile={resourceUpload.uploadFile}
          uploadDragActive={resourceUpload.uploadDragActive}
          hasCourse={hasCourse}
          currentCourseTitle={currentCourseTitle}
          courseId={courseId}
          isPending={uploadResource.isPending}
          onClose={() => resourceUpload.closeUploadDialog(uploadResource.isPending)}
          onSubmit={() => resourceUpload.submitUploadedResource(uploadResource.mutate)}
          onDragActiveChange={resourceUpload.setUploadDragActive}
          onDrop={resourceUpload.handleResourceUploadDrop}
          onInputChange={resourceUpload.handleResourceUploadInputChange}
          onFileRemove={resourceUpload.removeUploadFile}
          onDraftChange={(patch) => resourceUpload.setUploadDraft((draft) => ({ ...draft, ...patch }))}
        />
      )}
      {activePreviewId && (
        <ResourceHallPreviewDialog
          previewVersion={preview.previewVersion}
          previewResource={preview.previewResource}
          detailResource={preview.detail.data}
          detailContent={preview.detailContent}
          isDetailLoading={preview.detail.isLoading}
          isEditing={preview.isEditing}
          draftContent={preview.draftContent}
          updatePending={updateResource.isPending}
          copyPending={copyResource.isPending}
          submitPending={submitResource.isPending}
          deletePending={deleteResource.isPending}
          restorePending={restoreVersion.isPending}
          versions={preview.versions.data?.items ?? []}
          previewInteraction={hallInteractions.previewInteraction}
          previewComments={hallInteractions.previewComments}
          commentDraft={hallInteractions.commentDraft}
          canDeletePreviewResource={preview.canDeletePreviewResource}
          previewDeleteResource={preview.previewDeleteResource}
          onClose={preview.closePreview}
          onStartEdit={preview.startEdit}
          onDraftContentChange={preview.setDraftContent}
          onSaveDraft={() => updateResource.mutate({ content: preview.draftContent })}
          onCancelEdit={() => preview.setIsEditing(false)}
          onCopyResource={() => copyResource.mutate()}
          onSubmitResource={() => submitResource.mutate()}
          onDeletePreviewResource={() => {
            if (preview.previewDeleteResource) void requestDeleteResource(preview.previewDeleteResource, true);
          }}
          onPreviewVersionChange={preview.selectPreviewVersion}
          onRestoreVersion={(version) => restoreVersion.mutate(version)}
          onToggleLike={() => hallInteractions.toggleLike(activePreviewId, preview.previewResource)}
          onToggleSave={() => hallInteractions.toggleSave(activePreviewId, preview.previewResource)}
          onTogglePlan={() => hallInteractions.togglePlan(activePreviewId, preview.previewResource)}
          onToggleCompleted={() => hallInteractions.toggleCompleted(activePreviewId, preview.previewResource)}
          onShare={() => void hallInteractions.sharePreviewResource(activePreviewId, preview.previewResource)}
          onCommentDraftChange={hallInteractions.setCommentDraft}
          onSubmitComment={() => hallInteractions.submitComment(activePreviewId, preview.previewResource)}
        />
      )}
    </OverlayPageShell>
  );
}
