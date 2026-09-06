import { create, type StoreApi, type UseBoundStore } from 'zustand';
import type { WorkspaceChatMessage } from './conversation.store';
import type { ArtifactViewMode, CanvasMode, InspectorPanelTab, InspectorTab } from '../types/resource-workspace';
import { resolveArtifactId } from '../utils/resolve-artifact-id';
import { deriveCanvasMode } from '../utils/resource-workspace-state';
import {
  buildResourcePreviewPayload,
  resolveResourcePreviewFromMessage,
  scrollResourceCardIntoView,
} from '../utils/resource-preview';

export type WorkspaceRole = 'student' | 'admin';
export type WorkspaceMode = 'standalone' | 'split' | 'overlay';
export type RightPanelMode = 'pipeline-preview' | null;

export type CanvasType =
  | 'dashboard'
  | 'chat'
  | 'path'
  | 'calendar'
  | 'workshop'
  | 'assessment'
  | 'hall'
  | 'profile'
  | 'announcements'
  | 'settings'
  | 'classes'
  | 'builder'
  | 'knowledge'
  | 'gateway'
  | 'review'
  | 'monitoring'
  | 'announcementAdmin'
  | 'appearance'
  | 'assignments'
  | 'quizzes'
  | 'notifications'
  | 'history'
  | 'sandbox'
  | 'curriculum';

export type ArtifactWorkspaceMeta = {
  title: string;
  prompt: string;
  resourceType: string;
  startedAt: number;
  localStatus?: 'queued' | 'need_input' | 'failed';
  localErrorMessage?: string;
};

