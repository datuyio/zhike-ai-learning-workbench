import { request, requestBlob } from './client';
import {
  adaptCourseProfileToLearningProfile,
  buildMockLearningProfileResponse,
  emptyLearningProfileResponse,
  mockActiveCourses,
  mockChatdocConfig,
  mockChatdocDocumentChunks,
  mockChatdocVendorQuota,
  mockClearModelProviderLogs,
  mockCourseBuilderOutline,
  mockCourseModelConfig,
  mockDeleteChatdocConfig,
  mockDeleteCourse,
  mockDeleteKnowledgeDocument,
  mockDemoAuthSession,
  mockGenerateCourseFromAI,
  mockKnowledgeDocumentsMerged,
  mockKnowledgeDocumentsScoped,
  mockKnowledgeIngestionStatus,
  mockKnowledgeUploadPolicy,
  mockListChatdocConfigInstances,
  mockModelProviderIcons,
  mockModelProviderLogs,
  mockModelProviderUsageStats,
  mockModelProviders,
  mockModelProviderTemplates,
  mockNativeChunks,
  mockPersonalSettingsSummary,
  mockPurgeDeletedCourse,
  mockRagIntegrationTemplates,
  mockRegisterChatdocInstance,
  mockResourceReviewWorkspace,
  mockRestoreCourse,
  mockDeletedCourses,
  mockSearchKnowledge,
  mockUpdateChatdocConfig,
  mockUpdateCourseModelConfig,
  mockUploadKnowledgeDocument,
  resolveDataMode,
  shouldUseMockData,
} from './mockAdapter';
import { authMock, learningMock, mockCourses } from '../mocks/fixtures';
import { readLocalJson, writeLocalJson } from '../utils/browser-storage';
import type {
  AssessmentResult,
  Citation,
  ChatResponse,
  Course,
  CourseBuilderOutline,
  CourseConcept,
  CourseConceptOutline,
  CourseOutlineImportResult,
  CourseOutlineSectionDraft,
  CourseReadiness,
  CourseProfile,
  CourseLearningProfile,
  LearningProfileResponse,
  LearningScheduleItem,
  LearningScheduleListResponse,
  MasterySummary,
  Metrics,
  ModelProviderHealth,
  ModelProviderLogFilters,
  ModelTraceDetail,
  ModelProviderPayload,
  ModelProviderTemplate,
  ModelProviderIcon,
  ProviderTestResult,
  ProviderCheckAllResult,
  ModelCallLogList,
  ModelCallLogClearResult,
  ModelProviderUsageStats,
  CourseModelConfig,
  CourseAiContext,
  ExtractedQaItem,
  IntentRouterEvalMetrics,
  IntentRouterValidationIssue,
  KnowledgeDocument,
  KnowledgeUploadPolicy,
  TaskEvent,
  IngestionStage,
  IngestionStatus,
  DocumentUploadResult,
  PathNode,
  PathNodeMastery,
  Resource,
  ResourceAsset,
  ResourceBatchDeleteResponse,
  ResourceGenerationStep,
  ResourceGenerationTask,
  ResourceHallResponse,
  ResourceReviewLog,
  ResourceReviewPayload,
  ResourceReviewStats,
  ResourceVersion,
  ResourceType,
  OutlineSectionPayload,
  OperationsDashboard,
  AnnouncementDetail,
  AnnouncementDisplayType,
  AnnouncementItem,
  AnnouncementListResponse,
  AnnouncementPayload,
  AnnouncementStats,
  AnnouncementSummaryResponse,
  LoginBackgroundMediaLibraryResponse,
  LoginBackgroundSettings,
  LoginBackgroundUploadResult,
  IntentRouterConfigView,
  IntentRouterEvalReport,
  IntentRouterRegistryConfig,
  IntentRouterValidationResult,
} from '../types';
import type { PresetChipSubmitRequest, PresetChipSubmitResponse } from '../types/onboarding';

export type SandboxExecuteResponse = {
  language: string;
  output: string;
  error: string;
  execution_time_ms: number;
};

export type ChatPayload = {
  course_id?: string | null;
  learning_scope?: 'general' | 'course';
  conversation_id?: string | null;
  message: string;
  concept_id?: string | null;
  path_node_id?: string | null;
  mode?: 'default_chat' | 'course_rag_qa';
  actionType?: 'chat' | 'resource_generation';
  resourceType?: string | null;
  uploadedDocId?: string | null;
  uploaded_doc_id?: string | null;
  needCourseEvidence?: boolean;
  clientContext?: Record<string, unknown>;
  response_mode?: 'stream' | 'json';
  require_citations?: boolean;
  auto_generate_resource?: boolean;
  preferred_resource_type?: string | null;
  intent_type?: string;
};

export type ResourceGeneratePayload = {
  scope?: 'course' | 'general';
  course_id?: string | null;
  concept_id?: string | null;
  path_node_id?: string | null;
  resource_type: ResourceType | string;
  difficulty: string;
  goal: string;
  requirements?: string;
  topic?: string | null;
  actionType?: 'resource_generation';
  needCourseEvidence?: boolean;
  clientContext?: Record<string, unknown>;
};

export type ResourceUploadPayload = {
  title: string;
  summary?: string;
  content?: string;
  resourceType: ResourceType | string;
  difficulty: string;
  courseId?: string | null;
  conceptId?: string | null;
  pathNodeId?: string | null;
  submitForReview?: boolean;
  file?: File | null;
};

export type AssessmentPayload = {
  course_id: string;
  concept_id: string;
  path_node_id?: string | null;
  assessment_type: string;
  answer: string;
  duration_seconds?: number;
};

export type AssessmentDraftPayload = {
  course_id: string;
  concept_id: string;
  path_node_id?: string | null;
  difficulty?: string;
  requirements?: string | null;
};

export type AssessmentDraftResponse = {
  title: string;
  content: string;
  course_id: string;
  concept_id: string;
  path_node_id?: string | null;
  source: string;
};

export type LearningSchedulePayload = {
  course_id?: string | null;
  concept_id?: string | null;
  path_node_id?: string | null;
  resource_id?: string | null;
  source_type?: string;
  source_id?: string | null;
  item_type?: string;
  title: string;
  description?: string | null;
  scheduled_date: string;
  time_label?: string | null;
  priority?: number;
  meta_json?: Record<string, unknown>;
};

export type LearningScheduleUpdatePayload = Partial<Pick<
  LearningSchedulePayload,
  'title' | 'description' | 'scheduled_date' | 'time_label' | 'priority' | 'meta_json'
>> & {
  status?: 'planned' | 'completed' | 'skipped';
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type RegisterPayload = {
  name: string;
  email: string;
  password: string;
  role?: 'student' | 'ta';
};

export type UpdateMePayload = {
  name: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    name: string;
    role: string;
    email?: string | null;
  };
};

export type CourseCreatePayload = {
  slug?: string;
  title: string;
  description?: string;
  applicable_major?: string;
  status?: string;
};

export type CourseGenerateFromAIPayload = {
  course_name: string;
  description?: string;
  section_limit?: number;
  concept_limit_per_section?: number;
};

export type CourseOutlineImportPayload = {
  source_path?: string;
  readme_text?: string;
  source_name?: string;
};

export type CourseOutlineApplyPayload = {
  mode: 'replace' | 'merge';
  course_title?: string;
  course_description?: string;
  sections: CourseOutlineSectionDraft[];
  rebuild_prerequisites?: boolean;
};

export type CourseUpdatePayload = {
  title?: string;
  description?: string;
  applicable_major?: string;
  status?: string;
};

export type CourseSectionPayload = {
  code?: string;
  title: string;
  description?: string;
  order_index?: number;
};

export type CourseConceptPayload = {
  code?: string;
  title: string;
  section_code?: string | null;
  section_title?: string;
  definition?: string;
  difficulty?: string;
  recommended_order?: number;
  prerequisites?: string[];
  status?: string;
};

export type LearningProfileParams = {
  courseId?: string | null;
  scope?: 'global' | 'course' | 'session' | 'cross_course' | 'all';
  courseTitle?: string | null;
  conversationId?: string | null;
};

export type ProfileCorrectionPayload = {
  scope: 'global' | 'course' | 'session' | 'cross_course';
  dimension_key: string;
  action?: 'update_dimension' | 'mark_inaccurate' | 'suppress_evidence' | 'clear_evidence';
  label?: string | null;
  summary?: string | null;
  score?: number | null;
  course_id?: string | null;
  conversation_id?: string | null;
  evidence_id?: string | null;
};

type ConversationHistoryItem = {
  conversation_id: string;
  title: string;
  updated_at: string;
  first_message_snippet?: string | null;
};

type ConversationHistoryResponse = {
  course_id: string;
  today_items: ConversationHistoryItem[];
  yesterday_items: ConversationHistoryItem[];
  older_items: ConversationHistoryItem[];
};

type ConversationMessagesResponse = {
  conversation_id: string;
  messages: Array<{
    id: string;
    role: string;
    content: string;
    created_at: string;
    meta_json?: Record<string, unknown>;
    citations?: Citation[];
  }>;
};

type KnowledgeSearchResponse = {
  course_id: string;
  query: string;
  mode?: string;
  retrieval_mode?: string;
  latency_ms?: number;
  wiki_filter_score?: number;
  items: Citation[];
  concept_filter_applied?: boolean;
  file_ids_count?: number;
  filter_reason?: string;
};

async function makeIdempotencyKey(scope: string, payload: unknown): Promise<string> {
  const text = `${scope}:${JSON.stringify(payload)}`;
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
  }
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  }
  return `${scope}-${Math.abs(hash).toString(16)}`;
}

const mockResourceTypeLabels: Record<string, string> = {
  lecture: '讲义',
  mindmap: '思维导图',
  quiz: '题库',
  misconception_card: '错题补救卡',
  ppt: 'PPT 大纲',
  code_lab: '代码实验',
  video: '视频脚本',
  reading: '拓展阅读',
  diagram_pack: '教学图解包',
};

const mockDifficultyLabels: Record<string, string> = {
  basic: '基础',
  medium: '中级',
  intermediate: '中级',
  advanced: '进阶',
};

const mockDeletedResourceIds = new Set<string>();
const mockUploadedResources: Resource[] = [];
const mockUploadedResourceVersions = new Map<string, ResourceVersion[]>();

function mockFixtureCourses(): Course[] {
  return mockCourses;
}

function mockFixtureConcepts(): CourseConcept[] {
  return learningMock.concepts;
}

function normalizePathNodeStatus(status: string): PathNode['status'] {
  if (status === 'mastered' || status === 'learning' || status === 'review' || status === 'not_started' || status === 'needs_remedial') {
    return status;
  }
  return 'not_started';
}

function mockFixturePathNodes(): PathNode[] {
  return learningMock.path.map((node) => ({
    ...node,
    status: normalizePathNodeStatus(node.status),
  }));
}

function buildMockMasterySummary(courseId: string): MasterySummary {
  return { ...learningMock.mastery, course_id: courseId };
}

function buildMockCourseProfile(courseId: string): CourseProfile {
  return { ...learningMock.profile, course_id: courseId };
}

function mockFixtureResources(): Resource[] {
  return learningMock.resources;
}

function mockFixtureResourceVersions(): ResourceVersion[] {
  return learningMock.resourceVersions;
}

function listMockResources(): Resource[] {
  return [...mockUploadedResources, ...mockFixtureResources()].filter((item) => !mockDeletedResourceIds.has(item.id));
}

function findMockResource(resourceId: string): Resource {
  const resource = listMockResources().find((item) => item.id === resourceId) ?? mockFixtureResources()[0];
  if (!resource) {
    throw new Error('Mock 资源数据为空，无法构造资源响应。');
  }
  return resource;
}

function listMockResourceVersions(resourceId: string): ResourceVersion[] {
  return mockUploadedResourceVersions.get(resourceId) ?? mockFixtureResourceVersions();
}

function buildMockResourceTask(taskId: string, patch: Partial<ResourceGenerationTask> = {}): ResourceGenerationTask {
  return {
    task_id: taskId,
    status: 'generating',
    resource_type: 'lecture',
    steps: [],
    ...patch,
  };
}

function buildMockResourceGenerationTask(payload: ResourceGeneratePayload): ResourceGenerationTask {
  return buildMockResourceTask(`mock-task-${Date.now()}`, {
    status: 'generating',
    course_id: payload.course_id,
    scope: payload.scope ?? (payload.course_id ? 'course' : 'general'),
    resource_type: payload.resource_type,
    difficulty: payload.difficulty,
    progress: 48,
    steps: [
      { name: '课程上下文确认', status: 'completed', detail: '已绑定当前课程与知识点' },
      { name: 'RAG 检索', status: 'completed', detail: '命中 5 个课程切片' },
      { name: 'WriterAgent · 资源正文生成', status: 'running', phase: 'generating', detail: '正在生成结构化内容' },
    ],
    message: 'mock generation started',
  });
}

function optionalString(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === 'string' ? value : undefined;
}

function optionalBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function optionalNumberArray(value: unknown): number[] | null | undefined {
  if (value === null) return null;
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'number' || !Number.isFinite(item))) {
    return undefined;
  }
  return value;
}

function parseCitation(value: unknown): Citation | null {
  if (
    !isRecord(value)
    || typeof value.similarity !== 'number'
    || !Number.isFinite(value.similarity)
    || typeof value.snippet !== 'string'
  ) {
    return null;
  }

  return {
    document_id: optionalString(value.document_id),
    source_id: typeof value.source_id === 'string' ? value.source_id : undefined,
    sourceTitle: typeof value.sourceTitle === 'string' ? value.sourceTitle : undefined,
    source_title: typeof value.source_title === 'string' ? value.source_title : undefined,
    pageNo: optionalNumber(value.pageNo),
    page_no: optionalNumber(value.page_no),
    iflytek_file_id: optionalString(value.iflytek_file_id),
    chunk_index: value.chunk_index === null ? null : optionalNumber(value.chunk_index),
    local_chunk_id: optionalString(value.local_chunk_id),
    provenance_source: optionalString(value.provenance_source),
    chunk_id: typeof value.chunk_id === 'string' ? value.chunk_id : undefined,
    kind: typeof value.kind === 'string' ? value.kind : undefined,
    page_asset_id: optionalString(value.page_asset_id),
    element_id: optionalString(value.element_id),
    asset_type: optionalString(value.asset_type),
    heading_path_text: optionalString(value.heading_path_text),
    heading_number: optionalString(value.heading_number),
    bbox: optionalNumberArray(value.bbox),
    bbox_norm: optionalNumberArray(value.bbox_norm),
    evidence_uri: optionalString(value.evidence_uri),
    section_path: optionalString(value.section_path),
    retrieval_mode: optionalString(value.retrieval_mode),
    similarity: value.similarity,
    snippet: value.snippet,
    content: optionalString(value.content),
  };
}

function parseCitationList(value: unknown): Citation[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const citation = parseCitation(item);
    return citation ? [citation] : [];
  }) : [];
}

function parseResourceGenerationStep(value: unknown): ResourceGenerationStep | string | null {
  if (typeof value === 'string') {
    return value;
  }
  if (!isRecord(value) || typeof value.name !== 'string' || typeof value.status !== 'string') {
    return null;
  }
  return {
    name: value.name,
    status: value.status,
    detail: optionalString(value.detail),
    phase: optionalString(value.phase),
    citations: parseCitationList(value.citations),
  };
}

function parseResourceGenerationSteps(value: unknown): ResourceGenerationTask['steps'] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const step = parseResourceGenerationStep(item);
    return step ? [step] : [];
  }) : [];
}

function parseOutlineSectionPayload(value: unknown): OutlineSectionPayload | null {
  if (
    !isRecord(value)
    || typeof value.id !== 'string'
    || typeof value.level !== 'number'
    || !Number.isFinite(value.level)
    || typeof value.title !== 'string'
    || typeof value.order !== 'number'
    || !Number.isFinite(value.order)
  ) {
    return null;
  }
  return {
    id: value.id,
    level: value.level,
    title: value.title,
    order: value.order,
  };
}

function parseOutlineSections(value: unknown): OutlineSectionPayload[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const section = parseOutlineSectionPayload(item);
    return section ? [section] : [];
  }) : [];
}

function parseResourceAsset(value: unknown): ResourceAsset | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.title !== 'string' || typeof value.status !== 'string') {
    return null;
  }

  return {
    id: value.id,
    diagram_type: optionalString(value.diagram_type),
    title: value.title,
    file_url: optionalString(value.file_url),
    width: value.width === null ? null : optionalNumber(value.width),
    height: value.height === null ? null : optionalNumber(value.height),
    mime_type: optionalString(value.mime_type),
    prompt: optionalString(value.prompt),
    revised_prompt: optionalString(value.revised_prompt),
    provider: optionalString(value.provider),
    model: optionalString(value.model),
    status: value.status,
    raw_params: isRecord(value.raw_params) ? value.raw_params : undefined,
  };
}

function parseResourceAssets(value: unknown): ResourceAsset[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const asset = parseResourceAsset(item);
    return asset ? [asset] : [];
  }) : [];
}

export function parseAuthUser(payload: unknown): AuthResponse['user'] {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.name !== 'string'
    || typeof payload.role !== 'string'
    || (payload.email !== undefined && payload.email !== null && typeof payload.email !== 'string')
  ) {
    throw new Error('认证用户响应缺少核心字段');
  }
  return {
    id: payload.id,
    name: payload.name,
    role: payload.role,
    email: payload.email === null ? null : optionalString(payload.email),
  };
}

export function parseAuthResponse(payload: unknown): AuthResponse {
  if (
    !isRecord(payload)
    || typeof payload.access_token !== 'string'
    || typeof payload.token_type !== 'string'
  ) {
    throw new Error('认证响应缺少 token 字段');
  }
  return {
    access_token: payload.access_token,
    token_type: payload.token_type,
    user: parseAuthUser(payload.user),
  };
}

export function parseCurrentUserResponse(payload: unknown): { user: AuthResponse['user'] } {
  if (!isRecord(payload)) {
    throw new Error('当前用户响应不是对象');
  }
  return {
    user: parseAuthUser(payload.user),
  };
}

export function parseCourse(payload: unknown): Course {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.title !== 'string'
    || typeof payload.description !== 'string'
    || typeof payload.status !== 'string'
  ) {
    throw new Error('课程响应缺少核心字段');
  }
  return {
    id: payload.id,
    title: payload.title,
    description: payload.description,
    status: payload.status,
    applicable_major: optionalString(payload.applicable_major),
    display_config: isRecord(payload.display_config) ? payload.display_config : {},
    deleted_at: optionalString(payload.deleted_at),
  };
}

export function parseCourseListResponse(payload: unknown): { items: Course[] } {
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new Error('课程列表响应结构无效');
  }
  return {
    items: payload.items.map(parseCourse),
  };
}

export function parseUserCourseListResponse(payload: unknown): { user: string; items: Course[] } {
  if (!isRecord(payload) || typeof payload.user !== 'string' || !Array.isArray(payload.items)) {
    throw new Error('用户课程列表响应结构无效');
  }
  return {
    user: payload.user,
    items: payload.items.map(parseCourse),
  };
}

export function parseCurrentCourseResponse(payload: unknown): { course_id: string | null } {
  if (!isRecord(payload)) {
    throw new Error('当前课程响应不是对象');
  }
  const courseId = optionalString(payload.course_id);
  if (courseId === undefined) {
    throw new Error('当前课程响应缺少 course_id 字段');
  }
  return {
    course_id: courseId,
  };
}

export function parseCurrentCourseUpdateResponse(payload: unknown): { course_id: string; message: string } {
  if (!isRecord(payload) || typeof payload.message !== 'string') {
    throw new Error('当前课程更新响应缺少 message 字段');
  }
  const parsed = parseCurrentCourseResponse(payload);
  if (typeof parsed.course_id !== 'string') {
    throw new Error('当前课程更新响应缺少 course_id 字段');
  }
  return {
    course_id: parsed.course_id,
    message: payload.message,
  };
}

