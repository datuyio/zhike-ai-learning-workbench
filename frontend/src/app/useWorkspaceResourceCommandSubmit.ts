import { useCallback } from 'react';
import type { WorkspaceToastItem } from '../components/shared/WorkspaceToast';
import type { ChatCommandDefinition } from '../config/chat-commands';
import { useGenerateResourceMutation } from '../hooks/useCourseData';
import type { WorkspaceChatMessage } from '../stores/conversation.store';
import { useUiStore, type WorkspaceRole } from '../stores/ui.store';
import type { AgentTraceEvent, SuggestedAction } from '../types';
import { explainTaskFailure } from '../utils/resource-task-errors';
import {
  buildResourceGeneratePayload,
  buildSuggestedActionResourcePayload,
  type DiagramPackImageOptions,
} from '../utils/resource-generation-payload';
import { upsertResourceTaskMessage } from '../utils/resource-task-messages';
import { explainResourceError, formatErrorContent } from '../utils/workspace-errors';
import {
  buildResourceCommandTraceEvents,
  buildSubmittedResourceTaskPatch,
  buildWorkspaceResourceTaskMessage,
  createWorkspaceMessageId,
  type WorkspaceRequestContext,
} from './workspaceDialogueUtils';

type GenerationContextParams = {
  taskId?: string | null;
  artifactId?: string | null;
  concept?: string | null;
  type?: string | null;
  pathNode?: string | null;
};

type SetActiveTaskPayload = {
  taskId: string;
  title: string;
  prompt?: string;
  resourceType: string;
  startedAt?: number;
  messageId?: string | null;
};

type UpdateSessionMessages = (
  sessionId: string,
  updater: (items: WorkspaceChatMessage[]) => WorkspaceChatMessage[],
) => void;

export type WorkspaceResourceCommandSubmissionPlan = {
  conceptIdForTask?: string;
  resourceType: string;
  resourceScope: WorkspaceChatMessage['resourceScope'];
  needsAdditionalInput: boolean;
  generationContext: GenerationContextParams;
};

export type BuildWorkspaceResourceCommandSubmissionPlanInput = {
  command: ChatCommandDefinition;
  isCourseMode: boolean;
  requestContext: WorkspaceRequestContext;
  fallbackConceptId?: string | null;
};

export type SubmitWorkspaceResourceCommandInput = {
  sessionId: string;
  command: ChatCommandDefinition;
  userContent: string;
  contextualMessage: string;
  resourceEvidenceEnabled: boolean;
};

export type SubmitSuggestedResourceActionInput = {
  action: SuggestedAction;
  resolveSessionId: (title: string) => string;
};

export type UseWorkspaceResourceCommandSubmitParams = {
  isCourseMode: boolean;
  courseId: string;
  currentRole: WorkspaceRole;
  requestContext: WorkspaceRequestContext;
  materialClientContext: Record<string, unknown>;
  fallbackConceptId?: string | null;
  diagramPackImageOptions: DiagramPackImageOptions;
  updateSessionMessages: UpdateSessionMessages;
  syncGenerationContext: (params: GenerationContextParams) => void;
  openSplitCanvas: (canvasType?: 'workshop') => void;
  setActiveTask: (payload: SetActiveTaskPayload) => void;
  setTraceEvents: (events: AgentTraceEvent[]) => void;
  clearTraceBuffer: () => void;
  clearSuggestedActions: () => void;
  onToast: (message: string, tone?: WorkspaceToastItem['tone']) => void;
};

export type UseWorkspaceResourceCommandSubmitResult = {
  isSubmittingResource: boolean;
  submitResourceCommand: (input: SubmitWorkspaceResourceCommandInput) => Promise<void>;
  submitSuggestedResourceAction: (input: SubmitSuggestedResourceActionInput) => Promise<void>;
};

/** 解析资源命令提交所需的知识点、资源类型和生成上下文。 */
export function buildWorkspaceResourceCommandSubmissionPlan({
  command,
  isCourseMode,
  requestContext,
  fallbackConceptId,
}: BuildWorkspaceResourceCommandSubmissionPlanInput): WorkspaceResourceCommandSubmissionPlan {
  const resourceType = command.resourceType ?? 'lecture';
  const conceptIdForTask = isCourseMode
    ? requestContext.concept_id ?? fallbackConceptId ?? undefined
    : undefined;
  return {
    conceptIdForTask,
    resourceType,
    resourceScope: isCourseMode ? 'course' : 'general',
    needsAdditionalInput: Boolean(isCourseMode && !conceptIdForTask),
    generationContext: {
      concept: isCourseMode ? conceptIdForTask : undefined,
      type: resourceType,
      pathNode: isCourseMode ? requestContext.path_node_id ?? undefined : undefined,
    },
  };
}

function showResourceErrorToast(
  error: unknown,
  context: { hasCourse: boolean; isUserMode: boolean },
  onToast: UseWorkspaceResourceCommandSubmitParams['onToast'],
): void {
  const explained = explainResourceError(error, context);
  onToast(explained.rootCause ? `${explained.summary}（${explained.rootCause}）` : explained.summary, 'error');
}