export type UiState = {
  /** true：侧栏完全隐藏；false：侧栏展开显示 */
  sidebarCollapsed: boolean;
  /** 侧栏展开时的像素宽度，可通过分割线拖动调整 */
  sidebarWidth: number;
  currentRole: WorkspaceRole;
  workspaceMode: WorkspaceMode;
  isCanvasOpen: boolean;
  isHistoryPanelOpen: boolean;
  canvasType: CanvasType;
  activeCommand: string | null;
  splitOutlineCollapsed: boolean;
  previewFocusRequest: number;
  rightPanelOpen: boolean;
  rightPanelMode: RightPanelMode;
  activeArtifactId: string | null;
  activeTaskId: string | null;
  canvasMode: CanvasMode;
  inspectorOpen: boolean;
  inspectorTab: InspectorPanelTab;
  artifactViewMode: ArtifactViewMode;
  artifactMeta: ArtifactWorkspaceMeta | null;
  activeMessageId: string | null;
  activeResourceType: string | null;
  activeResourceTitle: string | null;
  /** @deprecated 由 activeTaskId + artifactMeta 替代 */
  activeResourceId: string | null;
  activePipelineRunId: string | null;
  resourcePreviewTask: ArtifactWorkspaceMeta & { taskId: string } | null;
  chunkWorkbenchFullscreen: boolean;
  /** 冷启动引导态：true 时工作台隐藏左侧导航、桌宠、多智能体现场等，只保留精简对话区 */
  onboardingActive: boolean;
  setOnboardingActive: (active: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setSidebarWidth: (width: number) => void;
  toggleSidebar: () => void;
  setCurrentRole: (role: WorkspaceRole) => void;
  openCanvas: (canvasType?: CanvasType) => void;
  openSplitCanvas: (canvasType?: CanvasType) => void;
  closeCanvas: () => void;
  setWorkspaceMode: (mode: WorkspaceMode) => void;
  setCanvasType: (canvasType: CanvasType) => void;
  setActiveCommand: (command: string | null) => void;
  openHistoryWorkspace: () => void;
  closeHistoryWorkspace: () => void;
  toggleHistoryWorkspace: () => void;
  toggleSplitOutlineCollapsed: () => void;
  requestPreviewFocus: () => void;
  setActiveTask: (payload: {
    taskId: string;
    title: string;
    prompt?: string;
    resourceType: string;
    startedAt?: number;
    messageId?: string | null;
  }) => void;
  setActiveArtifact: (artifactId: string, meta?: Partial<ArtifactWorkspaceMeta>) => void;
  activateArtifactFromTask: (hints: {
    resultResourceId?: string | null;
    resultResourceCode?: string | null;
    lookup?: string | null;
    meta?: Partial<ArtifactWorkspaceMeta>;
  }) => Promise<string | null>;
  openInspector: (tab: InspectorPanelTab) => void;
  closeInspector: () => void;
  /** @deprecated 请优先使用 openInspector / closeInspector */
  setInspectorTab: (tab: InspectorTab | null) => void;
  setArtifactViewMode: (mode: ArtifactViewMode) => void;
  openResourcePreview: (payload: {
    artifactId?: string | null;
    taskId?: string | null;
    messageId?: string;
    resourceType?: string;
    resourceTitle?: string;
    title?: string;
    prompt?: string;
    startedAt?: number;
    localStatus?: 'queued' | 'need_input' | 'failed';
    localErrorMessage?: string;
  }) => void;
  openResourcePreviewFromMessage: (message: WorkspaceChatMessage) => void;
  resetResourcePreview: () => void;
  syncCanvasMode: () => void;
  setChunkWorkbenchFullscreen: (active: boolean) => void;
};

function applyTaskState(
  set: (partial: Partial<UiState> | ((state: UiState) => Partial<UiState>)) => void,
  get: () => UiState,
  taskId: string,
  meta: ArtifactWorkspaceMeta,
  messageId?: string | null,
) {
  set((state) => {
    const activeArtifactId = null;
    const activeTaskId = taskId;
    return {
      activeArtifactId,
      activeTaskId,
      activePipelineRunId: taskId,
      activeResourceId: taskId,
      artifactMeta: meta,
      activeMessageId: messageId ?? state.activeMessageId,
      activeResourceType: meta.resourceType,
      activeResourceTitle: meta.title,
      resourcePreviewTask: { taskId, ...meta },
      artifactViewMode: 'preview' as ArtifactViewMode,
      canvasMode: deriveCanvasMode(activeArtifactId, activeTaskId),
      previewFocusRequest: state.previewFocusRequest + 1,
    };
  });
}

function normalizeInspectorPanelTab(tab: InspectorTab | InspectorPanelTab | null | undefined): InspectorPanelTab {
  if (tab === 'trace' || tab === 'versions') return tab;
  if (tab === 'citations' || tab === 'evidence') return 'evidence';
  return 'evidence';
}

function applyArtifactState(
  set: (partial: Partial<UiState> | ((state: UiState) => Partial<UiState>)) => void,
  get: () => UiState,
  artifactId: string,
  meta?: Partial<ArtifactWorkspaceMeta>,
  preserveTask = Boolean(meta),
) {
  set((state) => {
    const artifactMeta = meta
      ? {
          title: meta.title ?? state.artifactMeta?.title ?? '资源',
          prompt: meta.prompt ?? state.artifactMeta?.prompt ?? '',
          resourceType: meta.resourceType ?? state.artifactMeta?.resourceType ?? 'lecture',
          startedAt: meta.startedAt ?? state.artifactMeta?.startedAt ?? Date.now(),
          localStatus: meta.localStatus,
        }
      : state.artifactMeta
        ? { ...state.artifactMeta, localStatus: undefined }
        : state.artifactMeta;
    const activeArtifactId = artifactId;
    const activeTaskId = preserveTask ? state.activeTaskId : null;
    return {
      activeArtifactId,
      activeTaskId,
      activePipelineRunId: activeTaskId,
      activeResourceId: artifactId,
      artifactMeta,
      inspectorTab: normalizeInspectorPanelTab(state.inspectorTab),
      artifactViewMode: 'preview' as ArtifactViewMode,
      canvasMode: deriveCanvasMode(activeArtifactId, activeTaskId),
      previewFocusRequest: state.previewFocusRequest + 1,
    };
  });
}

function normalizeSidebarWidth(width: number): number {
  return Math.min(360, Math.max(180, Math.round(width)));
}

export const useUiStore: UseBoundStore<StoreApi<UiState>> = create<UiState>((set, get) => ({
  /** false：侧栏展开；true：侧栏完全隐藏（非图标窄栏） */
  sidebarCollapsed: false,
  sidebarWidth: 240,
  currentRole: 'student',
  workspaceMode: 'standalone',
  isCanvasOpen: false,
  isHistoryPanelOpen: false,
  canvasType: 'dashboard',
  activeCommand: null,
  splitOutlineCollapsed: false,
  previewFocusRequest: 0,
  rightPanelOpen: false,
  rightPanelMode: null,
  activeArtifactId: null,
  activeTaskId: null,
  canvasMode: 'empty',
  inspectorOpen: false,
  inspectorTab: 'evidence',
  artifactViewMode: 'preview',
  artifactMeta: null,
  activeMessageId: null,
  activeResourceType: null,
  activeResourceTitle: null,
  activeResourceId: null,
  activePipelineRunId: null,
  resourcePreviewTask: null,
  chunkWorkbenchFullscreen: false,
  onboardingActive: false,
  setOnboardingActive: (active) => set({ onboardingActive: active }),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setSidebarWidth: (width) => set({ sidebarWidth: normalizeSidebarWidth(width) }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setCurrentRole: (role) => set({ currentRole: role }),
  openCanvas: (canvasType) =>
    set((state) => ({ workspaceMode: 'overlay', isCanvasOpen: true, canvasType: canvasType ?? state.canvasType })),
  openSplitCanvas: (canvasType) =>
    set((state) => ({
      workspaceMode: 'split',
      isCanvasOpen: true,
      canvasType: canvasType ?? state.canvasType,
    })),
  closeCanvas: () =>
    set({
      workspaceMode: 'standalone',
      isCanvasOpen: false,
      canvasType: 'dashboard',
      rightPanelOpen: false,
      rightPanelMode: null,
      activeArtifactId: null,
      activeTaskId: null,
      canvasMode: 'empty',
      inspectorOpen: false,
      inspectorTab: 'evidence',
      artifactViewMode: 'preview',
      artifactMeta: null,
      activeResourceId: null,
      activePipelineRunId: null,
      activeMessageId: null,
      activeResourceType: null,
      activeResourceTitle: null,
      resourcePreviewTask: null,
    }),
  setWorkspaceMode: (mode) => set({ workspaceMode: mode, isCanvasOpen: mode !== 'standalone' }),
  setCanvasType: (canvasType) => set({ canvasType }),
  setActiveCommand: (command) => set({ activeCommand: command }),
  openHistoryWorkspace: () => set({ isHistoryPanelOpen: true }),
  closeHistoryWorkspace: () => set({ isHistoryPanelOpen: false }),
  toggleHistoryWorkspace: () => set((state) => ({ isHistoryPanelOpen: !state.isHistoryPanelOpen })),
  toggleSplitOutlineCollapsed: () => set((state) => ({ splitOutlineCollapsed: !state.splitOutlineCollapsed })),
  requestPreviewFocus: () => set((state) => ({ previewFocusRequest: state.previewFocusRequest + 1 })),
  syncCanvasMode: () => {
    const { activeArtifactId, activeTaskId } = get();
    set({ canvasMode: deriveCanvasMode(activeArtifactId, activeTaskId) });
  },
  setActiveTask: ({ taskId, title, prompt = '', resourceType, startedAt, messageId }) => {
    const meta: ArtifactWorkspaceMeta = {
      title,
      prompt,
      resourceType,
      startedAt: startedAt ?? Date.now(),
    };
    applyTaskState(set, get, taskId, meta, messageId);
    get().openSplitCanvas('workshop');
  },
  setActiveArtifact: (artifactId, meta) => {
    applyArtifactState(set, get, artifactId, meta);
    get().openSplitCanvas('workshop');
  },
  activateArtifactFromTask: async (hints) => {
    const artifactId = await resolveArtifactId(hints);
    if (!artifactId) return null;
    applyArtifactState(set, get, artifactId, hints.meta, true);
    get().openSplitCanvas('workshop');
    return artifactId;
  },
  openInspector: (tab) =>
    set({
      inspectorOpen: true,
      inspectorTab: tab,
    }),
  closeInspector: () => set({ inspectorOpen: false }),
  setInspectorTab: (tab) => {
    if (tab === null) {
      set({ inspectorOpen: false });
      return;
    }
    const normalized = normalizeInspectorPanelTab(tab);
    if (tab === 'outline') return;
    set({ inspectorOpen: true, inspectorTab: normalized });
  },
  setArtifactViewMode: (mode) => set({ artifactViewMode: mode }),
  openResourcePreview: (payload) => {
    const startedAt = payload.startedAt ?? Date.now();
    const resourceTitle = payload.resourceTitle ?? payload.title ?? '资源';
    const hasTask = Boolean(payload.taskId);
    const hasArtifact = Boolean(payload.artifactId);
    const meta: ArtifactWorkspaceMeta = {
      title: resourceTitle,
      prompt: payload.prompt ?? '',
      resourceType: payload.resourceType ?? 'lecture',
      startedAt,
      localStatus: payload.localStatus ?? (!hasTask && !hasArtifact ? 'queued' : undefined),
      localErrorMessage: payload.localErrorMessage,
    };

    if (payload.taskId) {
      applyTaskState(set, get, payload.taskId, meta, payload.messageId);
    } else if (payload.artifactId) {
      applyArtifactState(set, get, payload.artifactId, meta, false);
    } else if (meta.localStatus) {
      set((state) => ({
        activeArtifactId: null,
        activeTaskId: null,
        artifactMeta: meta,
        activeMessageId: payload.messageId ?? state.activeMessageId,
        activeResourceType: meta.resourceType,
        activeResourceTitle: meta.title,
        activeResourceId: null,
        activePipelineRunId: null,
        resourcePreviewTask: null,
        canvasMode: 'generating',
        artifactViewMode: 'preview',
        inspectorTab: normalizeInspectorPanelTab(state.inspectorTab),
        previewFocusRequest: state.previewFocusRequest + 1,
      }));
    }

    set({
      artifactViewMode: 'preview',
    });
    get().openSplitCanvas('workshop');
    scrollResourceCardIntoView({
      resourceId: !hasTask ? payload.artifactId ?? undefined : undefined,
      pipelineRunId: payload.taskId ?? undefined,
      resourceTitle,
    });
  },
  openResourcePreviewFromMessage: (message) => {
    const resolved = resolveResourcePreviewFromMessage(message);
    const payload = buildResourcePreviewPayload(message);
    const canOpenArtifact =
      !resolved.pipelineRunId || message.taskStatus === 'completed' || message.taskStatus === 'succeeded';
    const artifactId = canOpenArtifact
      ? message.artifactId ?? (message.resourceId && message.resourceId !== resolved.pipelineRunId ? message.resourceId : undefined)
      : undefined;
    get().openResourcePreview({
      taskId: canOpenArtifact && artifactId ? undefined : resolved.pipelineRunId ?? undefined,
      artifactId,
      messageId: resolved.messageId,
      resourceType: resolved.resourceType,
      resourceTitle: resolved.resourceTitle,
      title: payload.title,
      prompt: payload.prompt,
      startedAt: payload.startedAt,
    });
  },
  resetResourcePreview: () =>
    set({
      rightPanelOpen: false,
      rightPanelMode: null,
      activeArtifactId: null,
      activeTaskId: null,
      canvasMode: 'empty',
      inspectorOpen: false,
      inspectorTab: 'evidence',
      artifactViewMode: 'preview',
      artifactMeta: null,
      activeResourceId: null,
      activePipelineRunId: null,
      activeMessageId: null,
      activeResourceType: null,
      activeResourceTitle: null,
      resourcePreviewTask: null,
    }),
  setChunkWorkbenchFullscreen: (active) => set({ chunkWorkbenchFullscreen: active }),
}));