export function parseCourseMutationResponse(payload: unknown): { status: string; course: Course; course_id?: string | null } {
  if (!isRecord(payload) || typeof payload.status !== 'string') {
    throw new Error('课程变更响应缺少 status 字段');
  }
  const courseId = optionalString(payload.course_id);
  return {
    status: payload.status,
    course: parseCourse(payload.course),
    course_id: courseId,
  };
}

export function parseCourseUpdateResponse(payload: unknown): { status: string; course_id: string; course: Course } {
  const parsed = parseCourseMutationResponse(payload);
  if (typeof parsed.course_id !== 'string') {
    throw new Error('课程更新响应缺少 course_id 字段');
  }
  return {
    status: parsed.status,
    course_id: parsed.course_id,
    course: parsed.course,
  };
}

function isPathNodeStatus(value: unknown): value is PathNode['status'] {
  return value === 'mastered'
    || value === 'learning'
    || value === 'review'
    || value === 'not_started'
    || value === 'needs_remedial';
}

function parsePathPrerequisiteEdge(value: unknown): NonNullable<PathNode['prerequisite_edges']>[number] | null {
  if (!isRecord(value) || typeof value.id !== 'string') {
    return null;
  }
  return {
    id: value.id,
    dependency_type: typeof value.dependency_type === 'string' ? value.dependency_type : 'strong',
  };
}

function parsePathPrerequisiteEdges(value: unknown): NonNullable<PathNode['prerequisite_edges']> {
  return Array.isArray(value) ? value.flatMap((item) => {
    const edge = parsePathPrerequisiteEdge(item);
    return edge ? [edge] : [];
  }) : [];
}

export function parsePathNode(payload: unknown): PathNode {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.title !== 'string'
    || typeof payload.mastery !== 'number'
    || !Number.isFinite(payload.mastery)
    || !isPathNodeStatus(payload.status)
  ) {
    throw new Error('学习路径节点响应缺少核心字段');
  }
  const masteryScore = optionalNumber(payload.mastery_score);
  return {
    id: payload.id,
    course_id: optionalString(payload.course_id),
    concept_id: optionalString(payload.concept_id),
    concept_name: optionalString(payload.concept_name),
    title: payload.title,
    mastery: payload.mastery,
    ...(masteryScore === undefined ? {} : { mastery_score: masteryScore }),
    status: payload.status,
    is_remedial: typeof payload.is_remedial === 'boolean' ? payload.is_remedial : undefined,
    isRemedial: typeof payload.isRemedial === 'boolean' ? payload.isRemedial : undefined,
    is_remediation: typeof payload.is_remediation === 'boolean' ? payload.is_remediation : undefined,
    sequence_index: optionalNumber(payload.sequence_index),
    remediate_for_concept_id: optionalString(payload.remediate_for_concept_id),
    prerequisites: isStringArray(payload.prerequisites) ? payload.prerequisites : [],
    prerequisite_edges: parsePathPrerequisiteEdges(payload.prerequisite_edges),
    recommendation: isRecord(payload.recommendation) ? payload.recommendation : {},
    evidence: Array.isArray(payload.evidence) ? payload.evidence.filter(isRecord) : [],
    updated_at: optionalString(payload.updated_at),
  };
}

export function parseLearningPathResponse(payload: unknown): { course_id: string; items: PathNode[] } {
  if (!isRecord(payload) || typeof payload.course_id !== 'string' || !Array.isArray(payload.items)) {
    throw new Error('学习路径响应结构无效');
  }
  return {
    course_id: payload.course_id,
    items: payload.items.map(parsePathNode),
  };
}

export function parseLearningPathGenerateResponse(payload: unknown): { course_id: string; status: string; items: PathNode[] } {
  if (!isRecord(payload) || typeof payload.status !== 'string') {
    throw new Error('学习路径生成响应缺少 status 字段');
  }
  return {
    ...parseLearningPathResponse(payload),
    status: payload.status,
  };
}

export function parsePathNodeStatusResponse(payload: unknown): { node_id: string; status: string; mastery_score?: number } {
  if (!isRecord(payload) || typeof payload.node_id !== 'string' || !isPathNodeStatus(payload.status)) {
    throw new Error('学习路径节点状态响应结构无效');
  }
  return {
    node_id: payload.node_id,
    status: payload.status,
    mastery_score: optionalNumber(payload.mastery_score),
  };
}

export function parsePathNodeMastery(payload: unknown): PathNodeMastery {
  if (
    !isRecord(payload)
    || typeof payload.node_id !== 'string'
    || typeof payload.title !== 'string'
    || typeof payload.mastery !== 'number'
    || !Number.isFinite(payload.mastery)
    || !isPathNodeStatus(payload.status)
  ) {
    throw new Error('学习路径节点掌握度响应结构无效');
  }
  const masteryScore = optionalNumber(payload.mastery_score) ?? payload.mastery;
  return {
    node_id: payload.node_id,
    course_id: optionalString(payload.course_id),
    concept_id: optionalString(payload.concept_id),
    title: payload.title,
    status: payload.status,
    mastery: payload.mastery,
    mastery_score: masteryScore,
    is_remedial: typeof payload.is_remedial === 'boolean' ? payload.is_remedial : undefined,
    evidence: Array.isArray(payload.evidence) ? payload.evidence.filter(isRecord) : [],
    updated_at: optionalString(payload.updated_at),
  };
}

function parseNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const entries = Object.entries(value).filter((entry): entry is [string, number] => (
    typeof entry[1] === 'number' && Number.isFinite(entry[1])
  ));
  return Object.fromEntries(entries);
}

export function parseKnowledgeDocument(payload: unknown): KnowledgeDocument {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.title !== 'string'
    || typeof payload.filename !== 'string'
    || typeof payload.parse_status !== 'string'
    || typeof payload.vector_status !== 'string'
    || typeof payload.chunk_count !== 'number'
    || !Number.isFinite(payload.chunk_count)
  ) {
    throw new Error('知识库文档响应缺少核心字段');
  }
  return {
    id: payload.id,
    title: payload.title,
    filename: payload.filename,
    mime_type: optionalString(payload.mime_type),
    parse_status: payload.parse_status,
    vector_status: payload.vector_status,
    text_vector_status: optionalString(payload.text_vector_status),
    visual_vector_status: optionalString(payload.visual_vector_status),
    review_status: optionalString(payload.review_status),
    publish_readiness: optionalString(payload.publish_readiness),
    chunk_count: payload.chunk_count,
    page_count: optionalNumber(payload.page_count),
    source_type: optionalString(payload.source_type),
    created_at: optionalString(payload.created_at),
    updated_at: optionalString(payload.updated_at),
    embedding_model: optionalString(payload.embedding_model),
    embedding_status: optionalString(payload.embedding_status),
    parser_version: optionalString(payload.parser_version),
    chunker_version: optionalString(payload.chunker_version),
    iflytek_file_id: optionalString(payload.iflytek_file_id),
    iflytek_repo_id: optionalString(payload.iflytek_repo_id),
    chatdoc_sid: optionalString(payload.chatdoc_sid),
    chatdoc_file_status: optionalString(payload.chatdoc_file_status),
    cloud_status: optionalString(payload.cloud_status),
    awaiting_activation: optionalBoolean(payload.awaiting_activation),
    chatdoc_step_by_step: payload.chatdoc_step_by_step === null ? null : optionalBoolean(payload.chatdoc_step_by_step),
    parse_type: optionalString(payload.parse_type),
    chatdoc_error: optionalString(payload.chatdoc_error),
    last_synced_at: optionalString(payload.last_synced_at),
    ingestion_duration_ms: payload.ingestion_duration_ms === null ? null : optionalNumber(payload.ingestion_duration_ms),
    native_chunks_synced_at: optionalString(payload.native_chunks_synced_at),
    local_native_chunk_count: optionalNumber(payload.local_native_chunk_count),
    rag_backend: optionalString(payload.rag_backend),
    course_id: optionalString(payload.course_id),
    course_title: optionalString(payload.course_title),
    duplicate_of: optionalString(payload.duplicate_of),
  };
}

export function parseKnowledgeDocumentListResponse(payload: unknown): { course_id: string; iflytek_repo_id?: string | null; items: KnowledgeDocument[] } {
  if (!isRecord(payload) || typeof payload.course_id !== 'string' || !Array.isArray(payload.items)) {
    throw new Error('知识库文档列表响应结构无效');
  }
  return {
    course_id: payload.course_id,
    iflytek_repo_id: optionalString(payload.iflytek_repo_id),
    items: payload.items.map(parseKnowledgeDocument),
  };
}

export function parseKnowledgeDocumentScopedListResponse(payload: unknown): {
  scope: 'all' | 'course';
  course_id?: string | null;
  course_title?: string | null;
  total: number;
  items: KnowledgeDocument[];
} {
  if (
    !isRecord(payload)
    || (payload.scope !== 'all' && payload.scope !== 'course')
    || typeof payload.total !== 'number'
    || !Number.isFinite(payload.total)
    || !Array.isArray(payload.items)
  ) {
    throw new Error('知识库文档范围列表响应结构无效');
  }
  return {
    scope: payload.scope,
    course_id: optionalString(payload.course_id),
    course_title: optionalString(payload.course_title),
    total: payload.total,
    items: payload.items.map(parseKnowledgeDocument),
  };
}

export function parseKnowledgeUploadPolicy(payload: unknown): KnowledgeUploadPolicy {
  if (
    !isRecord(payload)
    || typeof payload.max_upload_bytes !== 'number'
    || !Number.isFinite(payload.max_upload_bytes)
    || !isStringArray(payload.allowed_extensions)
    || !isStringArray(payload.allowed_mime_types)
    || typeof payload.block_duplicate_upload !== 'boolean'
    || typeof payload.block_duplicate_filename !== 'boolean'
    || typeof payload.upload_timeout_seconds !== 'number'
    || !Number.isFinite(payload.upload_timeout_seconds)
    || typeof payload.rag_backend !== 'string'
  ) {
    throw new Error('知识库上传策略响应结构无效');
  }
  return {
    max_upload_bytes: payload.max_upload_bytes,
    allowed_extensions: payload.allowed_extensions,
    allowed_mime_types: payload.allowed_mime_types,
    block_duplicate_upload: payload.block_duplicate_upload,
    block_duplicate_filename: payload.block_duplicate_filename,
    upload_timeout_seconds: payload.upload_timeout_seconds,
    rag_backend: payload.rag_backend,
  };
}

export function parseDocumentUploadResult(payload: unknown): DocumentUploadResult {
  if (
    !isRecord(payload)
    || typeof payload.document_id !== 'string'
    || typeof payload.course_id !== 'string'
    || typeof payload.filename !== 'string'
    || typeof payload.parse_status !== 'string'
    || typeof payload.vector_status !== 'string'
  ) {
    throw new Error('知识库文档上传响应缺少核心字段');
  }
  return {
    document_id: payload.document_id,
    course_id: payload.course_id,
    course_title: optionalString(payload.course_title),
    filename: payload.filename,
    parse_status: payload.parse_status,
    vector_status: payload.vector_status,
    review_status: optionalString(payload.review_status),
    publish_readiness: optionalString(payload.publish_readiness),
    chunk_count: optionalNumber(payload.chunk_count),
    page_count: optionalNumber(payload.page_count),
    embedding_model: typeof payload.embedding_model === 'string' ? payload.embedding_model : undefined,
    embedding_status: typeof payload.embedding_status === 'string' ? payload.embedding_status : undefined,
    message: optionalString(payload.message),
    duplicate_of: optionalString(payload.duplicate_of),
    rag_backend: optionalString(payload.rag_backend),
    iflytek_file_id: optionalString(payload.iflytek_file_id),
    iflytek_repo_id: optionalString(payload.iflytek_repo_id),
    cloud_status: optionalString(payload.cloud_status),
    step_by_step: payload.step_by_step === null ? null : optionalBoolean(payload.step_by_step),
    awaiting_activation: payload.awaiting_activation === null ? null : optionalBoolean(payload.awaiting_activation),
  };
}

function parseIngestionTaskEvent(payload: unknown): TaskEvent | null {
  if (
    !isRecord(payload)
    || typeof payload.event_id !== 'string'
    || typeof payload.task_id !== 'string'
    || typeof payload.task_type !== 'string'
    || typeof payload.stage !== 'string'
    || typeof payload.status !== 'string'
  ) {
    return null;
  }
  return {
    event_id: payload.event_id,
    task_id: payload.task_id,
    task_type: payload.task_type,
    stage: payload.stage,
    status: payload.status,
    message: optionalString(payload.message),
    worker_id: optionalString(payload.worker_id),
    trace_id: optionalString(payload.trace_id),
    metrics: payload.metrics === null ? null : (isRecord(payload.metrics) ? payload.metrics : undefined),
    created_at: optionalString(payload.created_at),
  };
}

function parseIngestionStage(payload: unknown): IngestionStage | null {
  if (
    !isRecord(payload)
    || typeof payload.name !== 'string'
    || typeof payload.status !== 'string'
    || typeof payload.progress !== 'number'
    || !Number.isFinite(payload.progress)
  ) {
    return null;
  }
  return {
    name: payload.name,
    status: payload.status,
    progress: payload.progress,
    meta: isRecord(payload.meta) ? payload.meta : undefined,
  };
}

export function parseIngestionStatus(payload: unknown): IngestionStatus {
  if (
    !isRecord(payload)
    || typeof payload.document_id !== 'string'
    || typeof payload.status !== 'string'
    || !Array.isArray(payload.stages)
  ) {
    throw new Error('知识库入库状态响应缺少核心字段');
  }
  return {
    document_id: payload.document_id,
    task_id: optionalString(payload.task_id),
    stage: optionalString(payload.stage),
    attempt_count: optionalNumber(payload.attempt_count),
    max_attempts: optionalNumber(payload.max_attempts),
    worker_id: optionalString(payload.worker_id),
    trace_id: optionalString(payload.trace_id),
    locked_at: optionalString(payload.locked_at),
    heartbeat_at: optionalString(payload.heartbeat_at),
    next_retry_at: optionalString(payload.next_retry_at),
    started_at: optionalString(payload.started_at),
    finished_at: optionalString(payload.finished_at),
    status: payload.status,
    progress: optionalNumber(payload.progress),
    parse_status: typeof payload.parse_status === 'string' ? payload.parse_status : undefined,
    vector_status: typeof payload.vector_status === 'string' ? payload.vector_status : undefined,
    awaiting_activation: optionalBoolean(payload.awaiting_activation),
    cloud_status: optionalString(payload.cloud_status),
    local_native_chunk_count: optionalNumber(payload.local_native_chunk_count),
    error: optionalString(payload.error),
    result: isRecord(payload.result) ? payload.result : undefined,
    asset_type_counts: parseNumberRecord(payload.asset_type_counts),
    token_total: optionalNumber(payload.token_total),
    average_tokens: optionalNumber(payload.average_tokens),
    partial_chunks: optionalNumber(payload.partial_chunks),
    isolated_output_chunks: optionalNumber(payload.isolated_output_chunks),
    events: Array.isArray(payload.events)
      ? payload.events.flatMap((item) => {
        const event = parseIngestionTaskEvent(item);
        return event ? [event] : [];
      })
      : [],
    stages: payload.stages.flatMap((item) => {
      const stage = parseIngestionStage(item);
      return stage ? [stage] : [];
    }),
  };
}

export function parseCoursesWithKnowledgeResponse(payload: unknown): { course_ids: string[] } {
  if (!isRecord(payload) || !isStringArray(payload.course_ids)) {
    throw new Error('知识库课程列表响应结构无效');
  }
  return {
    course_ids: payload.course_ids,
  };
}

export function parseKnowledgeDocumentActionResponse(payload: unknown): {
  status: string;
  document_id: string;
  title?: string | null;
  filename?: string | null;
  chatdoc?: Record<string, unknown>;
  cleanup?: Record<string, unknown>;
} {
  if (!isRecord(payload) || typeof payload.status !== 'string' || typeof payload.document_id !== 'string') {
    throw new Error('知识库文档操作响应缺少核心字段');
  }
  return {
    status: payload.status,
    document_id: payload.document_id,
    title: optionalString(payload.title),
    filename: optionalString(payload.filename),
    chatdoc: isRecord(payload.chatdoc) ? payload.chatdoc : undefined,
    cleanup: isRecord(payload.cleanup) ? payload.cleanup : undefined,
  };
}

export function parseRecycledKnowledgeDocumentListResponse(payload: unknown): { total: number; items: KnowledgeDocument[] } {
  if (!isRecord(payload) || typeof payload.total !== 'number' || !Number.isFinite(payload.total) || !Array.isArray(payload.items)) {
    throw new Error('知识库回收站列表响应结构无效');
  }
  return {
    total: payload.total,
    items: payload.items.map(parseKnowledgeDocument),
  };
}

export function parseKnowledgeSearchResponse(payload: unknown): KnowledgeSearchResponse {
  if (
    !isRecord(payload)
    || typeof payload.course_id !== 'string'
    || typeof payload.query !== 'string'
    || typeof payload.retrieval_mode !== 'string'
    || typeof payload.latency_ms !== 'number'
    || !Number.isFinite(payload.latency_ms)
    || !Array.isArray(payload.items)
  ) {
    throw new Error('知识库检索响应缺少核心字段');
  }
  return {
    course_id: payload.course_id,
    query: payload.query,
    mode: typeof payload.mode === 'string' ? payload.mode : undefined,
    retrieval_mode: payload.retrieval_mode,
    latency_ms: payload.latency_ms,
    wiki_filter_score: optionalNumber(payload.wiki_filter_score),
    items: parseCitationList(payload.items),
    concept_filter_applied: optionalBoolean(payload.concept_filter_applied),
    file_ids_count: optionalNumber(payload.file_ids_count),
    filter_reason: typeof payload.filter_reason === 'string' ? payload.filter_reason : undefined,
  };
}

function requiredFiniteNumber(value: unknown, message: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(message);
  }
  return value;
}

function optionalRecord(value: unknown): Record<string, unknown> | undefined {
  return isRecord(value) ? value : undefined;
}

export function parseModelProviderHealth(payload: unknown): ModelProviderHealth {
  if (
    !isRecord(payload)
    || typeof payload.provider !== 'string'
    || typeof payload.display_name !== 'string'
    || typeof payload.status !== 'string'
  ) {
    throw new Error('模型供应商健康响应缺少核心字段');
  }
  return {
    provider: payload.provider,
    display_name: payload.display_name,
    provider_type: typeof payload.provider_type === 'string' ? payload.provider_type : undefined,
    status: payload.status,
    priority: requiredFiniteNumber(payload.priority, '模型供应商健康响应缺少 priority 字段'),
    is_active: optionalBoolean(payload.is_active),
    is_default: optionalBoolean(payload.is_default),
    chat_model: optionalString(payload.chat_model),
    embedding_model: optionalString(payload.embedding_model),
    image_model: optionalString(payload.image_model),
    embedding_dimension: payload.embedding_dimension === null ? null : optionalNumber(payload.embedding_dimension),
    max_batch_size: optionalNumber(payload.max_batch_size),
    rate_limit_rps: payload.rate_limit_rps === null ? null : optionalNumber(payload.rate_limit_rps),
    supports_stream: optionalBoolean(payload.supports_stream),
    supports_tool_call: optionalBoolean(payload.supports_tool_call),
    supports_json_mode: optionalBoolean(payload.supports_json_mode),
    key_configured: optionalBoolean(payload.key_configured),
    key_source: typeof payload.key_source === 'string' ? payload.key_source : undefined,
    key_masked: optionalString(payload.key_masked),
    base_url: optionalString(payload.base_url),
    protocol: typeof payload.protocol === 'string' ? payload.protocol : undefined,
    last_checked_at: optionalString(payload.last_checked_at),
    last_error: optionalString(payload.last_error),
    avg_latency_ms: payload.avg_latency_ms === null ? null : optionalNumber(payload.avg_latency_ms),
    consecutive_failures: optionalNumber(payload.consecutive_failures),
    daily_limit: payload.daily_limit === null ? null : optionalNumber(payload.daily_limit),
    cost_config_json: optionalRecord(payload.cost_config_json),
    meta_json: optionalRecord(payload.meta_json),
  };
}