/** 提交工作台资源命令和建议动作触发的资源生成任务。 */
export function useWorkspaceResourceCommandSubmit({
  isCourseMode,
  courseId,
  currentRole,
  requestContext,
  materialClientContext,
  fallbackConceptId,
  diagramPackImageOptions,
  updateSessionMessages,
  syncGenerationContext,
  openSplitCanvas,
  setActiveTask,
  setTraceEvents,
  clearTraceBuffer,
  clearSuggestedActions,
  onToast,
}: UseWorkspaceResourceCommandSubmitParams): UseWorkspaceResourceCommandSubmitResult {
  const generateResource = useGenerateResourceMutation();
  const mutateResource = generateResource.mutateAsync;
  const isSubmittingResource = generateResource.isPending;

  const submitResourceCommand = useCallback(async ({
    sessionId,
    command,
    userContent,
    contextualMessage,
    resourceEvidenceEnabled,
  }: SubmitWorkspaceResourceCommandInput): Promise<void> => {
    const plan = buildWorkspaceResourceCommandSubmissionPlan({
      command,
      isCourseMode,
      requestContext,
      fallbackConceptId,
    });

    setTraceEvents(buildResourceCommandTraceEvents({
      commandLabel: command.label,
      resourceEvidenceEnabled,
      isCourseMode,
    }));

    if (plan.needsAdditionalInput) {
      const assistantMessageId = createWorkspaceMessageId('assistant-resource-need-input');
      updateSessionMessages(sessionId, (items) => [
        ...items,
        buildWorkspaceResourceTaskMessage({
          id: assistantMessageId,
          resourceLabel: command.label,
          resourceType: plan.resourceType,
          resourceScope: 'course',
          courseBound: true,
          courseEvidenceRequired: resourceEvidenceEnabled,
          taskStatus: 'need_input',
          taskProgress: 0,
          content: '还缺少学习主题/错题内容/知识点，请补充后继续生成',
          createdAt: Date.now(),
        }),
      ]);
      useUiStore.getState().openResourcePreview({
        messageId: assistantMessageId,
        resourceType: plan.resourceType,
        resourceTitle: command.label,
        prompt: userContent,
        localStatus: 'need_input',
      });
      onToast('还缺少学习主题/错题内容/知识点，请补充后继续生成', 'error');
      return;
    }

    openSplitCanvas('workshop');
    syncGenerationContext(plan.generationContext);
    const assistantMessageId = createWorkspaceMessageId('assistant-resource');
    clearTraceBuffer();
    updateSessionMessages(sessionId, (items) => [
      ...items,
      buildWorkspaceResourceTaskMessage({
        id: assistantMessageId,
        resourceLabel: command.label,
        resourceType: plan.resourceType,
        resourceScope: plan.resourceScope,
        courseBound: isCourseMode,
        courseEvidenceRequired: resourceEvidenceEnabled,
        taskStep: '排队中',
        createdAt: Date.now(),
      }),
    ]);
    useUiStore.getState().openResourcePreview({
      messageId: assistantMessageId,
      resourceType: plan.resourceType,
      resourceTitle: command.label,
      prompt: userContent,
    });

    try {
      const task = await mutateResource(buildResourceGeneratePayload({
        isCourseMode,
        courseId,
        conceptId: plan.conceptIdForTask,
        pathNodeId: requestContext.path_node_id,
        materialContext: {
          materialScope: requestContext.material_scope,
          documentId: requestContext.document_id,
          sourceTitle: requestContext.source_title,
        },
        command,
        message: contextualMessage,
        prompt: userContent,
        useCourseEvidence: resourceEvidenceEnabled,
        imageOptions: plan.resourceType === 'diagram_pack' ? diagramPackImageOptions : undefined,
      }));
      const taskId = task.task_id;
      setActiveTask({
        taskId,
        title: command.label,
        prompt: userContent,
        resourceType: plan.resourceType,
        messageId: assistantMessageId,
      });
      syncGenerationContext({
        ...plan.generationContext,
        taskId,
      });
      const taskPatch = buildSubmittedResourceTaskPatch({
        id: assistantMessageId,
        task,
        resourceScope: plan.resourceScope,
        isCourseMode,
        resourceEvidenceEnabled,
        resourceType: plan.resourceType,
      });
      updateSessionMessages(sessionId, (items) =>
        upsertResourceTaskMessage(items, taskId, taskPatch),
      );
      if (taskPatch.taskStatus === 'failed') {
        const explained = explainTaskFailure(task.error_message, {
          hasCourse: isCourseMode,
          errorCode: task.error_code,
          resourceType: plan.resourceType,
        });
        onToast(explained.summary, 'error');
      } else {
        onToast('任务已进入队列，右侧画布将同步更新', 'info');
      }
    } catch (error) {
      const explained = explainResourceError(error, {
        hasCourse: isCourseMode,
        isUserMode: currentRole === 'student',
      });
      showResourceErrorToast(error, { hasCourse: isCourseMode, isUserMode: currentRole === 'student' }, onToast);
      useUiStore.getState().openResourcePreview({
        messageId: assistantMessageId,
        resourceType: plan.resourceType,
        resourceTitle: command.label,
        prompt: userContent,
        localStatus: 'failed',
        localErrorMessage: explained.summary,
      });
      updateSessionMessages(sessionId, (items) =>
        items.map((item) =>
          item.id === assistantMessageId
            ? {
                ...item,
                variant: 'error',
                taskStatus: 'failed',
                content: formatErrorContent(explained),
              }
            : item,
        ),
      );
    }
  }, [
    clearTraceBuffer,
    courseId,
    currentRole,
    diagramPackImageOptions,
    fallbackConceptId,
    isCourseMode,
    mutateResource,
    onToast,
    openSplitCanvas,
    requestContext,
    setActiveTask,
    setTraceEvents,
    syncGenerationContext,
    updateSessionMessages,
  ]);

  const submitSuggestedResourceAction = useCallback(async ({
    action,
    resolveSessionId,
  }: SubmitSuggestedResourceActionInput): Promise<void> => {
    if (!isCourseMode) {
      onToast('请选择课程后使用课程资源生成', 'error');
      return;
    }
    if (isSubmittingResource) return;
    const conceptIdForTask = requestContext.concept_id ?? fallbackConceptId ?? undefined;
    if (!conceptIdForTask) {
      onToast('当前课程暂无可用知识点，无法生成资源', 'error');
      return;
    }

    clearSuggestedActions();
    openSplitCanvas('workshop');
    const sessionId = resolveSessionId(action.label);
    const assistantMessageId = createWorkspaceMessageId('assistant-resource');
    updateSessionMessages(sessionId, (items) => [
      ...items,
      buildWorkspaceResourceTaskMessage({
        id: assistantMessageId,
        resourceLabel: action.label,
        resourceType: action.resource_type,
        resourceScope: 'course',
        courseBound: true,
        courseEvidenceRequired: true,
        taskStep: '排队中',
        createdAt: Date.now(),
      }),
    ]);
    useUiStore.getState().openResourcePreview({
      messageId: assistantMessageId,
      resourceType: action.resource_type,
      resourceTitle: action.label,
      prompt: action.reason,
    });

    try {
      const task = await mutateResource(buildSuggestedActionResourcePayload({
        courseId,
        conceptId: conceptIdForTask,
        pathNodeId: requestContext.path_node_id,
        action,
        clientContext: materialClientContext,
      }));
      setActiveTask({
        taskId: task.task_id,
        title: action.label,
        prompt: action.reason,
        resourceType: action.resource_type,
        messageId: assistantMessageId,
      });
      syncGenerationContext({
        taskId: task.task_id,
        concept: conceptIdForTask,
        type: action.resource_type,
        pathNode: requestContext.path_node_id ?? undefined,
      });
      const taskPatch = buildSubmittedResourceTaskPatch({
        id: assistantMessageId,
        task,
        resourceScope: 'course',
        isCourseMode: true,
        resourceEvidenceEnabled: true,
        resourceType: action.resource_type,
      });
      updateSessionMessages(sessionId, (items) =>
        upsertResourceTaskMessage(items, task.task_id, taskPatch),
      );
      if (taskPatch.taskStatus === 'failed') {
        const explained = explainTaskFailure(task.error_message, {
          hasCourse: true,
          errorCode: task.error_code,
          resourceType: action.resource_type,
        });
        onToast(explained.summary, 'error');
      } else {
        onToast('任务已进入队列', 'info');
      }
    } catch (error) {
      const explained = explainResourceError(error, {
        hasCourse: true,
        isUserMode: currentRole === 'student',
      });
      showResourceErrorToast(error, { hasCourse: true, isUserMode: currentRole === 'student' }, onToast);
      useUiStore.getState().openResourcePreview({
        messageId: assistantMessageId,
        resourceType: action.resource_type,
        resourceTitle: action.label,
        prompt: action.reason,
        localStatus: 'failed',
        localErrorMessage: explained.summary,
      });
      updateSessionMessages(sessionId, (items) =>
        items.map((item) =>
          item.id === assistantMessageId
            ? {
                ...item,
                variant: 'error',
                taskStatus: 'failed',
                content: formatErrorContent(explained),
              }
            : item,
        ),
      );
    }
  }, [
    clearSuggestedActions,
    courseId,
    currentRole,
    fallbackConceptId,
    isCourseMode,
    isSubmittingResource,
    materialClientContext,
    mutateResource,
    onToast,
    openSplitCanvas,
    requestContext.concept_id,
    requestContext.path_node_id,
    setActiveTask,
    syncGenerationContext,
    updateSessionMessages,
  ]);

  return {
    isSubmittingResource,
    submitResourceCommand,
    submitSuggestedResourceAction,
  };
}