export function parseModelProviderHealthResponse(payload: unknown): { items: ModelProviderHealth[] } {
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new Error('模型供应商健康列表响应结构无效');
  }
  return {
    items: payload.items.map(parseModelProviderHealth),
  };
}

function parseModelCallLogSummary(payload: unknown): ModelCallLogList['summary'] {
  if (!isRecord(payload)) {
    throw new Error('模型调用日志汇总响应结构无效');
  }
  return {
    total_calls: requiredFiniteNumber(payload.total_calls, '模型调用日志汇总缺少 total_calls 字段'),
    failed_calls: requiredFiniteNumber(payload.failed_calls, '模型调用日志汇总缺少 failed_calls 字段'),
    failure_rate: requiredFiniteNumber(payload.failure_rate, '模型调用日志汇总缺少 failure_rate 字段'),
    avg_latency_ms: requiredFiniteNumber(payload.avg_latency_ms, '模型调用日志汇总缺少 avg_latency_ms 字段'),
    request_count: requiredFiniteNumber(payload.request_count, '模型调用日志汇总缺少 request_count 字段'),
    token_input: requiredFiniteNumber(payload.token_input, '模型调用日志汇总缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型调用日志汇总缺少 token_output 字段'),
    estimated_cost: requiredFiniteNumber(payload.estimated_cost, '模型调用日志汇总缺少 estimated_cost 字段'),
  };
}

function parseModelCallLogItem(payload: unknown): ModelCallLogList['items'][number] {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.provider !== 'string'
    || typeof payload.display_name !== 'string'
    || typeof payload.capability !== 'string'
    || typeof payload.status !== 'string'
  ) {
    throw new Error('模型调用日志响应缺少核心字段');
  }
  return {
    id: payload.id,
    provider: payload.provider,
    display_name: payload.display_name,
    course_id: optionalString(payload.course_id),
    course_slug: optionalString(payload.course_slug),
    course_title: optionalString(payload.course_title),
    model_name: optionalString(payload.model_name),
    capability: payload.capability,
    request_count: requiredFiniteNumber(payload.request_count, '模型调用日志响应缺少 request_count 字段'),
    batch_count: requiredFiniteNumber(payload.batch_count, '模型调用日志响应缺少 batch_count 字段'),
    embedding_dim: payload.embedding_dim === null ? null : optionalNumber(payload.embedding_dim),
    token_input: requiredFiniteNumber(payload.token_input, '模型调用日志响应缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型调用日志响应缺少 token_output 字段'),
    latency_ms: requiredFiniteNumber(payload.latency_ms, '模型调用日志响应缺少 latency_ms 字段'),
    status: payload.status,
    error_message: optionalString(payload.error_message),
    meta_json: optionalRecord(payload.meta_json),
    trace_id: optionalString(payload.trace_id),
    estimated_cost: optionalNumber(payload.estimated_cost),
    created_at: optionalString(payload.created_at),
  };
}

export function parseModelCallLogListResponse(payload: unknown): ModelCallLogList {
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new Error('模型调用日志列表响应结构无效');
  }
  const range = isRecord(payload.range)
    && typeof payload.range.start_at === 'string'
    && typeof payload.range.end_at === 'string'
    ? { start_at: payload.range.start_at, end_at: payload.range.end_at }
    : undefined;
  return {
    range,
    summary: parseModelCallLogSummary(payload.summary),
    items: payload.items.map(parseModelCallLogItem),
  };
}

function parseModelTraceCall(payload: unknown): ModelTraceDetail['model_calls'][number] {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.provider !== 'string'
    || typeof payload.display_name !== 'string'
    || typeof payload.capability !== 'string'
    || typeof payload.status !== 'string'
  ) {
    throw new Error('模型调用链路响应缺少模型调用核心字段');
  }
  return {
    id: payload.id,
    created_at: optionalString(payload.created_at),
    provider: payload.provider,
    display_name: payload.display_name,
    model_name: optionalString(payload.model_name),
    capability: payload.capability,
    status: payload.status,
    latency_ms: requiredFiniteNumber(payload.latency_ms, '模型调用链路响应缺少 latency_ms 字段'),
    token_input: requiredFiniteNumber(payload.token_input, '模型调用链路响应缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型调用链路响应缺少 token_output 字段'),
    estimated_cost: requiredFiniteNumber(payload.estimated_cost, '模型调用链路响应缺少 estimated_cost 字段'),
    error_message: optionalString(payload.error_message),
    course_slug: optionalString(payload.course_slug),
    course_title: optionalString(payload.course_title),
    meta_json: optionalRecord(payload.meta_json),
  };
}

function parseModelTraceRagQuery(payload: unknown): ModelTraceDetail['rag_queries'][number] {
  if (
    !isRecord(payload)
    || typeof payload.id !== 'string'
    || typeof payload.intent !== 'string'
    || typeof payload.hit !== 'boolean'
    || typeof payload.refused !== 'boolean'
  ) {
    throw new Error('模型调用链路响应缺少 RAG 查询核心字段');
  }
  return {
    id: payload.id,
    created_at: optionalString(payload.created_at),
    course_slug: optionalString(payload.course_slug),
    course_title: optionalString(payload.course_title),
    intent: payload.intent,
    hit: payload.hit,
    top_score: requiredFiniteNumber(payload.top_score, '模型调用链路响应缺少 top_score 字段'),
    citation_count: requiredFiniteNumber(payload.citation_count, '模型调用链路响应缺少 citation_count 字段'),
    refused: payload.refused,
    latency_ms: requiredFiniteNumber(payload.latency_ms, '模型调用链路响应缺少 RAG latency_ms 字段'),
    query_text: optionalString(payload.query_text),
    meta_json: optionalRecord(payload.meta_json),
  };
}

function parseModelTraceAdminAudit(payload: unknown): ModelTraceDetail['admin_audits'][number] {
  if (!isRecord(payload) || typeof payload.id !== 'string' || typeof payload.action !== 'string') {
    throw new Error('模型调用链路响应缺少审计核心字段');
  }
  return {
    id: payload.id,
    created_at: optionalString(payload.created_at),
    action: payload.action,
    target_type: optionalString(payload.target_type),
    target_id: optionalString(payload.target_id),
    detail_json: optionalRecord(payload.detail_json),
  };
}

export function parseModelTraceDetailResponse(payload: unknown): ModelTraceDetail {
  if (
    !isRecord(payload)
    || typeof payload.trace_id !== 'string'
    || !Array.isArray(payload.model_calls)
    || !Array.isArray(payload.rag_queries)
    || !Array.isArray(payload.admin_audits)
  ) {
    throw new Error('模型调用链路详情响应结构无效');
  }
  return {
    trace_id: payload.trace_id,
    model_calls: payload.model_calls.map(parseModelTraceCall),
    rag_queries: payload.rag_queries.map(parseModelTraceRagQuery),
    admin_audits: payload.admin_audits.map(parseModelTraceAdminAudit),
  };
}

function parseModelProviderUsageSummary(payload: unknown): ModelProviderUsageStats['summary'] {
  if (!isRecord(payload)) {
    throw new Error('模型供应商用量摘要响应结构无效');
  }
  return {
    total_calls: requiredFiniteNumber(payload.total_calls, '模型供应商用量摘要缺少 total_calls 字段'),
    failed_calls: requiredFiniteNumber(payload.failed_calls, '模型供应商用量摘要缺少 failed_calls 字段'),
    failure_rate: requiredFiniteNumber(payload.failure_rate, '模型供应商用量摘要缺少 failure_rate 字段'),
    token_input: requiredFiniteNumber(payload.token_input, '模型供应商用量摘要缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型供应商用量摘要缺少 token_output 字段'),
    estimated_cost: requiredFiniteNumber(payload.estimated_cost, '模型供应商用量摘要缺少 estimated_cost 字段'),
  };
}

function parseModelProviderUsageItem(payload: unknown): ModelProviderUsageStats['items'][number] {
  if (!isRecord(payload) || typeof payload.provider !== 'string' || typeof payload.display_name !== 'string') {
    throw new Error('模型供应商用量列表项缺少核心字段');
  }
  return {
    provider: payload.provider,
    display_name: payload.display_name,
    total_calls: requiredFiniteNumber(payload.total_calls, '模型供应商用量列表项缺少 total_calls 字段'),
    failed_calls: requiredFiniteNumber(payload.failed_calls, '模型供应商用量列表项缺少 failed_calls 字段'),
    failure_rate: requiredFiniteNumber(payload.failure_rate, '模型供应商用量列表项缺少 failure_rate 字段'),
    avg_latency_ms: requiredFiniteNumber(payload.avg_latency_ms, '模型供应商用量列表项缺少 avg_latency_ms 字段'),
    token_input: requiredFiniteNumber(payload.token_input, '模型供应商用量列表项缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型供应商用量列表项缺少 token_output 字段'),
    request_count: requiredFiniteNumber(payload.request_count, '模型供应商用量列表项缺少 request_count 字段'),
    estimated_cost: requiredFiniteNumber(payload.estimated_cost, '模型供应商用量列表项缺少 estimated_cost 字段'),
  };
}

function parseModelProviderUsageTrend(payload: unknown): ModelProviderUsageStats['cost_trends'][number] {
  if (!isRecord(payload) || typeof payload.date !== 'string') {
    throw new Error('模型供应商用量趋势项缺少日期字段');
  }
  return {
    date: payload.date,
    calls: requiredFiniteNumber(payload.calls, '模型供应商用量趋势项缺少 calls 字段'),
    token_input: requiredFiniteNumber(payload.token_input, '模型供应商用量趋势项缺少 token_input 字段'),
    token_output: requiredFiniteNumber(payload.token_output, '模型供应商用量趋势项缺少 token_output 字段'),
    estimated_cost: requiredFiniteNumber(payload.estimated_cost, '模型供应商用量趋势项缺少 estimated_cost 字段'),
  };
}

export function parseModelProviderUsageStatsResponse(payload: unknown): ModelProviderUsageStats {
  if (!isRecord(payload) || !Array.isArray(payload.items) || !Array.isArray(payload.cost_trends)) {
    throw new Error('模型供应商用量统计响应结构无效');
  }
  return {
    summary: parseModelProviderUsageSummary(payload.summary),
    items: payload.items.map(parseModelProviderUsageItem),
    cost_trends: payload.cost_trends.map(parseModelProviderUsageTrend),
  };
}

function parseIntentRouterValidationIssue(payload: unknown): IntentRouterValidationIssue {
  if (!isRecord(payload) || typeof payload.path !== 'string' || typeof payload.message !== 'string') {
    throw new Error('意图路由校验错误项缺少核心字段');
  }
  return {
    path: payload.path,
    message: payload.message,
    line: payload.line === null ? null : optionalNumber(payload.line),
    column: payload.column === null ? null : optionalNumber(payload.column),
  };
}

export function parseIntentRouterValidationResult(payload: unknown): IntentRouterValidationResult {
  if (!isRecord(payload) || typeof payload.ok !== 'boolean' || !Array.isArray(payload.errors)) {
    throw new Error('意图路由校验响应结构无效');
  }
  return {
    ok: payload.ok,
    errors: payload.errors.map(parseIntentRouterValidationIssue),
  };
}

function parseIntentRouterEvalMetrics(payload: unknown): IntentRouterEvalMetrics {
  if (!isRecord(payload)) {
    throw new Error('意图路由评测指标结构无效');
  }
  return {
    precision: requiredFiniteNumber(payload.precision, '意图路由评测指标缺少 precision 字段'),
    recall: requiredFiniteNumber(payload.recall, '意图路由评测指标缺少 recall 字段'),
    false_positive: requiredFiniteNumber(payload.false_positive, '意图路由评测指标缺少 false_positive 字段'),
    false_negative: requiredFiniteNumber(payload.false_negative, '意图路由评测指标缺少 false_negative 字段'),
    support: requiredFiniteNumber(payload.support, '意图路由评测指标缺少 support 字段'),
  };
}

export function parseIntentRouterEvalReport(payload: unknown): IntentRouterEvalReport {
  if (!isRecord(payload) || !isRecord(payload.by_intent)) {
    throw new Error('意图路由评测响应结构无效');
  }
  return {
    total: requiredFiniteNumber(payload.total, '意图路由评测响应缺少 total 字段'),
    correct: requiredFiniteNumber(payload.correct, '意图路由评测响应缺少 correct 字段'),
    accuracy: requiredFiniteNumber(payload.accuracy, '意图路由评测响应缺少 accuracy 字段'),
    clarification_rate: requiredFiniteNumber(payload.clarification_rate, '意图路由评测响应缺少 clarification_rate 字段'),
    high_risk_false_positive: requiredFiniteNumber(payload.high_risk_false_positive, '意图路由评测响应缺少 high_risk_false_positive 字段'),
    by_intent: Object.fromEntries(
      Object.entries(payload.by_intent).map(([key, value]) => [key, parseIntentRouterEvalMetrics(value)]),
    ),
  };
}

export function parseIntentRouterConfigView(payload: unknown): IntentRouterConfigView {
  if (
    !isRecord(payload)
    || typeof payload.active_path !== 'string'
    || typeof payload.active_version !== 'string'
    || typeof payload.yaml_text !== 'string'
    || typeof payload.embedding_warmup_status !== 'string'
    || typeof payload.has_draft !== 'boolean'
  ) {
    throw new Error('意图路由配置视图响应缺少核心字段');
  }
  return {
    active_path: payload.active_path,
    active_version: payload.active_version,
    draft_version: optionalString(payload.draft_version),
    updated_at: optionalString(payload.updated_at),
    updated_by: optionalString(payload.updated_by),
    validation: parseIntentRouterValidationResult(payload.validation),
    evaluation: payload.evaluation === null ? null : (payload.evaluation === undefined ? undefined : parseIntentRouterEvalReport(payload.evaluation)),
    yaml_text: payload.yaml_text,
    config: payload.config === null ? null : (isRecord(payload.config) ? payload.config as IntentRouterRegistryConfig : undefined),
    embedding_warmup_status: payload.embedding_warmup_status,
    has_draft: payload.has_draft,
  };
}

export function parseResourceGenerationTask(payload: unknown): ResourceGenerationTask {
  if (
    !isRecord(payload)
    || typeof payload.task_id !== 'string'
    || typeof payload.status !== 'string'
    || typeof payload.resource_type !== 'string'
  ) {
    throw new Error('资源生成任务响应缺少核心字段');
  }
  return {
    task_id: payload.task_id,
    status: payload.status,
    resource_type: payload.resource_type,
    course_id: optionalString(payload.course_id),
    scope: typeof payload.scope === 'string' ? payload.scope : undefined,
    concept_id: optionalString(payload.concept_id),
    path_node_id: optionalString(payload.path_node_id),
    resource_type_label: optionalString(payload.resource_type_label),
    difficulty: typeof payload.difficulty === 'string' ? payload.difficulty : undefined,
    progress: optionalNumber(payload.progress),
    steps: parseResourceGenerationSteps(payload.steps),
    draft_content: optionalString(payload.draft_content),
    outline_json: parseOutlineSections(payload.outline_json),
    citations: parseCitationList(payload.citations),
    need_course_evidence: optionalBoolean(payload.need_course_evidence),
    course_evidence_required: optionalBoolean(payload.course_evidence_required),
    current_agent: optionalString(payload.current_agent),
    citation_coverage: optionalString(payload.citation_coverage),
    result_resource_id: optionalString(payload.result_resource_id),
    result_resource_code: optionalString(payload.result_resource_code),
    error_code: optionalString(payload.error_code),
    error_message: optionalString(payload.error_message),
    error_root_cause: optionalString(payload.error_root_cause),
    message: typeof payload.message === 'string' ? payload.message : undefined,
    orchestration: isRecord(payload.orchestration) ? payload.orchestration : undefined,
    assets: parseResourceAssets(payload.assets),
  };
}

function buildMockCourse(payload: CourseCreatePayload | CourseUpdatePayload, fallbackId = `course_${Date.now()}`): Course {
  return {
    id: fallbackId,
    title: payload.title ?? '课程',
    description: payload.description ?? '',
    status: payload.status ?? 'draft',
  };
}

function buildMockAssessmentResult(): AssessmentResult {
  return {
    id: `mock-assessment-${Date.now()}`,
    score: 86,
    mastery_delta: 6,
    feedback: '回答覆盖了核心步骤，建议补充链式法则中局部梯度相乘的解释。',
    weak_reasons: ['公式推导细节不足', '中间变量定义不够清晰'],
    recommended_actions: ['复习反向传播动画讲解', '完成链式求导补救题'],
    rubric: [
      { key: 'concept_accuracy', label: '概念准确性', score: 88, weight: 0.35, evidence: '覆盖核心定义和输入输出。', feedback: '概念主线稳定。' },
      { key: 'reasoning_integrity', label: '推理完整性', score: 80, weight: 0.30, evidence: '说明了主要步骤，但局部梯度连接还可补强。', feedback: '补充中间过程会更完整。' },
      { key: 'evidence_examples', label: '证据与例子', score: 84, weight: 0.20, evidence: '给出了简单例子。', feedback: '可加入代码或图解证据。' },
      { key: 'transfer_practice', label: '迁移应用', score: 74, weight: 0.15, evidence: '迁移到实践的说明偏少。', feedback: '建议补一个项目场景。' },
    ],
    scoring_method: 'mock_llm_rubric',
    progress_report: '你已经能解释主线概念，下一步建议围绕链式法则做一次针对性补救。',
  };
}

function buildEmptyConversationHistory(courseId: string): ConversationHistoryResponse {
  return {
    course_id: courseId,
    today_items: [],
    yesterday_items: [],
    older_items: [],
  };
}

function buildEmptyConversationMessages(conversationId: string): ConversationMessagesResponse {
  return {
    conversation_id: conversationId,
    messages: [],
  };
}

function buildMockChatResponse(payload: ChatPayload): ChatResponse {
  const isGeneral = payload.learning_scope === 'general' || !payload.course_id;
  return {
    conversation_id: payload.conversation_id ?? `mock-conv-${Date.now()}`,
    answer: isGeneral
      ? '这是 mock 模式的通用 AI 学习助手回答。可直接提问、规划学习或生成 Markdown 资料，不绑定课程知识库。'
      : '这是 mock 模式的课程 RAG 回答。当前问题已绑定课程，并返回引用来源用于演示。',
    citations: isGeneral
      ? []
      : [{ source_title: '深度学习讲义第 8 章.pdf', page_no: 118, similarity: 0.82, snippet: 'CNN 通过局部感受野、权重共享和池化提取层次特征。' }],
    agent_trace: [
      {
        step: isGeneral ? '通用学习上下文' : '课程上下文 Agent',
        status: 'completed',
        detail: isGeneral ? '通用学习 · 不使用课程知识库' : '已确认当前课程',
      },
    ],
  };
}

function buildMockModelProviderIcon(file: File): ModelProviderIcon {
  return { filename: file.name, url: `/provider-icons/${file.name}`, deletable: true };
}

function buildMockProviderCheckAllResult(): ProviderCheckAllResult {
  return {
    status: 'completed',
    checked: 3,
    passed: 2,
    degraded: 0,
    failed: 1,
    items: [],
  };
}

async function createMockUploadedResource(payload: ResourceUploadPayload): Promise<Resource> {
  const now = new Date().toISOString();
  const fileContent = payload.file ? await payload.file.text() : '';
  const manualContent = payload.content?.trim() ?? '';
  const content = fileContent && manualContent
    ? `${fileContent.trim()}\n\n---\n\n## 上传补充说明\n\n${manualContent}`
    : (fileContent.trim() || manualContent || '# 上传资源\n\n暂无正文');
  const id = `upload-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
  const title = payload.title.trim() || payload.file?.name.replace(/\.[^.]+$/, '') || '上传资源';
  const resource: Resource = {
    id,
    course_id: payload.courseId ?? null,
    concept_id: payload.conceptId ?? null,
    path_node_id: payload.pathNodeId ?? null,
    title,
    resource_type: payload.resourceType,
    type: mockResourceTypeLabels[payload.resourceType] ?? payload.resourceType,
    difficulty: payload.difficulty,
    difficulty_label: mockDifficultyLabels[payload.difficulty] ?? payload.difficulty,
    status: payload.submitForReview ? 'pending_review' : 'private',
    summary: payload.summary?.trim() || content.replace(/[#*`>\-]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120) || '用户上传的资源草稿',
    quality: 'B',
    refs: 0,
    quality_score: 72,
    citations: [],
    personalization: {},
    generation_basis_summary: '用户上传并保存为个人资源草稿',
    citation_coverage: 'manual_upload',
    safety_status: 'passed',
    latest_version: 1,
    content,
    updated_at: now,
    scope: payload.courseId ? 'course' : 'general',
    owner_scope: 'mine',
    course_bound: Boolean(payload.courseId),
    course_evidence_required: false,
    is_recommended: false,
    is_featured: false,
    view_count: 0,
    copied_count: 0,
    recommendation_score: 72,
    match_reason: payload.courseId ? '已绑定当前课程，可继续编辑或提交审核' : '通用上传资源，可归档到课程',
    recommendation_evidence: [
      {
        key: 'manual_upload',
        label: '个人上传',
        summary: payload.courseId ? '已绑定当前课程，可继续编辑、提交审核或加入学习清单。' : '通用上传资源，可后续归档到课程。',
        source: 'manual_upload',
        score: 72,
      },
    ],
    badges: [payload.courseId ? '本课' : '通用', '我的', payload.submitForReview ? '待审' : '草稿'],
    assets: [],
    asset_count: 0,
  };
  mockUploadedResources.unshift(resource);
  mockUploadedResourceVersions.set(id, [
    {
      id: `${id}-v1`,
      version: 1,
      content,
      meta: { source: 'manual_upload', source_filename: payload.file?.name ?? null },
      created_at: now,
    },
  ]);
  return resource;
}

function buildMockResourceHall(
  courseId?: string | null,
  params: { q?: string; scope?: string; type?: string; difficulty?: string; page?: number; pageSize?: number } = {},
): ResourceHallResponse {
  const query = params.q?.trim().toLowerCase() ?? '';
  const scope = params.scope ?? 'all';
  const typed = params.type && params.type !== 'all' ? params.type : null;
  const difficulty = params.difficulty && params.difficulty !== 'all' ? params.difficulty : null;
  const resources = listMockResources().map((item, index) => {
    const refs = item.refs ?? item.citations?.length ?? 0;
    const score = (item.quality_score ?? 80) + refs * 4 + (3 - index) * 2;
    const isFeatured = item.status === 'featured';
    return {
      ...item,
      scope: item.course_id ? 'course' : 'general',
      owner_scope: index === 1 ? 'community' : 'mine',
      view_count: 120 - index * 19,
      copied_count: 18 - index * 5,
      recommendation_score: score,
      is_featured: isFeatured,
      is_recommended: score >= 88,
      match_reason: refs > 0 ? `${refs} 条引用可追溯，匹配当前课程画像` : '适合作为通用学习补充',
      recommendation_evidence: [
        ...(item.course_id && courseId
          ? [{ key: 'course_match', label: '课程匹配', summary: '绑定当前课程，可直接服务本课学习路径。', source: 'course_context', score: 100 }]
          : []),
        ...(refs > 0
          ? [{ key: 'course_citation', label: '课程资料', summary: `${refs} 条引用可追溯，便于核验正文。`, source: 'citation', score: Math.min(100, 60 + refs * 8) }]
          : []),
        { key: 'quality', label: '质量与复用', summary: `推荐分 ${Math.round(score)}，按质量、引用和资源状态排序。`, source: 'mock_ranking', score: Math.round(score) },
      ],
      badges: [
        item.course_id ? '本课' : '通用',
        index === 1 ? '社区' : '我的',
        ...(isFeatured ? ['精选'] : []),
        ...(refs > 0 ? ['可溯源'] : []),
      ],
    } satisfies Resource;
  });
  let items = resources.filter((item) => !courseId || !item.course_id || item.course_id === courseId);
  if (typed) items = items.filter((item) => item.resource_type === typed || item.type === typed);
  if (difficulty) items = items.filter((item) => item.difficulty === difficulty);
  if (query) {
    items = items.filter((item) =>
      `${item.title} ${item.summary} ${item.type ?? ''} ${item.resource_type} ${item.match_reason ?? ''} ${(item.recommendation_evidence ?? []).map((evidence) => `${evidence.label} ${evidence.summary}`).join(' ')}`.toLowerCase().includes(query),
    );
  }
  items = [...items].sort((a, b) => (b.recommendation_score ?? 0) - (a.recommendation_score ?? 0));
  const countBy = (selector: (item: Resource) => string | undefined | null) => {
    const counts = new Map<string, number>();
    for (const item of items) {
      const value = selector(item);
      if (!value) continue;
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
    return counts;
  };
  const typeCounts = countBy((item) => item.resource_type);
  const difficultyCounts = countBy((item) => item.difficulty);
  const scopeCounts = new Map<string, number>([
    ['course', items.filter((item) => item.course_id === courseId).length],
    ['general', items.filter((item) => !item.course_id || item.scope === 'general').length],
    ['mine', items.filter((item) => item.owner_scope === 'mine').length],
    ['community', items.filter((item) => item.owner_scope === 'community').length],
    ['recommended', items.filter((item) => item.is_recommended).length],
  ]);
  const optionsFromCounts = (counts: Map<string, number>, labels: Record<string, string>) =>
    Array.from(counts.entries())
      .filter(([, count]) => count > 0)
      .map(([value, count]) => ({ value, label: labels[value] ?? value, count }));
  const total = items.length;
  const scopedItems = items.filter((item) => {
    if (scope === 'all') return true;
    if (scope === 'course') return Boolean(courseId) && item.course_id === courseId;
    if (scope === 'general') return item.scope === 'general' || !item.course_id;
    if (scope === 'mine') return item.owner_scope === 'mine';
    if (scope === 'community') return item.owner_scope === 'community' || item.status === 'published' || item.status === 'featured';
    if (scope === 'recommended') return Boolean(item.is_recommended);
    return true;
  });
  const pageSize = Math.min(48, Math.max(6, params.pageSize ?? 12));
  const totalItems = scopedItems.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const page = Math.min(totalPages, Math.max(1, params.page ?? 1));
  const offset = (page - 1) * pageSize;
  return {
    items: scopedItems.slice(offset, offset + pageSize),
    stats: {
      total,
      course: scopeCounts.get('course') ?? 0,
      general: scopeCounts.get('general') ?? 0,
      mine: scopeCounts.get('mine') ?? 0,
      community: scopeCounts.get('community') ?? 0,
      recommended: scopeCounts.get('recommended') ?? 0,
      featured: items.filter((item) => item.is_featured).length,
      with_citations: items.filter((item) => (item.refs ?? item.citations?.length ?? 0) > 0).length,
      avg_quality: total ? Math.round(items.reduce((sum, item) => sum + (item.quality_score ?? 0), 0) / total) : 0,
      total_views: items.reduce((sum, item) => sum + (item.view_count ?? 0), 0),
      total_copies: items.reduce((sum, item) => sum + (item.copied_count ?? 0), 0),
    },
    filters: {
      scopes: [
        { value: 'all', label: '全部资源', count: total },
        ...optionsFromCounts(scopeCounts, {
          course: '当前课程',
          general: '通用资源',
          mine: '我的生成',
          community: '社区共享',
          recommended: '画像推荐',
        }),
      ],
      resource_types: [{ value: 'all', label: '全部类型', count: total }, ...optionsFromCounts(typeCounts, mockResourceTypeLabels)],
      difficulties: [{ value: 'all', label: '全部难度', count: total }, ...optionsFromCounts(difficultyCounts, mockDifficultyLabels)],
    },
    highlights: {
      featured: items.filter((item) => item.is_featured).slice(0, 3),
      recommended: items.filter((item) => item.is_recommended).slice(0, 4),
      recent: items.slice(0, 4),
    },
    pagination: {
      page,
      page_size: pageSize,
      total_items: totalItems,
      total_pages: totalPages,
      offset,
      has_prev: page > 1,
      has_next: page < totalPages,
    },
    course_id: courseId ?? null,
    query: params.q ?? null,
    generated_at: new Date().toISOString(),
  };
}

async function probeBackendHealth(): Promise<boolean> {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/api\/v1\/?$/, '');
  const url = `${base}/health`;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 2500);
  try {
    const response = await fetch(url, { signal: controller.signal, credentials: 'include' });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

const MOCK_ANNOUNCEMENTS_KEY = 'zhike_mock_announcements';
const MOCK_ANNOUNCEMENT_READS_KEY = 'zhike_mock_announcement_reads';
const MOCK_ANNOUNCEMENT_DISMISSALS_KEY = 'zhike_mock_announcement_dismissals';
const MOCK_LOGIN_BACKGROUND_KEY = 'zhike_mock_login_background';
const MOCK_LEARNING_SCHEDULES_KEY = 'zhike_mock_learning_schedules';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isOptionalStringOrNull(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'string';
}

function isOptionalNumberOrNull(value: unknown): boolean {
  return value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isOptionalBoolean(value: unknown): boolean {
  return value === undefined || typeof value === 'boolean';
}

function isOptionalNumber(value: unknown): boolean {
  return value === undefined || (typeof value === 'number' && Number.isFinite(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isLearningScheduleItem(value: unknown): value is LearningScheduleItem {
  if (!isRecord(value)) return false;
  return typeof value.id === 'string'
    && typeof value.title === 'string'
    && typeof value.scheduled_date === 'string'
    && typeof value.status === 'string'
    && typeof value.priority === 'number';
}

function isPartialLoginBackgroundSettings(value: unknown): value is Partial<LoginBackgroundSettings> {
  if (!isRecord(value)) return false;
  return isOptionalBoolean(value.enabled)
    && (value.media_type === undefined || value.media_type === 'image' || value.media_type === 'video')
    && (value.fit === undefined || value.fit === 'cover' || value.fit === 'contain')
    && (value.media_url === undefined || typeof value.media_url === 'string')
    && isOptionalNumber(value.position_x)
    && isOptionalNumber(value.position_y)
    && isOptionalNumber(value.scale)
    && isOptionalNumber(value.brightness)
    && isOptionalNumber(value.contrast)
    && isOptionalNumber(value.saturate)
    && isOptionalNumber(value.blur)
    && isOptionalNumber(value.overlay_opacity)
    && (value.fallback_color === undefined || typeof value.fallback_color === 'string')
    && isOptionalStringOrNull(value.updated_at)
    && isOptionalStringOrNull(value.updated_by);
}

function isAnnouncementItem(value: unknown): value is AnnouncementItem {
  if (!isRecord(value)) return false;
  return typeof value.id === 'string'
    && typeof value.title === 'string'
    && typeof value.summary === 'string'
    && typeof value.category === 'string'
    && typeof value.priority === 'string'
    && typeof value.display_type === 'string'
    && typeof value.audience_role === 'string'
    && typeof value.status === 'string'
    && typeof value.pinned === 'boolean'
    && typeof value.dismissible === 'boolean'
    && typeof value.require_confirmation === 'boolean'
    && isOptionalNumberOrNull(value.auto_dismiss_seconds)
    && isOptionalStringOrNull(value.action_label)
    && isOptionalStringOrNull(value.action_url)
    && isOptionalStringOrNull(value.effective_at)
    && isOptionalStringOrNull(value.expires_at)
    && isOptionalStringOrNull(value.created_at)
    && isOptionalStringOrNull(value.updated_at)
    && typeof value.is_read === 'boolean'
    && typeof value.is_dismissed === 'boolean'
    && typeof value.is_active === 'boolean'
    && isOptionalNumberOrNull(value.read_count)
    && isOptionalNumberOrNull(value.dismissal_count);
}

function isAnnouncementDetail(value: unknown): value is AnnouncementDetail {
  if (!isRecord(value) || typeof value.body !== 'string') return false;
  return isAnnouncementItem(value);
}

function isAnnouncementDetailArray(value: unknown): value is AnnouncementDetail[] {
  return Array.isArray(value) && value.every(isAnnouncementDetail);
}

function normalizeAnnouncementPriority(value: string): AnnouncementPayload['priority'] {
  if (value === 'info' || value === 'success' || value === 'warning' || value === 'critical' || value === 'maintenance') {
    return value;
  }
  return 'info';
}

function normalizeAnnouncementDisplayType(value: string): AnnouncementPayload['display_type'] {
  if (value === 'top_bar' || value === 'modal' || value === 'page_card' || value === 'toast' || value === 'list_only') {
    return value;
  }
  return 'list_only';
}

function normalizeAnnouncementAudience(value: string): AnnouncementPayload['audience_role'] {
  if (value === 'all' || value === 'student' || value === 'admin') {
    return value;
  }
  return 'all';
}

function normalizeAnnouncementStatus(value: string): NonNullable<AnnouncementPayload['status']> {
  if (value === 'draft' || value === 'published' || value === 'archived' || value === 'deleted') {
    return value;
  }
  return 'draft';
}

function readMockLearningSchedules(): LearningScheduleItem[] {
  return readLocalJson<LearningScheduleItem[]>(
    MOCK_LEARNING_SCHEDULES_KEY,
    [],
    (value): value is LearningScheduleItem[] => Array.isArray(value) && value.every(isLearningScheduleItem),
  );
}

function writeMockLearningSchedules(items: LearningScheduleItem[]): void {
  writeLocalJson(MOCK_LEARNING_SCHEDULES_KEY, items);
}

function createMockLearningSchedule(payload: LearningSchedulePayload): LearningScheduleItem {
  const now = new Date().toISOString();
  const item: LearningScheduleItem = {
    id: `schedule-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`,
    course_id: payload.course_id ?? null,
    concept_id: payload.concept_id ?? null,
    path_node_id: payload.path_node_id ?? null,
    resource_id: payload.resource_id ?? null,
    source_type: payload.source_type ?? 'manual',
    source_id: payload.source_id ?? null,
    item_type: payload.item_type ?? 'focus',
    title: payload.title,
    description: payload.description ?? null,
    scheduled_date: payload.scheduled_date,
    time_label: payload.time_label ?? null,
    status: 'planned',
    priority: payload.priority ?? 50,
    meta_json: payload.meta_json ?? {},
    created_at: now,
    updated_at: now,
  };
  const items = [item, ...readMockLearningSchedules()];
  writeMockLearningSchedules(items);
  return item;
}

function updateMockLearningSchedule(itemId: string, payload: LearningScheduleUpdatePayload): LearningScheduleItem {
  const items = readMockLearningSchedules();
  const current = items.find((item) => item.id === itemId);
  if (!current) throw new Error('学习日程不存在。');
  const updated = { ...current, ...payload, updated_at: new Date().toISOString() };
  writeMockLearningSchedules(items.map((item) => (item.id === itemId ? updated : item)));
  return updated;
}

const mockIntentRouterYaml = `schema_version: "2.0"
version: "mock"
global:
  execution_threshold: 0.6
  clarification_threshold: 0.44
  margin_threshold: 0.06
  high_risk_threshold: 0.82
  semantic_provider: "semantic-router"
  embedding_provider: "model_gateway"
  llm_judge_enabled: true
  context_follow_up_phrases: ["那下一步呢"]
  context_block_phrases: ["我要学"]
  clarification:
    prompt: "你是想开始学习、查看进度，还是制定计划？"
    high_risk_prompt: "请确认要执行的学习动作。"
    code: "intent_clarification_required"
intents:
  - name: "start_learning_session"
    display_name: "开始学习"
    enabled: true
    description: "进入今天学习。"
    utterances: ["我要学", "开始学习"]
    negative_utterances: ["我学到哪了"]
    rules:
      exact_any: ["我要学"]
      contains_any: ["今天我要学什么"]
      contains_all: []
      negative_contains_any: ["学习进度"]
    risk_level: "low"
    response_route: "learning_plan"
    allowed_actions: ["suggest_learning_entry"]
    applicable_pages: ["dashboard"]
    priority: 40
  - name: "learning_plan_request"
    display_name: "学习计划"
    enabled: true
    description: "制定学习安排。"
    utterances: ["帮我安排学习"]
    negative_utterances: []
    rules:
      exact_any: []
      contains_any: ["学习计划"]
      contains_all: []
      negative_contains_any: []
    risk_level: "low"
    response_route: "learning_plan"
    allowed_actions: ["generate_learning_plan"]
    applicable_pages: ["dashboard"]
    priority: 50
  - name: "learning_progress_query"
    display_name: "学习进度"
    enabled: true
    description: "读取个人学习进度。"
    utterances: ["我学到哪了"]
    negative_utterances: ["我要学"]
    rules:
      exact_any: []
      contains_any: ["学习进度", "学到哪"]
      contains_all: []
      negative_contains_any: ["我要学"]
    risk_level: "medium"
    response_route: "learning_progress"
    allowed_actions: ["read_learning_progress"]
    applicable_pages: ["dashboard"]
    priority: 60
  - name: "course_rag_qa"
    display_name: "课程资料问答"
    enabled: true
    description: "基于课程资料回答。"
    utterances: ["课件里怎么定义 X"]
    negative_utterances: ["解释一下 X"]
    rules:
      exact_any: []
      contains_any: ["课件里"]
      contains_all: []
      negative_contains_any: []
    risk_level: "medium"
    response_route: "course_rag_qa"
    allowed_actions: ["query_course_rag"]
    applicable_pages: ["dashboard"]
    priority: 30
  - name: "resource_generation"
    display_name: "资源生成"
    enabled: true
    description: "创建学习资源。"
    utterances: ["根据我的薄弱点出题"]
    negative_utterances: ["我有哪些薄弱点"]
    rules:
      exact_any: []
      contains_any: ["出题", "生成练习题"]
      contains_all: []
      negative_contains_any: []
    risk_level: "high"
    response_route: "resource_generation"
    allowed_actions: ["create_resource_task"]
    applicable_pages: ["dashboard"]
    priority: 20
  - name: "default_chat"
    display_name: "普通对话"
    enabled: true
    description: "普通学习问答。"
    utterances: ["解释一下 X"]
    negative_utterances: []
    rules:
      exact_any: []
      contains_any: ["解释一下"]
      contains_all: []
      negative_contains_any: []
    risk_level: "low"
    response_route: "default_chat"
    allowed_actions: ["chat"]
    applicable_pages: ["dashboard"]
    priority: 900
`;

function mockIntentRouterConfig(): IntentRouterConfigView {
  const config: IntentRouterRegistryConfig = {
    schema_version: '2.0',
    version: 'mock',
    global: {
      execution_threshold: 0.6,
      clarification_threshold: 0.44,
      margin_threshold: 0.06,
      high_risk_threshold: 0.82,
      semantic_provider: 'semantic-router',
      embedding_provider: 'model_gateway',
      llm_judge_enabled: true,
      context_follow_up_phrases: ['那下一步呢'],
      context_block_phrases: ['我要学'],
      clarification: {
        prompt: '你是想开始学习、查看进度，还是制定计划？',
        high_risk_prompt: '请确认要执行的学习动作。',
        code: 'intent_clarification_required',
      },
    },
    intents: [
      {
        name: 'start_learning_session',
        display_name: '开始学习',
        enabled: true,
        description: '进入今天学习。',
        utterances: ['我要学', '开始学习'],
        negative_utterances: ['我学到哪了'],
        rules: { exact_any: ['我要学'], contains_any: ['今天我要学什么'], contains_all: [], negative_contains_any: ['学习进度'] },
        risk_level: 'low',
        response_route: 'learning_plan',
        allowed_actions: ['suggest_learning_entry'],
        applicable_pages: ['dashboard'],
        priority: 40,
      },
    ],
  };
  return {
    active_path: 'mock://intent_registry.yaml',
    active_version: 'mock',
    draft_version: null,
    updated_at: new Date().toISOString(),
    updated_by: 'mock-admin',
    validation: { ok: true, errors: [] },
    evaluation: null,
    yaml_text: mockIntentRouterYaml,
    config,
    embedding_warmup_status: 'ready',
    has_draft: false,
  };
}

const defaultLoginBackgroundSettings: LoginBackgroundSettings = {
  enabled: true,
  media_type: 'video',
  media_url: '/auth/login-hero.mp4',
  fit: 'cover',
  position_x: 50,
  position_y: 50,
  scale: 1.02,
  brightness: 0.96,
  contrast: 1.08,
  saturate: 1.08,
  blur: 0,
  overlay_opacity: 0.46,
  fallback_color: '#b7d8ea',
  updated_at: null,
  updated_by: null,
};

function mockAnnouncementSeeds(): AnnouncementDetail[] {
  const now = new Date().toISOString();
  return [
    {
      id: 'mock-maintenance',
      title: '系统维护通知',
      summary: '系统将于 2026 年 6 月 8 日 02:00 至 04:00 维护，部分功能可能短暂不可用。',
      body: '## 系统维护通知\n\n发生什么：平台将进行数据库与向量检索服务维护。\n\n影响谁：所有正在使用课程知识库、资源生成和后台管理的用户。\n\n影响时间：2026 年 6 月 8 日 02:00 至 04:00（Asia/Shanghai）。\n\n用户需要做什么：请提前保存正在编辑的资源、课程大纲和公告草稿。',
      category: 'maintenance',
      priority: 'maintenance',
      display_type: 'top_bar',
      audience_role: 'all',
      status: 'published',
      pinned: true,
      dismissible: true,
      require_confirmation: false,
      auto_dismiss_seconds: null,
      action_label: '查看详情',
      action_url: '/announcements',
      effective_at: now,
      expires_at: null,
      created_at: now,
      updated_at: now,
      is_read: false,
      is_dismissed: false,
      is_active: true,
    },
    {
      id: 'mock-critical-policy',
      title: '资源发布规则变更',
      summary: '资源大厅发布内容必须包含来源说明，管理员审核将重点检查引用完整性。',
      body: '## 资源发布规则变更\n\n发生什么：资源大厅发布内容必须包含来源说明和引用信息。\n\n影响谁：所有发布、复用和审核资源的用户。\n\n影响时间：自公告发布起立即生效。\n\n用户需要做什么：发布前检查来源说明；管理员审核时优先检查引用完整性。',
      category: 'policy',
      priority: 'critical',
      display_type: 'modal',
      audience_role: 'all',
      status: 'published',
      pinned: true,
      dismissible: false,
      require_confirmation: true,
      auto_dismiss_seconds: null,
      action_label: '查看详情',
      action_url: '/announcements',
      effective_at: now,
      expires_at: null,
      created_at: now,
      updated_at: now,
      is_read: false,
      is_dismissed: false,
      is_active: true,
    },
    {
      id: 'mock-resource-citation',
      title: '资源生成引用规范更新',
      summary: '课程资料生成结果将更严格标注引用来源，便于教师审核和学生复查。',
      body: '## 资源生成引用规范更新\n\n发生什么：资源工坊会优先使用可追溯引用，并在生成结果中突出来源页码。\n\n影响谁：使用课程资料生成讲义、题库、图解包的学生和管理员。\n\n用户需要做什么：生成资料后请检查引用卡片，必要时在资源审核中补充说明。',
      category: 'resource',
      priority: 'info',
      display_type: 'page_card',
      audience_role: 'all',
      status: 'published',
      pinned: false,
      dismissible: true,
      require_confirmation: false,
      auto_dismiss_seconds: null,
      action_label: '查看公告',
      action_url: '/announcements',
      effective_at: now,
      expires_at: null,
      created_at: now,
      updated_at: now,
      is_read: false,
      is_dismissed: false,
      is_active: true,
    },
    {
      id: 'mock-admin-enabled',
      title: '管理员公告后台已启用',
      summary: '管理员现在可以在公告后台发布顶部条、弹窗、卡片和 Toast 公告。',
      body: '## 管理员公告后台已启用\n\n发生什么：公告模块支持分受众、分优先级、分展示方式发布。\n\n影响谁：平台管理员。\n\n用户需要做什么：进入管理员模式，在公告后台创建、编辑和发布公告。',
      category: 'admin',
      priority: 'success',
      display_type: 'toast',
      audience_role: 'admin',
      status: 'published',
      pinned: false,
      dismissible: true,
      require_confirmation: false,
      auto_dismiss_seconds: 8,
      action_label: '去管理',
      action_url: '/admin/announcements',
      effective_at: now,
      expires_at: null,
      created_at: now,
      updated_at: now,
      is_read: false,
      is_dismissed: false,
      is_active: true,
    },
  ];
}

function readMockJson<T>(key: string, fallback: T, validator: (value: unknown) => value is T): T {
  return readLocalJson(key, fallback, validator);
}

function writeMockJson<T>(key: string, value: T): void {
  writeLocalJson(key, value);
}

function mockLoginBackgroundSettings(): LoginBackgroundSettings {
  return {
    ...defaultLoginBackgroundSettings,
    ...readMockJson<Partial<LoginBackgroundSettings>>(MOCK_LOGIN_BACKGROUND_KEY, {}, isPartialLoginBackgroundSettings),
  };
}

function mockUpdateLoginBackground(payload: Partial<LoginBackgroundSettings>): LoginBackgroundSettings {
  const next: LoginBackgroundSettings = {
    ...mockLoginBackgroundSettings(),
    ...payload,
    updated_at: new Date().toISOString(),
    updated_by: 'mock-admin',
  };
  writeMockJson(MOCK_LOGIN_BACKGROUND_KEY, next);
  return next;
}

function mockUploadLoginBackground(file: File): LoginBackgroundUploadResult {
  const suffix = file.name.split('.').pop()?.toLowerCase() ?? '';
  const mediaType = file.type.startsWith('video/') || ['mp4', 'webm'].includes(suffix) ? 'video' : 'image';
  return {
    filename: file.name,
    media_url: URL.createObjectURL(file),
    media_type: mediaType,
    size: file.size,
  };
}

function mockLoginBackgroundMediaAssets(): LoginBackgroundMediaLibraryResponse {
  const current = mockLoginBackgroundSettings();
  const items: LoginBackgroundMediaLibraryResponse['items'] = [
    {
      filename: 'login-hero.mp4',
      media_url: '/auth/login-hero.mp4',
      media_type: 'video',
      source: 'built_in',
      size: null,
      updated_at: null,
    },
  ];
  if (current.media_url !== '/auth/login-hero.mp4') {
    items.unshift({
      filename: current.media_url.split('/').pop() || '当前背景资源',
      media_url: current.media_url,
      media_type: current.media_type,
      source: 'server_upload',
      size: null,
      updated_at: current.updated_at ?? null,
    });
  }
  return { items };
}

function readMockAnnouncements(): AnnouncementDetail[] {
  const stored = readMockJson<AnnouncementDetail[]>(MOCK_ANNOUNCEMENTS_KEY, [], isAnnouncementDetailArray);
  if (stored.length) return stored;
  const seeds = mockAnnouncementSeeds();
  writeMockJson(MOCK_ANNOUNCEMENTS_KEY, seeds);
  return seeds;
}

function writeMockAnnouncements(items: AnnouncementDetail[]): void {
  writeMockJson(MOCK_ANNOUNCEMENTS_KEY, items);
}

function readMockReadIds(): Set<string> {
  return new Set(readMockJson<string[]>(MOCK_ANNOUNCEMENT_READS_KEY, [], isStringArray));
}

function writeMockReadIds(values: Set<string>): void {
  writeMockJson(MOCK_ANNOUNCEMENT_READS_KEY, Array.from(values));
}

function readMockDismissals(): Set<string> {
  return new Set(readMockJson<string[]>(MOCK_ANNOUNCEMENT_DISMISSALS_KEY, [], isStringArray));
}

function writeMockDismissals(values: Set<string>): void {
  writeMockJson(MOCK_ANNOUNCEMENT_DISMISSALS_KEY, Array.from(values));
}

function mockDismissalKey(item: AnnouncementItem, displayType = item.display_type): string {
  return `${item.id}:${displayType}`;
}

function mockCurrentRole(): string {
  return authMock.user.role ?? 'student';
}

function isMockAnnouncementActive(item: AnnouncementItem): boolean {
  const now = Date.now();
  const effective = item.effective_at ? new Date(item.effective_at).getTime() : 0;
  const expires = item.expires_at ? new Date(item.expires_at).getTime() : Number.POSITIVE_INFINITY;
  return item.status === 'published' && effective <= now && expires > now;
}

function withMockAnnouncementState(item: AnnouncementDetail, readIds = readMockReadIds(), dismissals = readMockDismissals()): AnnouncementDetail {
  return {
    ...item,
    is_read: readIds.has(item.id),
    is_dismissed: dismissals.has(mockDismissalKey(item)),
    is_active: isMockAnnouncementActive(item),
  };
}

function visibleMockAnnouncements(activeOnly = false): AnnouncementDetail[] {
  const role = mockCurrentRole();
  return readMockAnnouncements()
    .filter((item) => item.status === 'published')
    .filter((item) => item.audience_role === 'all' || item.audience_role === role)
    .filter((item) => !activeOnly || isMockAnnouncementActive(item))
    .map((item) => withMockAnnouncementState(item))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.updated_at ?? '').localeCompare(a.updated_at ?? ''));
}

function mockAnnouncementSummary(): AnnouncementSummaryResponse {
  const items = visibleMockAnnouncements(true).filter((item) => !item.is_dismissed);
  const unreadCount = visibleMockAnnouncements(true).filter((item) => !item.is_read).length;
  return {
    unread_count: unreadCount,
    top_bar: items.find((item) => item.display_type === 'top_bar') ?? null,
    modal: items.find((item) => item.display_type === 'modal') ?? null,
    page_cards: items.filter((item) => item.display_type === 'page_card').slice(0, 3),
    toast_items: items.filter((item) => item.display_type === 'toast').slice(0, 2),
  };
}

function mockAnnouncementList(params: {
  category?: string;
  priority?: string;
  displayType?: string;
  unreadOnly?: boolean;
  limit?: number;
} = {}): AnnouncementListResponse {
  let items = visibleMockAnnouncements(false);
  if (params.category) items = items.filter((item) => item.category === params.category);
  if (params.priority) items = items.filter((item) => item.priority === params.priority);
  if (params.displayType) items = items.filter((item) => item.display_type === params.displayType);
  if (params.unreadOnly) items = items.filter((item) => !item.is_read);
  items = items.slice(0, params.limit ?? 100);
  return {
    items,
    total: items.length,
    unread_count: visibleMockAnnouncements(true).filter((item) => !item.is_read).length,
  };
}

function mockAnnouncementDetail(announcementId: string): AnnouncementDetail {
  const item = visibleMockAnnouncements(false).find((announcement) => announcement.id === announcementId);
  if (!item) throw new Error('公告不存在。');
  return item;
}

function mockReadAnnouncement(announcementId: string): { status: string; announcement_id: string } {
  const reads = readMockReadIds();
  reads.add(announcementId);
  writeMockReadIds(reads);
  return { status: 'ok', announcement_id: announcementId };
}

function mockDismissAnnouncement(announcementId: string, displayType: AnnouncementDisplayType | string): { status: string; announcement_id: string } {
  const dismissals = readMockDismissals();
  dismissals.add(`${announcementId}:${displayType}`);
  writeMockDismissals(dismissals);
  return { status: 'ok', announcement_id: announcementId };
}

function mockReadAllAnnouncements(): { status: string; unread_count: number } {
  const reads = readMockReadIds();
  visibleMockAnnouncements(false).forEach((item) => reads.add(item.id));
  writeMockReadIds(reads);
  return { status: 'ok', unread_count: 0 };
}

function mockAdminAnnouncementStats(): AnnouncementStats {
  const items = readMockAnnouncements();
  return {
    total: items.length,
    draft: items.filter((item) => item.status === 'draft').length,
    published: items.filter((item) => item.status === 'published').length,
    archived: items.filter((item) => item.status === 'archived').length,
    deleted: items.filter((item) => item.status === 'deleted').length,
    active: items.filter(isMockAnnouncementActive).length,
    critical: items.filter((item) => item.priority === 'critical').length,
    unread_total: visibleMockAnnouncements(true).filter((item) => !item.is_read).length,
  };
}

function mockAdminAnnouncementList(params: { status?: string; q?: string; displayType?: string; audienceRole?: string; priority?: string } = {}) {
  let items = readMockAnnouncements().map((item) => withMockAnnouncementState(item));
  if (params.status && params.status !== 'all') items = items.filter((item) => item.status === params.status);
  if (params.displayType && params.displayType !== 'all') items = items.filter((item) => item.display_type === params.displayType);
  if (params.audienceRole && params.audienceRole !== 'all') items = items.filter((item) => item.audience_role === params.audienceRole);
  if (params.priority && params.priority !== 'all') items = items.filter((item) => item.priority === params.priority);
  if (params.q?.trim()) {
    const query = params.q.trim();
    items = items.filter((item) => `${item.title} ${item.summary} ${item.body}`.includes(query));
  }
  return { items, total: items.length };
}

function mockUpsertAdminAnnouncement(payload: AnnouncementPayload, announcementId?: string): AnnouncementDetail {
  const now = new Date().toISOString();
  const items = readMockAnnouncements();
  const index = announcementId ? items.findIndex((item) => item.id === announcementId) : -1;
  const current = index >= 0 ? items[index] : null;
  const next: AnnouncementDetail = {
    ...(current ?? {
      id: `mock-announcement-${Date.now()}`,
      created_at: now,
      is_read: false,
      is_dismissed: false,
      is_active: false,
    }),
    ...payload,
    status: payload.status ?? current?.status ?? 'draft',
    action_label: payload.action_label || null,
    action_url: payload.action_url || null,
    auto_dismiss_seconds: payload.auto_dismiss_seconds ?? null,
    effective_at: payload.effective_at || null,
    expires_at: payload.expires_at || null,
    updated_at: now,
  };
  if (index >= 0) {
    items[index] = next;
  } else {
    items.unshift(next);
  }
  writeMockAnnouncements(items);
  return withMockAnnouncementState(next);
}

function mockChangeAdminAnnouncementStatus(announcementId: string, status: 'published' | 'archived' | 'deleted'): { status: string; announcement_id: string } {
  const items = readMockAnnouncements().map((item) => (
    item.id === announcementId ? { ...item, status, updated_at: new Date().toISOString() } : item
  ));
  writeMockAnnouncements(items);
  return { status, announcement_id: announcementId };
}

export const api = {
  runtimeInfo: () => resolveDataMode(),
  checkBackendHealth: () => (shouldUseMockData() ? Promise.resolve(true) : probeBackendHealth()),
  demoAuthSession: () => (shouldUseMockData() ? mockDemoAuthSession() : null),
  resourceReviewWorkspace: () => (shouldUseMockData() ? Promise.resolve(mockResourceReviewWorkspace()) : Promise.resolve(null)),
  personalSettingsSummary: () => (shouldUseMockData()
    ? Promise.resolve(mockPersonalSettingsSummary())
    : Promise.resolve({
      modelStatus: '未配置',
      privacyRetention: '未配置',
      documentCleanup: '未配置',
      provider: '未配置',
      model: '未配置',
    })),
  loginBackgroundSettings: () => (shouldUseMockData()
    ? Promise.resolve(mockLoginBackgroundSettings())
    : request<LoginBackgroundSettings>('/settings/login-background')),
  adminLoginBackgroundSettings: () => (shouldUseMockData()
    ? Promise.resolve(mockLoginBackgroundSettings())
    : request<LoginBackgroundSettings>('/admin/settings/login-background')),
  updateLoginBackgroundSettings: (payload: Partial<LoginBackgroundSettings>) => (shouldUseMockData()
    ? Promise.resolve(mockUpdateLoginBackground(payload))
    : request<LoginBackgroundSettings>('/admin/settings/login-background', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })),
  uploadLoginBackgroundMedia: (file: File) => {
    if (shouldUseMockData()) return Promise.resolve(mockUploadLoginBackground(file));
    const formData = new FormData();
    formData.append('file', file);
    return request<LoginBackgroundUploadResult>('/admin/settings/login-background/media', {
      method: 'POST',
      body: formData,
      timeoutMs: 90_000,
    });
  },
  loginBackgroundMediaAssets: () => (shouldUseMockData()
    ? Promise.resolve(mockLoginBackgroundMediaAssets())
    : request<LoginBackgroundMediaLibraryResponse>('/admin/settings/login-background/media')),
  announcementSummary: () => (shouldUseMockData()
    ? Promise.resolve(mockAnnouncementSummary())
    : request<AnnouncementSummaryResponse>('/announcements/summary')),
  announcements: (params: {
    category?: string;
    priority?: string;
    displayType?: string;
    unreadOnly?: boolean;
    limit?: number;
  } = {}) => {
    if (shouldUseMockData()) return Promise.resolve(mockAnnouncementList(params));
    const query = new URLSearchParams();
    if (params.category) query.set('category', params.category);
    if (params.priority) query.set('priority', params.priority);
    if (params.displayType) query.set('display_type', params.displayType);
    if (params.unreadOnly) query.set('unread_only', 'true');
    if (params.limit) query.set('limit', String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<AnnouncementListResponse>(`/announcements${suffix}`);
  },
  announcementDetail: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(mockAnnouncementDetail(announcementId))
    : request<AnnouncementDetail>(`/announcements/${encodeURIComponent(announcementId)}`)),
  readAnnouncement: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(mockReadAnnouncement(announcementId))
    : request<{ status: string; announcement_id: string }>(`/announcements/${encodeURIComponent(announcementId)}/read`, { method: 'POST' })),
  dismissAnnouncement: (announcementId: string, displayType: AnnouncementDisplayType | string) => (shouldUseMockData()
    ? Promise.resolve(mockDismissAnnouncement(announcementId, displayType))
    : request<{ status: string; announcement_id: string }>(`/announcements/${encodeURIComponent(announcementId)}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({ display_type: displayType }),
    })),
  readAllAnnouncements: () => (shouldUseMockData()
    ? Promise.resolve(mockReadAllAnnouncements())
    : request<{ status: string; unread_count: number }>('/announcements/read-all', { method: 'POST' })),
  adminAnnouncementStats: () => (shouldUseMockData()
    ? Promise.resolve(mockAdminAnnouncementStats())
    : request<AnnouncementStats>('/admin/announcements/stats')),
  adminAnnouncements: (params: {
    status?: string;
    q?: string;
    displayType?: string;
    audienceRole?: string;
    priority?: string;
    category?: string;
    limit?: number;
  } = {}) => {
    if (shouldUseMockData()) return Promise.resolve(mockAdminAnnouncementList(params));
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.q) query.set('q', params.q);
    if (params.displayType) query.set('display_type', params.displayType);
    if (params.audienceRole) query.set('audience_role', params.audienceRole);
    if (params.priority) query.set('priority', params.priority);
    if (params.category) query.set('category', params.category);
    if (params.limit) query.set('limit', String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: AnnouncementItem[]; total: number }>(`/admin/announcements${suffix}`);
  },
  adminAnnouncementDetail: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(readMockAnnouncements().find((item) => item.id === announcementId) ?? mockAnnouncementDetail(announcementId))
    : request<AnnouncementDetail>(`/admin/announcements/${encodeURIComponent(announcementId)}`)),
  createAdminAnnouncement: (payload: AnnouncementPayload) => (shouldUseMockData()
    ? Promise.resolve(mockUpsertAdminAnnouncement(payload))
    : request<AnnouncementDetail>('/admin/announcements', { method: 'POST', body: JSON.stringify(payload) })),
  updateAdminAnnouncement: (announcementId: string, payload: Partial<AnnouncementPayload>) => {
    if (shouldUseMockData()) {
      const current = readMockAnnouncements().find((item) => item.id === announcementId);
      if (!current) return Promise.reject(new Error('公告不存在。'));
      return Promise.resolve(mockUpsertAdminAnnouncement({
        title: payload.title ?? current.title,
        summary: payload.summary ?? current.summary,
        body: payload.body ?? current.body,
        category: payload.category ?? current.category,
        priority: payload.priority ?? normalizeAnnouncementPriority(current.priority),
        display_type: payload.display_type ?? normalizeAnnouncementDisplayType(current.display_type),
        audience_role: payload.audience_role ?? normalizeAnnouncementAudience(current.audience_role),
        status: payload.status ?? normalizeAnnouncementStatus(current.status),
        pinned: payload.pinned ?? current.pinned,
        dismissible: payload.dismissible ?? current.dismissible,
        require_confirmation: payload.require_confirmation ?? current.require_confirmation,
        auto_dismiss_seconds: payload.auto_dismiss_seconds ?? current.auto_dismiss_seconds,
        action_label: payload.action_label ?? current.action_label,
        action_url: payload.action_url ?? current.action_url,
        effective_at: payload.effective_at ?? current.effective_at,
        expires_at: payload.expires_at ?? current.expires_at,
      }, announcementId));
    }
    return request<AnnouncementDetail>(`/admin/announcements/${encodeURIComponent(announcementId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
  publishAdminAnnouncement: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(mockChangeAdminAnnouncementStatus(announcementId, 'published'))
    : request<{ status: string; announcement_id: string }>(`/admin/announcements/${encodeURIComponent(announcementId)}/publish`, { method: 'POST' })),
  archiveAdminAnnouncement: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(mockChangeAdminAnnouncementStatus(announcementId, 'archived'))
    : request<{ status: string; announcement_id: string }>(`/admin/announcements/${encodeURIComponent(announcementId)}/archive`, { method: 'POST' })),
  deleteAdminAnnouncement: (announcementId: string) => (shouldUseMockData()
    ? Promise.resolve(mockChangeAdminAnnouncementStatus(announcementId, 'deleted'))
    : request<{ status: string; announcement_id: string }>(`/admin/announcements/${encodeURIComponent(announcementId)}`, { method: 'DELETE' })),
  login: (payload: LoginPayload) =>
    shouldUseMockData()
      ? Promise.resolve({ access_token: authMock.token, token_type: 'bearer', user: authMock.user } satisfies AuthResponse)
      : request<AuthResponse>('/auth/login', {
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify(payload),
        validate: parseAuthResponse,
      }),
  register: (payload: RegisterPayload) =>
    shouldUseMockData()
      ? Promise.resolve({ access_token: authMock.token, token_type: 'bearer', user: { ...authMock.user, name: payload.name, email: payload.email, role: payload.role ?? 'student' } } satisfies AuthResponse)
      : request<AuthResponse>('/auth/register', {
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify(payload),
        validate: parseAuthResponse,
      }),
  me: () =>
    shouldUseMockData()
      ? Promise.resolve({ user: authMock.user })
      : request<{ user: AuthResponse['user'] }>('/auth/me', {
        credentials: 'include',
        validate: parseCurrentUserResponse,
      }),
  updateMe: (payload: UpdateMePayload) =>
    shouldUseMockData()
      ? Promise.resolve({ user: { ...authMock.user, name: payload.name.trim() || authMock.user.name } })
      : request<{ user: AuthResponse['user'] }>('/auth/me', {
        method: 'PATCH',
        credentials: 'include',
        body: JSON.stringify(payload),
        validate: parseCurrentUserResponse,
      }),
  logout: () =>
    shouldUseMockData()
      ? Promise.resolve({ status: 'ok' })
      : request<{ status: string }>('/auth/logout', { method: 'POST', credentials: 'include' }),
  courses: () => shouldUseMockData()
    ? Promise.resolve({ items: mockActiveCourses() })
    : request<{ items: Course[] }>('/courses', { validate: parseCourseListResponse }),
  adminCourses: () =>
    shouldUseMockData()
      ? Promise.resolve({ items: mockActiveCourses() })
      : request<{ items: Course[] }>('/admin/courses', { validate: parseCourseListResponse }),
  myCourses: () => shouldUseMockData()
    ? Promise.resolve({ user: authMock.user.name, items: mockFixtureCourses() })
    : request<{ user: string; items: Course[] }>('/me/courses', { validate: parseUserCourseListResponse }),
  currentCourse: () => shouldUseMockData()
    ? Promise.resolve({ course_id: 'deep_learning_001' })
    : request<{ course_id: string | null }>('/me/current-course', { validate: parseCurrentCourseResponse }),
  updateCurrentCourse: (courseId: string) =>
    shouldUseMockData() ? Promise.resolve({ course_id: courseId, message: 'mock current course updated' }) : request<{ course_id: string; message: string }>('/me/current-course', {
      method: 'PUT',
      body: JSON.stringify({ course_id: courseId }),
      validate: parseCurrentCourseUpdateResponse,
    }),
  concepts: (courseId: string) =>
    shouldUseMockData()
      ? Promise.resolve({ items: mockFixtureConcepts(), sections: [] })
      : request<CourseConceptOutline>(`/courses/${courseId}/concepts`),
  courseAiContext: (courseId: string) =>
    shouldUseMockData()
      ? Promise.resolve({
          course_id: courseId,
          course_title: '深度学习',
          knowledge_ready: true,
          chat_input_enabled: true,
          file_ids_count: 1,
          qa_mode: 'MIX',
          spark_version: 'ultra',
          require_citation_for_course_answer: true,
          default_use_course_evidence_for_resource: true,
          status_label: '深度学习 · 知识库已就绪',
        } satisfies CourseAiContext)
      : request<CourseAiContext>(`/courses/${courseId}/ai-context`),
  courseExtractedQa: (courseId: string, limit = 12) =>
    shouldUseMockData()
      ? Promise.resolve<{ course_id: string; items: ExtractedQaItem[] }>({ course_id: courseId, items: [] })
      : request<{ course_id: string; items: ExtractedQaItem[] }>(`/courses/${courseId}/extracted-qa?limit=${limit}`),
  courseExtractedQaDetail: (courseId: string, qaId: string) =>
    request<ExtractedQaItem>(`/courses/${courseId}/extracted-qa/${qaId}`),
  courseBuilder: (courseId: string) => shouldUseMockData() ? Promise.resolve(mockCourseBuilderOutline()) : request<CourseBuilderOutline>(`/admin/courses/${courseId}/builder`),
  courseReadiness: (courseId: string) => request<CourseReadiness>(`/admin/courses/${courseId}/readiness`),
  createCourse: (payload: CourseCreatePayload) => (shouldUseMockData()
    ? Promise.resolve({
        status: 'ok',
        course: buildMockCourse(payload),
      })
    : request<{ status: string; course: Course }>('/admin/courses', {
      method: 'POST',
      body: JSON.stringify(payload),
      validate: parseCourseMutationResponse,
    })),
  deleteCourse: (courseId: string) => {
    if (shouldUseMockData()) {
      const course = mockFixtureCourses().find((item) => item.id === courseId);
      if (!course) return Promise.reject(new Error('课程不存在'));
      return Promise.resolve(mockDeleteCourse(course));
    }
    return request<{ status: string; course_id: string }>(`/admin/courses/${courseId}`, { method: 'DELETE' });
  },
  deletedCourses: () => (shouldUseMockData()
    ? Promise.resolve({ items: mockDeletedCourses() })
    : request<{ items: Course[] }>('/admin/courses/deleted', { validate: parseCourseListResponse })),
  restoreCourse: (courseId: string) => (shouldUseMockData()
    ? Promise.resolve(mockRestoreCourse(courseId))
    : request<{ status: string; course: Course }>(`/admin/courses/${courseId}/restore`, {
      method: 'POST',
      validate: parseCourseMutationResponse,
    })),
  purgeDeletedCourse: (courseId: string) => (shouldUseMockData()
    ? Promise.resolve({ status: mockPurgeDeletedCourse(courseId) ? 'ok' : 'not_found', course_id: courseId })
    : request<{ status: string; course_id: string }>(`/admin/courses/${courseId}/purge`, { method: 'DELETE' })),
  deleteCourseSection: (courseId: string, sectionId: string) =>
    request<{ status: string; course_id: string; section_id: string }>(`/admin/courses/${courseId}/sections/${sectionId}`, { method: 'DELETE' }),
  generateCourseFromAI: (payload: CourseGenerateFromAIPayload) => (shouldUseMockData()
    ? Promise.resolve(mockGenerateCourseFromAI(payload))
    : request<{ status: string; course: Course; sections_created: number; concepts_created: number; prerequisites_created: number; generated_by: string }>(
      '/admin/courses/generate-from-ai',
      { method: 'POST', body: JSON.stringify(payload) },
    )),
  importCourseOutline: (courseId: string, payload: CourseOutlineImportPayload) =>
    request<CourseOutlineImportResult>(`/admin/courses/${courseId}/outline/import`, { method: 'POST', body: JSON.stringify(payload) }),
  applyCourseOutline: (courseId: string, payload: CourseOutlineApplyPayload) =>
    request<{ status: string; mode: string; course: Course; sections_created: number; sections_updated: number; concepts_created: number; concepts_updated: number; paths_archived: boolean }>(
      `/admin/courses/${courseId}/outline/apply`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  updateCourse: (courseId: string, payload: CourseUpdatePayload) => (shouldUseMockData()
    ? Promise.resolve({
        status: 'ok',
        course_id: courseId,
        course: buildMockCourse({ status: 'published', ...payload }, courseId),
      })
    : request<{ status: string; course_id: string; course: Course }>(`/admin/courses/${courseId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      validate: parseCourseUpdateResponse,
    })),
  saveCourseSection: (courseId: string, payload: CourseSectionPayload, sectionId?: string) =>
    request<{ status: string; section: import('../types').CourseSection }>(`/admin/courses/${courseId}/sections${sectionId ? `/${sectionId}` : ''}`, {
      method: sectionId ? 'PUT' : 'POST',
      body: JSON.stringify(payload),
    }),
  createCourseConcept: (courseId: string, payload: CourseConceptPayload) =>
    request<{ status: string; concept: CourseConcept }>(`/admin/courses/${courseId}/concepts`, { method: 'POST', body: JSON.stringify(payload) }),
  updateCourseConcept: (courseId: string, conceptId: string, payload: Partial<CourseConceptPayload>) =>
    request<{ status: string; concept: CourseConcept }>(`/admin/courses/${courseId}/concepts/${conceptId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  path: (courseId: string) => shouldUseMockData()
    ? Promise.resolve({ course_id: courseId, items: mockFixturePathNodes() })
    : request<{ course_id: string; items: PathNode[] }>(`/courses/${courseId}/path`, { validate: parseLearningPathResponse }),
  generatePath: (courseId: string) => shouldUseMockData()
    ? Promise.resolve({ course_id: courseId, status: 'mocked', items: mockFixturePathNodes() })
    : request<{ course_id: string; status: string; items: PathNode[] }>(`/courses/${courseId}/path/generate`, {
      method: 'POST',
      validate: parseLearningPathGenerateResponse,
    }),
  updatePathNodeStatus: (nodeId: string, status: string) => shouldUseMockData()
    ? Promise.resolve({ node_id: nodeId, status, mastery_score: mockFixturePathNodes().find((node) => node.id === nodeId)?.mastery })
    : request<{ node_id: string; status: string; mastery_score?: number }>(`/path-nodes/${nodeId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
      validate: parsePathNodeStatusResponse,
    }),
  pathNodeMastery: (nodeId: string) => {
    if (shouldUseMockData()) {
      const node = mockFixturePathNodes().find((item) => item.id === nodeId);
      if (!node) return Promise.reject(new Error('学习路径节点不存在'));
      return Promise.resolve(parsePathNodeMastery({
        node_id: node.id,
        course_id: node.course_id,
        concept_id: node.concept_id,
        title: node.title,
        status: node.status,
        mastery: node.mastery,
        mastery_score: node.mastery_score ?? node.mastery,
        is_remedial: node.is_remedial,
        evidence: node.evidence ?? [],
        updated_at: node.updated_at,
      }));
    }
    return request<PathNodeMastery>(`/path-nodes/${nodeId}/mastery`, { validate: parsePathNodeMastery });
  },
  learningSchedules: (params?: { courseId?: string | null; startDate?: string; endDate?: string; status?: string }) => {
    if (shouldUseMockData()) {
      let items = readMockLearningSchedules();
      if (params?.courseId) items = items.filter((item) => item.course_id === params.courseId);
      if (params?.startDate) items = items.filter((item) => item.scheduled_date >= params.startDate!);
      if (params?.endDate) items = items.filter((item) => item.scheduled_date <= params.endDate!);
      if (params?.status) items = items.filter((item) => item.status === params.status);
      return Promise.resolve({ items, total: items.length } satisfies LearningScheduleListResponse);
    }
    const query = new URLSearchParams();
    if (params?.courseId) query.set('course_id', params.courseId);
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);
    if (params?.status) query.set('status', params.status);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<LearningScheduleListResponse>(`/learning-schedules${suffix}`);
  },
  createLearningSchedule: (payload: LearningSchedulePayload) => shouldUseMockData()
    ? Promise.resolve(createMockLearningSchedule(payload))
    : request<LearningScheduleItem>('/learning-schedules', { method: 'POST', body: JSON.stringify(payload) }),
  updateLearningSchedule: (itemId: string, payload: LearningScheduleUpdatePayload) => shouldUseMockData()
    ? Promise.resolve(updateMockLearningSchedule(itemId, payload))
    : request<LearningScheduleItem>(`/learning-schedules/${itemId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteLearningSchedule: (itemId: string) => shouldUseMockData()
    ? Promise.resolve({ status: 'deleted', item_id: itemId })
    : request<{ status: string; item_id: string }>(`/learning-schedules/${itemId}`, { method: 'DELETE' }),
  mastery: (courseId: string) => shouldUseMockData() ? Promise.resolve(buildMockMasterySummary(courseId)) : request<MasterySummary>(`/courses/${courseId}/mastery`),
  profile: (courseId: string) => shouldUseMockData() ? Promise.resolve(buildMockCourseProfile(courseId)) : request<CourseProfile>(`/courses/${courseId}/profile`),
  learningProfile: async (params?: LearningProfileParams) => {
    const courseId = params?.courseId ?? null;
    const courseTitle = params?.courseTitle ?? null;

    if (shouldUseMockData()) {
      return buildMockLearningProfileResponse({ courseId, courseTitle });
    }

    const query = new URLSearchParams();
    query.set('scope', params?.scope ?? 'all');
    if (courseId) query.set('course_id', courseId);
    if (params?.conversationId) query.set('conversation_id', params.conversationId);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<LearningProfileResponse>(`/learning-profile${suffix}`);
  },
  correctLearningProfile: (payload: ProfileCorrectionPayload) =>
    shouldUseMockData()
      ? Promise.resolve({ status: 'ok', scope: payload.scope, dimension_key: payload.dimension_key, evidence_id: payload.evidence_id ?? null })
      : request<{ status: string; scope: string; dimension_key: string; evidence_id?: string | null }>('/learning-profile/corrections', {
          method: 'POST',
          body: JSON.stringify(payload),
        }),
  /** 预设 chip 直写：不走 LLM，后端直接写入画像维度并返回下一轮模板话术 */
  submitOnboardingPresetChip: (payload: PresetChipSubmitRequest) =>
    request<PresetChipSubmitResponse>('/learning-profile/onboarding/submit-chip', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  resourceHall: (courseId?: string | null, params?: { q?: string; scope?: string; type?: string; difficulty?: string; page?: number; pageSize?: number }): Promise<ResourceHallResponse> => {
    if (shouldUseMockData()) return Promise.resolve(buildMockResourceHall(courseId, params));
    const query = new URLSearchParams();
    if (courseId) query.set('course_id', courseId);
    if (params?.q?.trim()) query.set('q', params.q.trim());
    if (params?.scope && params.scope !== 'all') query.set('scope', params.scope);
    if (params?.type && params.type !== 'all') query.set('type', params.type);
    if (params?.difficulty && params.difficulty !== 'all') query.set('difficulty', params.difficulty);
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('page_size', String(params.pageSize));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<ResourceHallResponse>(`/resources/hall${suffix}`);
  },
  resources: (courseId?: string | null, params?: { concept_id?: string | null }) => {
    if (shouldUseMockData()) {
      const items = params?.concept_id
        ? listMockResources().filter((item) => item.concept_id === params.concept_id)
        : listMockResources();
      const visibleItems = items.filter((item) => !mockDeletedResourceIds.has(item.id));
      return Promise.resolve({
        items: courseId ? visibleItems.filter((item) => !item.course_id || item.course_id === courseId) : visibleItems,
      });
    }
    const query = new URLSearchParams();
    if (courseId) query.set('course_id', courseId);
    if (params?.concept_id) query.set('concept_id', params.concept_id);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: Resource[] }>(`/resources${suffix}`);
  },
  communityResources: (courseId?: string | null, params?: { concept_id?: string; type?: string; difficulty?: string }): Promise<{ items: Resource[]; filters: Record<string, string | null | undefined> }> => {
    if (shouldUseMockData()) return Promise.resolve({ items: [], filters: { course_id: courseId, ...params } });
    const query = new URLSearchParams();
    if (courseId) query.set('course_id', courseId);
    if (params?.concept_id) query.set('concept_id', params.concept_id);
    if (params?.type) query.set('type', params.type);
    if (params?.difficulty) query.set('difficulty', params.difficulty);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: Resource[]; filters: Record<string, string | null | undefined> }>(`/resources/community/list${suffix}`);
  },
  uploadResourceReferenceImages: (files: File[], courseId?: string | null) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (courseId) formData.append('course_id', courseId);
    return shouldUseMockData()
      ? Promise.resolve<{ items: Resource['assets']; count: number }>({ items: [], count: 0 })
      : request<{ items: Resource['assets']; count: number }>('/resources/assets/references', {
        method: 'POST',
        body: formData,
        timeoutMs: 30_000,
      });
  },
  uploadResource: async (payload: ResourceUploadPayload): Promise<Resource> => {
    if (shouldUseMockData()) return createMockUploadedResource(payload);
    const formData = new FormData();
    formData.append('title', payload.title);
    formData.append('resource_type', payload.resourceType);
    formData.append('difficulty', payload.difficulty);
    formData.append('submit_for_review', payload.submitForReview ? 'true' : 'false');
    if (payload.summary?.trim()) formData.append('summary', payload.summary.trim());
    if (payload.content?.trim()) formData.append('content', payload.content.trim());
    if (payload.courseId) formData.append('course_id', payload.courseId);
    if (payload.conceptId) formData.append('concept_id', payload.conceptId);
    if (payload.pathNodeId) formData.append('path_node_id', payload.pathNodeId);
    if (payload.file) formData.append('file', payload.file);
    return request<Resource>('/resources/upload', {
      method: 'POST',
      body: formData,
      timeoutMs: 60_000,
    });
  },
  resourceAssetFile: (assetId: string) =>
    shouldUseMockData()
      ? Promise.resolve(new Blob())
      : requestBlob(`/resources/assets/${assetId}/file`, { timeoutMs: 60_000 }),
  generateResource: async (payload: ResourceGeneratePayload): Promise<ResourceGenerationTask> => shouldUseMockData()
    ? Promise.resolve(buildMockResourceGenerationTask(payload))
    : request<ResourceGenerationTask>('/resource-tasks', {
      method: 'POST',
      headers: { 'X-Idempotency-Key': await makeIdempotencyKey('resource-generation', payload) },
      body: JSON.stringify({
        ...payload,
        actionType: payload.actionType ?? 'resource_generation',
      }),
      validate: parseResourceGenerationTask,
      timeoutMs: 12_000,
    }),
  resourceTask: (taskId: string) => shouldUseMockData()
    ? Promise.resolve(buildMockResourceTask(taskId, {
      status: 'completed',
      course_id: 'deep_learning_001',
      scope: 'course',
      resource_type: 'lecture',
      progress: 100,
      steps: [
        { name: '课程检索 Agent', status: 'completed', detail: '已完成' },
        { name: '资源生成 Agent', status: 'completed', detail: '已保存资源' },
      ],
      draft_content: findMockResource('res_001').content ?? '# 示例讲义\n\n## 生成目标\n个性化学习资源示例',
      outline_json: [
        { id: 'section', level: 1, title: '示例讲义', order: 0 },
        { id: 'section-2', level: 2, title: '生成目标', order: 1 },
      ],
      result_resource_code: findMockResource('res_001').id,
    }))
    : request<ResourceGenerationTask>(`/resources/tasks/${taskId}`, { validate: parseResourceGenerationTask }),
  rerunResourceTask: (taskId: string, payload?: { needCourseEvidence?: boolean }) => shouldUseMockData()
    ? Promise.resolve<ResourceGenerationTask>({
      task_id: taskId,
      status: 'queued',
      resource_type: 'lecture',
      need_course_evidence: payload?.needCourseEvidence ?? false,
      course_evidence_required: payload?.needCourseEvidence ?? false,
      progress: 0,
      steps: [],
    })
    : request<ResourceGenerationTask>(`/resources/tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
      validate: parseResourceGenerationTask,
    }),
  cancelResourceTask: (taskId: string) => shouldUseMockData()
    ? Promise.resolve(buildMockResourceTask(taskId, { status: 'cancelled' }))
    : request<ResourceGenerationTask>(`/resources/tasks/${taskId}/cancel`, {
      method: 'POST',
      validate: parseResourceGenerationTask,
    }),
  updateResourceTaskOutline: (taskId: string, sections: Array<{ id: string; level: number; title: string; order: number }>) =>
    shouldUseMockData()
      ? Promise.resolve(buildMockResourceTask(taskId, { status: 'generating', outline_json: sections }))
      : request<ResourceGenerationTask>(`/resources/tasks/${taskId}/outline`, {
        method: 'PATCH',
        body: JSON.stringify({ sections }),
        validate: parseResourceGenerationTask,
      }),
  resourceTasks: (courseId: string) => shouldUseMockData() ? Promise.resolve({ items: [] }) : request<{ items: ResourceGenerationTask[] }>(`/resources/tasks?course_id=${courseId}`),
  resourceDetail: (resourceId: string) => shouldUseMockData()
    ? Promise.resolve(findMockResource(resourceId))
    : request<Resource>(`/resources/${resourceId}`),
  resourceVersions: (resourceId: string) => shouldUseMockData()
    ? Promise.resolve({ resource_id: resourceId, items: listMockResourceVersions(resourceId) })
    : request<{ resource_id: string; items: ResourceVersion[] }>(`/resources/${resourceId}/versions`),
  restoreResourceVersion: (resourceId: string, version: number) =>
    shouldUseMockData()
      ? Promise.resolve({
        ...findMockResource(resourceId),
        content:
          mockFixtureResourceVersions().find((item) => item.version === version)?.content
          ?? findMockResource(resourceId).content,
        latest_version: version,
      })
      : request<Resource>(`/resources/${resourceId}/versions/${version}/restore`, { method: 'POST' }),
  updateResource: (resourceId: string, payload: { title?: string; summary?: string; content?: string; status?: string; difficulty?: string }) => {
    if (shouldUseMockData()) {
      const item = findMockResource(resourceId);
      const next: Resource = { ...item, ...payload, updated_at: new Date().toISOString() };
      const uploadedIndex = mockUploadedResources.findIndex((resource) => resource.id === resourceId);
      if (uploadedIndex >= 0) mockUploadedResources[uploadedIndex] = next;
      if (payload.content != null) {
        const versions = mockUploadedResourceVersions.get(resourceId) ?? [];
        mockUploadedResourceVersions.set(resourceId, [
          {
            id: `${resourceId}-v${versions.length + 1}`,
            version: versions.length + 1,
            content: payload.content,
            meta: { source: 'manual_edit' },
            created_at: new Date().toISOString(),
          },
          ...versions,
        ]);
      }
      return Promise.resolve(next);
    }
    return request<Resource>(`/resources/${resourceId}`, { method: 'PUT', body: JSON.stringify(payload) });
  },
  deleteResource: (resourceId: string) => {
    if (shouldUseMockData()) {
      mockDeletedResourceIds.add(resourceId);
      return Promise.resolve({ resource_id: resourceId, status: 'deleted', deleted_at: new Date().toISOString() });
    }
    return request<{ resource_id: string; status: string; deleted_at?: string }>(`/resources/${resourceId}`, { method: 'DELETE' });
  },
  batchDeleteResources: (resourceIds: string[]): Promise<ResourceBatchDeleteResponse> => {
    if (shouldUseMockData()) {
      const deletedAt = new Date().toISOString();
      resourceIds.forEach((resourceId) => mockDeletedResourceIds.add(resourceId));
      return Promise.resolve({
        status: 'ok',
        deleted: resourceIds.map((resourceId) => ({ resource_id: resourceId, status: 'deleted', deleted_at: deletedAt })),
        rejected: [],
        deleted_count: resourceIds.length,
        rejected_count: 0,
      });
    }
    return request<ResourceBatchDeleteResponse>('/resources/batch', {
      method: 'DELETE',
      body: JSON.stringify({ resource_ids: resourceIds }),
    });
  },
  archiveResourceToCourse: (resourceId: string, payload: { course_id: string; concept_id?: string | null; path_node_id?: string | null }) =>
    shouldUseMockData()
      ? Promise.resolve({
        ...findMockResource(resourceId),
        course_id: payload.course_id,
        concept_id: payload.concept_id ?? null,
        path_node_id: payload.path_node_id ?? null,
        scope: 'course',
      })
      : request<Resource>(`/resources/${resourceId}/archive-course`, { method: 'POST', body: JSON.stringify(payload) }),
  copyResource: (resourceId: string) => shouldUseMockData() ? Promise.resolve({ ...findMockResource(resourceId), id: `${resourceId}-copy` }) : request<Resource>(`/resources/${resourceId}/copy`, { method: 'POST' }),
  submitCommunityResource: (resourceId: string) => shouldUseMockData() ? Promise.resolve({ resource_id: resourceId, status: 'pending_review' }) : request<{ resource_id: string; status: string }>(`/resources/${resourceId}/submit-community`, { method: 'POST' }),

  resourceReviewStats: (courseId: string) => {
    const query = new URLSearchParams({ course_id: courseId });
    return request<ResourceReviewStats>(`/admin/resources/review/stats?${query.toString()}`);
  },
  resourceReviewQueue: (courseId: string, status = 'all') => {
    const query = new URLSearchParams({ course_id: courseId, status });
    return request<{ items: Resource[] }>(`/admin/resources/review?${query.toString()}`);
  },
  resourceReviewDetail: (resourceId: string) => request<Resource>(`/admin/resources/review/${encodeURIComponent(resourceId)}`),
  resourceReviewLogs: (courseId?: string | null, resourceId?: string | null, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (courseId) query.set('course_id', courseId);
    if (resourceId) query.set('resource_id', resourceId);
    return request<{ items: ResourceReviewLog[] }>(`/admin/resources/review/logs?${query.toString()}`);
  },
  reviewResource: (resourceId: string, payload: ResourceReviewPayload) => request<Resource>(`/admin/resources/review/${encodeURIComponent(resourceId)}`, { method: 'POST', body: JSON.stringify(payload) }),
  submitAssessment: async (payload: AssessmentPayload) => shouldUseMockData()
    ? Promise.resolve(buildMockAssessmentResult())
    : request<AssessmentResult>('/assessments', {
      method: 'POST',
      headers: { 'X-Idempotency-Key': await makeIdempotencyKey('assessment-submit', payload) },
      body: JSON.stringify(payload),
    }),
  generateAssessmentDraft: async (payload: AssessmentDraftPayload) => request<AssessmentDraftResponse>('/assessments/draft', {
    method: 'POST',
    headers: { 'X-Idempotency-Key': await makeIdempotencyKey('assessment-draft', payload) },
    body: JSON.stringify(payload),
    timeoutMs: 60_000,
  }),
  conversations: (courseId: string) =>
    shouldUseMockData()
      ? Promise.resolve(buildEmptyConversationHistory(courseId))
      : request<ConversationHistoryResponse>(`/conversations?course_id=${encodeURIComponent(courseId)}`),
  conversationsGeneral: () =>
    shouldUseMockData()
      ? Promise.resolve(buildEmptyConversationHistory('general'))
      : request<ConversationHistoryResponse>('/conversations?scope=general'),
  conversationMessages: (conversationId: string) =>
    shouldUseMockData()
      ? Promise.resolve(buildEmptyConversationMessages(conversationId))
      : request<ConversationMessagesResponse>(`/conversations/${encodeURIComponent(conversationId)}/messages`),
  deleteConversation: (conversationId: string) =>
    shouldUseMockData()
      ? Promise.resolve({ status: 'deleted', conversation_id: conversationId })
      : request<{ status: string; conversation_id: string }>(`/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' }),
  renameConversation: (conversationId: string, title: string) =>
    shouldUseMockData()
      ? Promise.resolve({ id: conversationId, title })
      : request<{ id: string; title: string }>(`/conversations/${encodeURIComponent(conversationId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
  chat: (payload: ChatPayload) => {
    const isGeneral = payload.learning_scope === 'general' || !payload.course_id;
    if (shouldUseMockData()) {
      return Promise.resolve(buildMockChatResponse(payload));
    }
    return request<ChatResponse>('/ai/messages', {
      method: 'POST',
      body: JSON.stringify({
        response_mode: 'stream',
        mode: payload.mode ?? (payload.intent_type === 'COURSE_RAG_QA' || payload.intent_type === 'KNOWLEDGE_QA' ? 'course_rag_qa' : 'default_chat'),
        actionType: payload.actionType ?? (payload.intent_type === 'RESOURCE_GENERATION' ? 'resource_generation' : 'chat'),
        resourceType: payload.resourceType ?? payload.preferred_resource_type,
        needCourseEvidence: payload.needCourseEvidence ?? Boolean(!isGeneral && (payload.require_citations || payload.intent_type === 'COURSE_RAG_QA')),
        clientContext: payload.clientContext ?? {},
        require_citations: payload.require_citations ?? false,
        learning_scope: isGeneral ? 'general' : 'course',
        course_id: isGeneral ? null : payload.course_id,
        ...payload,
      }),
    });
  },
  metrics: () => request<Metrics>('/admin/metrics'),
  operationsDashboard: (courseId?: string | null, days = 7) => {
    const query = new URLSearchParams({ days: String(days) });
    if (courseId) query.set('course_id', courseId);
    return request<OperationsDashboard>(`/admin/operations/dashboard?${query.toString()}`);
  },
  modelProviderTemplates: () => (shouldUseMockData()
    ? Promise.resolve(mockModelProviderTemplates())
    : request<{ items: ModelProviderTemplate[] }>('/admin/model-providers/templates')),
  modelProviders: (capability: 'all' | 'chat' | 'embedding' | 'vision' | 'image' | 'image_generation' = 'all') => (shouldUseMockData()
    ? Promise.resolve(mockModelProviders())
    : request<{ items: ModelProviderHealth[] }>(
      `/admin/model-providers?capability=${capability}`,
      { validate: parseModelProviderHealthResponse },
    )),
  modelProviderIcons: () => (shouldUseMockData()
    ? Promise.resolve(mockModelProviderIcons())
    : request<{ items: ModelProviderIcon[] }>('/admin/model-providers/icons')),
  uploadModelProviderIcon: (file: File) => {
    if (shouldUseMockData()) {
      return Promise.resolve(buildMockModelProviderIcon(file));
    }
    const formData = new FormData();
    formData.append('file', file);
    return request<ModelProviderIcon>('/admin/model-providers/icons', { method: 'POST', body: formData });
  },
  deleteModelProviderIcon: (filename: string) => (shouldUseMockData()
    ? Promise.resolve({ filename, status: 'ok' })
    : request<{ filename: string; status: string }>(`/admin/model-providers/icons/${encodeURIComponent(filename)}`, { method: 'DELETE' })),
  modelProviderHealth: () => request<{ items: ModelProviderHealth[] }>(
    '/admin/model-providers/health',
    { validate: parseModelProviderHealthResponse },
  ),
  saveModelProvider: (payload: ModelProviderPayload, providerId?: string) => (shouldUseMockData()
    ? Promise.resolve({ status: 'ok', provider: payload.provider, display_name: payload.display_name })
    : request<{ status: string; provider: string; display_name?: string }>(`/admin/model-providers${providerId ? `/${providerId}` : ''}`, {
      method: providerId ? 'PUT' : 'POST',
      body: JSON.stringify(payload),
    })),
  deleteModelProvider: (providerId: string) => (shouldUseMockData()
    ? Promise.resolve({
      status: 'ok',
      provider: providerId,
      deleted_call_logs: 0,
      deleted_user_overrides: 0,
      cleared_course_bindings: 0,
    })
    : request<{
      status: string;
      provider: string;
      deleted_call_logs?: number;
      deleted_user_overrides?: number;
      cleared_course_bindings?: number;
    }>(`/admin/model-providers/${providerId}`, { method: 'DELETE' })),
  setDefaultProvider: (providerId: string) => (shouldUseMockData()
    ? Promise.resolve({ status: 'ok', provider: providerId, is_default: true })
    : request<{ status: string; provider: string; is_default: boolean }>(`/admin/model-providers/${providerId}/default`, { method: 'POST' })),
  reloadModelProviders: () => request<{ status: string; channel: string }>('/admin/model-providers/reload', { method: 'POST' }),
  modelProviderLogs: (filters: ModelProviderLogFilters = {}): Promise<ModelCallLogList> => {
    if (shouldUseMockData()) return Promise.resolve(mockModelProviderLogs());
    const query = new URLSearchParams({
      capability: filters.capability ?? 'all',
      days: String(filters.days ?? 7),
      limit: String(filters.limit ?? 100),
    });
    if (filters.provider) query.set('provider', filters.provider);
    if (filters.status) query.set('status', filters.status);
    if (filters.course_id) query.set('course_id', filters.course_id);
    if (filters.start_at) query.set('start_at', filters.start_at);
    if (filters.end_at) query.set('end_at', filters.end_at);
    if (filters.model_name) query.set('model_name', filters.model_name);
    if (filters.trace_id) query.set('trace_id', filters.trace_id);
    return request<ModelCallLogList>(`/admin/model-providers/logs?${query.toString()}`, {
      validate: parseModelCallLogListResponse,
    });
  },
  clearModelProviderLogs: (filters: ModelProviderLogFilters = {}) => {
    if (shouldUseMockData()) return Promise.resolve(mockClearModelProviderLogs());
    const query = new URLSearchParams({
      capability: filters.capability ?? 'all',
      days: String(filters.days ?? 7),
    });
    if (filters.provider) query.set('provider', filters.provider);
    if (filters.status) query.set('status', filters.status);
    if (filters.course_id) query.set('course_id', filters.course_id);
    if (filters.start_at) query.set('start_at', filters.start_at);
    if (filters.end_at) query.set('end_at', filters.end_at);
    if (filters.model_name) query.set('model_name', filters.model_name);
    if (filters.trace_id) query.set('trace_id', filters.trace_id);
    return request<ModelCallLogClearResult>(`/admin/model-providers/logs?${query.toString()}`, { method: 'DELETE' });
  },
  modelTraceDetail: (traceId: string) => (shouldUseMockData()
    ? Promise.reject(new Error('Mock 模式下无调用链路详情。'))
    : request<ModelTraceDetail>(
      `/admin/model-providers/traces/${encodeURIComponent(traceId)}`,
      { validate: parseModelTraceDetailResponse },
    )),
  testProvider: (providerId: string) => (shouldUseMockData()
    ? Promise.resolve({ status: 'passed', provider_id: providerId, message: 'Mock 连接测试通过。' } satisfies ProviderTestResult)
    : request<ProviderTestResult>(`/admin/model-providers/${providerId}/test`, { method: 'POST' })),
  testModelProviderDraft: (payload: ModelProviderPayload) => (shouldUseMockData()
    ? Promise.resolve({ status: 'passed', provider_id: payload.provider, message: 'Mock 草稿连接测试通过。' } satisfies ProviderTestResult)
    : request<ProviderTestResult>('/admin/model-providers/test', { method: 'POST', body: JSON.stringify(payload) })),
  userModelOverride: () => request<{
    provider: string | null;
    base_url: string | null;
    chat_model: string | null;
    embedding_model: string | null;
    enabled: boolean;
    key_configured: boolean;
  }>('/me/model-override'),
  saveUserModelOverride: (payload: {
    provider: string;
    base_url?: string | null;
    api_key?: string | null;
    clear_api_key?: boolean;
    chat_model: string;
    embedding_model?: string | null;
    enabled: boolean;
  }) => request<{
    provider: string | null;
    base_url: string | null;
    chat_model: string | null;
    embedding_model: string | null;
    enabled: boolean;
    key_configured: boolean;
  }>('/me/model-override', { method: 'PUT', body: JSON.stringify(payload) }),
  deleteUserModelOverride: () => request<{ status: string }>('/me/model-override', { method: 'DELETE' }),
  testUserModelOverride: (payload: {
    provider: string;
    base_url?: string | null;
    api_key?: string | null;
    chat_model: string;
  }) => request<ProviderTestResult>('/me/model-override/test', { method: 'POST', body: JSON.stringify(payload) }),
  checkAllModelProviders: () => (shouldUseMockData()
    ? Promise.resolve(buildMockProviderCheckAllResult())
    : request<ProviderCheckAllResult>('/admin/model-providers/check-all', { method: 'POST' })),
  modelProviderUsageStats: (params: {
    days?: number;
    start_at?: string;
    end_at?: string;
    capability?: string;
  } = {}): Promise<ModelProviderUsageStats> => {
    if (shouldUseMockData()) return Promise.resolve(mockModelProviderUsageStats());
    const query = new URLSearchParams({
      days: String(params.days ?? 30),
      capability: params.capability ?? 'all',
    });
    if (params.start_at) query.set('start_at', params.start_at);
    if (params.end_at) query.set('end_at', params.end_at);
    return request<ModelProviderUsageStats>(`/admin/model-providers/usage-stats?${query.toString()}`, {
      validate: parseModelProviderUsageStatsResponse,
    });
  },
  intentRouterConfig: () => (shouldUseMockData()
    ? Promise.resolve(mockIntentRouterConfig())
    : request<IntentRouterConfigView>('/admin/intent-router/config', { validate: parseIntentRouterConfigView })),
  saveIntentRouterConfig: (payload: { yaml_text?: string; config?: IntentRouterRegistryConfig }) => (shouldUseMockData()
    ? Promise.resolve({ ...mockIntentRouterConfig(), has_draft: true, draft_version: 'mock-draft' })
    : request<IntentRouterConfigView>('/admin/intent-router/config', {
      method: 'PUT',
      body: JSON.stringify(payload),
      validate: parseIntentRouterConfigView,
    })),
  validateIntentRouterConfig: (payload: { yaml_text?: string; config?: IntentRouterRegistryConfig }) => (shouldUseMockData()
    ? Promise.resolve({ ok: true, errors: [] } satisfies IntentRouterValidationResult)
    : request<IntentRouterValidationResult>('/admin/intent-router/config/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
      validate: parseIntentRouterValidationResult,
    })),
  evaluateIntentRouterConfig: (payload?: { yaml_text?: string; config?: IntentRouterRegistryConfig }) => (shouldUseMockData()
    ? Promise.resolve({
      total: 12,
      correct: 12,
      accuracy: 1,
      clarification_rate: 0.08,
      high_risk_false_positive: 0,
      by_intent: {},
    } satisfies IntentRouterEvalReport)
    : request<IntentRouterEvalReport>('/admin/intent-router/config/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
      validate: parseIntentRouterEvalReport,
    })),
  reloadIntentRouterConfig: () => (shouldUseMockData()
    ? Promise.resolve(mockIntentRouterConfig())
    : request<IntentRouterConfigView>('/admin/intent-router/config/reload', {
      method: 'POST',
      validate: parseIntentRouterConfigView,
    })),
  publishIntentRouterConfig: (payload?: { yaml_text?: string; config?: IntentRouterRegistryConfig }) => (shouldUseMockData()
    ? Promise.resolve({ ...mockIntentRouterConfig(), has_draft: false })
    : request<IntentRouterConfigView>('/admin/intent-router/config/publish', payload
      ? { method: 'POST', body: JSON.stringify(payload), validate: parseIntentRouterConfigView }
      : { method: 'POST', validate: parseIntentRouterConfigView })),
  rollbackIntentRouterConfig: () => (shouldUseMockData()
    ? Promise.resolve(mockIntentRouterConfig())
    : request<IntentRouterConfigView>('/admin/intent-router/config/rollback', {
      method: 'POST',
      validate: parseIntentRouterConfigView,
    })),
  exportIntentRouterConfig: () => (shouldUseMockData()
    ? Promise.resolve(new Blob([mockIntentRouterYaml], { type: 'application/x-yaml' }))
    : requestBlob('/admin/intent-router/config/export')),
  importIntentRouterConfig: (file: File) => {
    if (shouldUseMockData()) return Promise.resolve({ ...mockIntentRouterConfig(), has_draft: true, draft_version: 'mock-import' });
    const formData = new FormData();
    formData.append('file', file);
    return request<IntentRouterConfigView>('/admin/intent-router/config/import', {
      method: 'POST',
      body: formData,
      validate: parseIntentRouterConfigView,
    });
  },
  courseModelConfig: (courseId: string) => (shouldUseMockData()
    ? Promise.resolve(mockCourseModelConfig(courseId))
    : request<CourseModelConfig>(`/admin/courses/${courseId}/model-config`)),
  updateCourseModelConfig: (courseId: string, payload: Partial<CourseModelConfig>) => (shouldUseMockData()
    ? Promise.resolve(mockUpdateCourseModelConfig(courseId, payload))
    : request<CourseModelConfig>(`/admin/courses/${courseId}/model-config`, { method: 'PUT', body: JSON.stringify(payload) })),
  knowledgeDocuments: (courseId: string) => request<{ course_id: string; items: KnowledgeDocument[] }>(
    `/admin/courses/${courseId}/documents`,
    { validate: parseKnowledgeDocumentListResponse },
  ),
  courseKnowledgeDocuments: (courseId: string): Promise<{ course_id: string; items: KnowledgeDocument[] }> => (shouldUseMockData()
    ? Promise.resolve({ course_id: courseId, items: mockKnowledgeDocumentsMerged(courseId).items })
    : request<{ course_id: string; items: KnowledgeDocument[] }>(
      `/courses/${courseId}/documents`,
      { validate: parseKnowledgeDocumentListResponse },
    )),
  knowledgeDocumentsScoped: (courseId?: string | null) => {
    if (shouldUseMockData()) {
      return Promise.resolve(mockKnowledgeDocumentsMerged(courseId));
    }
    const query = new URLSearchParams();
    if (courseId) query.set('course_id', courseId);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<{
      scope: 'all' | 'course';
      course_id?: string | null;
      course_title?: string | null;
      total: number;
      items: KnowledgeDocument[];
    }>(`/admin/knowledge/documents${suffix}`, { validate: parseKnowledgeDocumentScopedListResponse });
  },
  knowledgeUploadPolicy: () => (shouldUseMockData()
    ? Promise.resolve(mockKnowledgeUploadPolicy())
    : request<KnowledgeUploadPolicy>('/admin/knowledge/upload-policy', { validate: parseKnowledgeUploadPolicy })),
  uploadKnowledgeDocument: (
    courseId: string,
    file: File,
    options?: {
      integrationKey?: string;
      pipelineStageJson?: Record<string, unknown>;
      forceReupload?: boolean;
      timeoutMs?: number;
    },
  ) => {
    if (shouldUseMockData()) {
      return Promise.resolve(mockUploadKnowledgeDocument(courseId, file));
    }
    const formData = new FormData();
    formData.append('file', file);
    if (options?.integrationKey) formData.append('integration_key', options.integrationKey);
    if (options?.pipelineStageJson) {
      formData.append('pipeline_stage_json', JSON.stringify(options.pipelineStageJson));
    }
    if (options?.forceReupload) formData.append('force_reupload', 'true');
    return request<DocumentUploadResult>(`/admin/courses/${courseId}/documents`, {
      method: 'POST',
      body: formData,
      timeoutMs: options?.timeoutMs
        ?? Number(import.meta.env.VITE_KNOWLEDGE_UPLOAD_TIMEOUT_MS ?? 180_000),
      validate: parseDocumentUploadResult,
    });
  },
  chatdocConfig: (templateKey?: string) => (shouldUseMockData()
    ? Promise.resolve(mockChatdocConfig(templateKey))
    : (() => {
      const query = templateKey ? `?template_key=${encodeURIComponent(templateKey)}` : '';
      return request<import('../types').ChatdocConfigView>(`/admin/chatdoc-config${query}`);
    })()),
  listChatdocConfigInstances: () => (shouldUseMockData()
    ? Promise.resolve(mockListChatdocConfigInstances())
    : request<{ items: import('../types').ChatdocConfigView[]; total: number; active_integration_key?: string }>(
      '/admin/chatdoc-config/instances',
    )),
  registerChatdocConfig: (templateKey: string) => (shouldUseMockData()
    ? Promise.resolve(mockRegisterChatdocInstance(templateKey))
    : request<import('../types').ChatdocConfigView & { status: string }>(
      `/admin/chatdoc-config/register?template_key=${encodeURIComponent(templateKey)}`,
      { method: 'POST' },
    )),
  ragIntegrationTemplates: () => (shouldUseMockData()
    ? Promise.resolve(mockRagIntegrationTemplates())
    : request<{ items: import('../types').RagIntegrationTemplate[] }>('/admin/rag-integration/templates')),
  updateChatdocConfig: (payload: {
    integration_key?: string;
    preset_template_key?: string;
    display_label?: string;
    set_active?: boolean;
    app_id?: string;
    base_url?: string;
    api_secret?: string;
    clear_api_secret?: boolean;
    wiki_filter_score?: number;
    pipeline_config_json?: Record<string, unknown> | null;
    is_active?: boolean;
    icon_file?: string;
  }) => (shouldUseMockData()
    ? Promise.resolve(mockUpdateChatdocConfig(payload))
    : request<import('../types').ChatdocConfigView>('/admin/chatdoc-config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })),
  testChatdocConfig: (templateKey?: string) => (shouldUseMockData()
    ? Promise.resolve({ ...mockChatdocConfig(templateKey), last_test_status: 'passed', last_test_message: 'Mock 连接测试通过。' })
    : (() => {
      const query = templateKey ? `?template_key=${encodeURIComponent(templateKey)}` : '';
      return request<import('../types').ChatdocConfigView>(`/admin/chatdoc-config/test${query}`, { method: 'POST' });
    })()),
  testChatdocConfigDraft: (payload: {
    integration_key?: string;
    preset_template_key?: string;
    display_label?: string;
    app_id?: string;
    base_url?: string;
    api_secret?: string;
    wiki_filter_score?: number;
    pipeline_config_json?: Record<string, unknown> | null;
    is_active?: boolean;
  }) => (shouldUseMockData()
    ? Promise.resolve({ ...mockUpdateChatdocConfig(payload), last_test_status: 'passed', last_test_message: 'Mock 草稿连接测试通过。' })
    : request<import('../types').ChatdocConfigView>('/admin/chatdoc-config/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    })),
  deleteChatdocConfig: (templateKey: string) => (shouldUseMockData()
    ? Promise.resolve(mockDeleteChatdocConfig(templateKey))
    : request<import('../types').ChatdocConfigView & { status: string; removed?: boolean }>(
      `/admin/chatdoc-config?template_key=${encodeURIComponent(templateKey)}`,
      { method: 'DELETE' },
    )),
  chatdocVendorQuota: (templateKey: string) => (shouldUseMockData()
    ? Promise.resolve(mockChatdocVendorQuota(templateKey))
    : request<import('../types').ChatdocVendorQuotaView>(
      `/admin/chatdoc-config/vendor-quota?template_key=${encodeURIComponent(templateKey)}`,
    )),
  updateChatdocVendorQuota: (
    templateKey: string,
    payload: {
      upload_limit_pages?: number | null;
      doc_qa_limit?: number | null;
      extract_limit?: number | null;
      package_note?: string | null;
    },
  ) => (shouldUseMockData()
    ? Promise.resolve({ ...mockChatdocVendorQuota(templateKey), ...payload })
    : request<import('../types').ChatdocVendorQuotaView>(
      `/admin/chatdoc-config/vendor-quota?template_key=${encodeURIComponent(templateKey)}`,
      {
        method: 'PUT',
        body: JSON.stringify(payload),
      },
    )),
  resetChatdocVendorQuotaUsed: (
    templateKey: string,
    payload: {
      upload_used_pages?: number;
      doc_qa_used?: number;
      extract_used?: number;
    },
  ) => (shouldUseMockData()
    ? Promise.resolve({
      ...mockChatdocVendorQuota(templateKey),
      items: mockChatdocVendorQuota(templateKey).items.map((item) => {
        if (item.key === 'upload' && payload.upload_used_pages != null) return { ...item, used: payload.upload_used_pages };
        if (item.key === 'doc_qa' && payload.doc_qa_used != null) return { ...item, used: payload.doc_qa_used };
        if (item.key === 'extract' && payload.extract_used != null) return { ...item, used: payload.extract_used };
        return item;
      }),
    })
    : request<import('../types').ChatdocVendorQuotaView>(
      `/admin/chatdoc-config/vendor-quota/reset-used?template_key=${encodeURIComponent(templateKey)}`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )),
  chatdocDocumentChunks: (documentId: string, params?: { limit?: number; offset?: number }) => {
    if (shouldUseMockData()) {
      return Promise.resolve(mockChatdocDocumentChunks(documentId, params));
    }
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<import('../types').ChatDocChunksResponse>(`/admin/documents/${documentId}/chatdoc-chunks${suffix}`);
  },
  nativeChunks: (documentId: string, params?: { limit?: number; offset?: number; page?: number }) => {
    if (shouldUseMockData()) return Promise.resolve(mockNativeChunks(documentId, params));
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    if (params?.page) query.set('page', String(params.page));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<import('../types').NativeChunkListResponse>(`/admin/documents/${documentId}/native-chunks${suffix}`);
  },
  nativeChunkRevisions: (documentId: string) =>
    request<import('../types').NativeChunkRevisionListResponse>(
      `/admin/documents/${documentId}/native-chunks/revisions`,
    ),
  restoreNativeChunkRevision: (documentId: string, revisionId: string) =>
    request<Record<string, unknown>>(
      `/admin/documents/${documentId}/native-chunks/revisions/${revisionId}/restore`,
      { method: 'POST' },
    ),
  fetchDocumentFile: (documentId: string) => requestBlob(`/admin/documents/${documentId}/file`),
  fetchCourseDocumentFile: (courseId: string, documentId: string) => requestBlob(`/courses/${courseId}/documents/${documentId}/file`),
  syncNativeChunks: (documentId: string) =>
    request<import('../types').NativeChunkSyncResponse>(`/admin/documents/${documentId}/native-chunks/sync`, {
      method: 'POST',
    }),
  resplitNativeChunks: (
    documentId: string,
    body?: { integration_key?: string; split_body?: Record<string, unknown>; sync_after?: boolean },
  ) =>
    request<{ status: string; vendor?: Record<string, unknown>; sync?: Record<string, unknown> }>(
      `/admin/documents/${documentId}/native-chunks/resplit`,
      { method: 'POST', body: JSON.stringify(body ?? { sync_after: true }) },
    ),
  updateNativeChunk: (
    chunkId: string,
    body: { content?: string; tags?: string[]; page?: number },
  ) =>
    request<import('../types').NativeChunkItem>(`/admin/native-chunks/${chunkId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  embedNativeChunksDocument: (documentId: string, integrationKey?: string) =>
    request<{
      accepted: Array<{ document_id: string; iflytek_file_id?: string }>;
      rejected: Array<{ document_id: string; reason?: string }>;
    }>(`/admin/documents/${documentId}/native-chunks/embed`, {
      method: 'POST',
      body: JSON.stringify({ integration_key: integrationKey }),
    }),
  knowledgeIngestionStatus: (documentId: string) => (shouldUseMockData()
    ? Promise.resolve(mockKnowledgeIngestionStatus(documentId))
    : request<IngestionStatus>(`/admin/documents/${documentId}/ingestion-status`, { validate: parseIngestionStatus })),
  coursesWithKnowledge: () => (shouldUseMockData()
    ? Promise.resolve({ course_ids: mockActiveCourses().map((course) => course.id) })
    : request<{ course_ids: string[] }>('/courses/with-knowledge', { validate: parseCoursesWithKnowledgeResponse })),
  deleteKnowledgeDocument: (documentId: string) => (shouldUseMockData()
    ? Promise.resolve(mockDeleteKnowledgeDocument(documentId))
    : request<{ status: string; document_id: string; title?: string | null; filename?: string | null }>(
      `/admin/documents/${documentId}`,
      { method: 'DELETE', validate: parseKnowledgeDocumentActionResponse },
    )),
  listRecycledKnowledgeDocuments: (courseId?: string | null) => {
    if (shouldUseMockData()) {
      return Promise.resolve({ total: 0, items: [] });
    }
    const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : '';
    return request<{ total: number; items: KnowledgeDocument[] }>(
      `/admin/knowledge/documents/recycled${query}`,
      { validate: parseRecycledKnowledgeDocumentListResponse },
    );
  },
  restoreKnowledgeDocument: (documentId: string) =>
    request<{ document_id: string; status: string; title?: string | null }>(
      `/admin/documents/${documentId}/restore`,
      { method: 'POST', validate: parseKnowledgeDocumentActionResponse },
    ),
  purgeKnowledgeDocument: (documentId: string, syncChatdoc = true) =>
    request<{ status: string; document_id: string; chatdoc?: Record<string, unknown> }>(
      `/admin/documents/${documentId}/purge?sync_chatdoc=${syncChatdoc ? 'true' : 'false'}`,
      { method: 'POST', validate: parseKnowledgeDocumentActionResponse },
    ),
  purgeCourse: (courseId: string, syncChatdoc = true) => (shouldUseMockData()
    ? Promise.resolve({ status: mockPurgeDeletedCourse(courseId) ? 'ok' : 'not_found', course_id: courseId })
    : request<{ status: string; course_id: string; title?: string; documents_purged?: string[] }>(
      `/admin/courses/${courseId}?purge=true&sync_chatdoc=${syncChatdoc ? 'true' : 'false'}`,
      { method: 'DELETE' },
    )),
  batchEmbedKnowledgeDocuments: (
    documentIds: string[],
    options?: { integrationKey?: string; pipelineStageJson?: Record<string, unknown> },
  ) => (shouldUseMockData()
    ? Promise.resolve({
      accepted: documentIds.map((document_id) => ({ document_id, iflytek_file_id: 'mock-file-id' })),
      rejected: [],
      target_status: 'ready',
      message: 'Mock 批量向量化已受理。',
    })
    : request<{
      accepted: Array<{ document_id: string; iflytek_file_id?: string | null }>;
      rejected: Array<{ document_id: string; iflytek_file_id?: string | null; reason?: string | null }>;
      target_status: string;
      message: string;
    }>('/admin/knowledge/documents/batch-embed', {
      method: 'POST',
      body: JSON.stringify({
        document_ids: documentIds,
        integration_key: options?.integrationKey,
        pipeline_stage_json: options?.pipelineStageJson,
      }),
    })),
  extractKnowledgeDocuments: (
    documentIds: string[],
    options?: { integrationKey?: string; pipelineStageJson?: Record<string, unknown> },
  ) => (shouldUseMockData()
    ? Promise.resolve({
      accepted: documentIds.map((document_id) => ({ document_id, iflytek_file_id: 'mock-file-id' })),
      rejected: [],
      message: 'Mock 批量抽取已受理。',
    })
    : request<{
      accepted: Array<{ document_id: string; iflytek_file_id?: string | null }>;
      rejected: Array<{ document_id: string; iflytek_file_id?: string | null; reason?: string | null }>;
      message: string;
    }>('/admin/knowledge/documents/extract', {
      method: 'POST',
      body: JSON.stringify({
        document_ids: documentIds,
        integration_key: options?.integrationKey,
        pipeline_stage_json: options?.pipelineStageJson,
      }),
    })),
  searchKnowledge: (courseId: string, q: string, params?: { limit?: number; mode?: 'keyword' | 'vector' | 'page' | 'hybrid'; concept_id?: string; document_id?: string; asset_type?: string; include_stale?: boolean; include_failed?: boolean; integration_key?: string; pipeline_stage_json?: Record<string, unknown>; wiki_filter_score?: number }): Promise<KnowledgeSearchResponse> => {
    if (shouldUseMockData()) return Promise.resolve(mockSearchKnowledge(courseId, q));
    const query = new URLSearchParams({ course_id: courseId, q });
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.mode) query.set('mode', params.mode);
    if (params?.concept_id) query.set('concept_id', params.concept_id);
    if (params?.document_id) query.set('document_id', params.document_id);
    if (params?.asset_type) query.set('asset_type', params.asset_type);
    if (params?.include_stale !== undefined) query.set('include_stale', String(params.include_stale));
    if (params?.include_failed !== undefined) query.set('include_failed', String(params.include_failed));
    if (params?.integration_key) query.set('integration_key', params.integration_key);
    if (params?.pipeline_stage_json) query.set('pipeline_stage_json', JSON.stringify(params.pipeline_stage_json));
    if (params?.wiki_filter_score != null) query.set('wiki_filter_score', String(params.wiki_filter_score));
    return request<KnowledgeSearchResponse>(`/admin/knowledge/search?${query.toString()}`, {
      validate: parseKnowledgeSearchResponse,
    });
  },
  executeSandbox: (payload: { code: string; language?: 'python' }): Promise<SandboxExecuteResponse> =>
    request<SandboxExecuteResponse>('/sandbox/execute', {
      method: 'POST',
      body: JSON.stringify({ code: payload.code, language: payload.language ?? 'python' }),
    }),
};
