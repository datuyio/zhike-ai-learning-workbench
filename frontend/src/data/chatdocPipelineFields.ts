/** 讯飞 ChatDoc 流水线各阶段可配置字段（来源：chatdoc.xfyun.cn/docs V2） */

export type ChatdocPipelineStageId =
  | 'auth'
  | 'upload_preprocess'
  | 'extract_embed'
  | 'retrieval'
  | 'qa_query';

export type ChatdocPipelineFieldType = 'text' | 'number' | 'boolean' | 'select' | 'string_list';

export type ChatdocPipelineFieldDef = {
  key: string;
  label: string;
  description?: string;
  type: ChatdocPipelineFieldType;
  defaultValue?: string | number | boolean;
  options?: Array<{ value: string; label: string }>;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  /** 默认勾选并写入 JSON */
  enabledByDefault?: boolean;
  /** 始终写入 JSON，不可取消 */
  locked?: boolean;
  /** 嵌套路径，如 chatExtends.wikiFilterScore */
  jsonPath: string[];
  /** 仅当依赖字段等于指定值时，才允许勾选配置 */
  dependsOn?: { field: string; equals: string | boolean };
  /** 表单分组，用于折叠/分区展示 */
  group?: 'custom_split';
  /** 紧凑模式下显示的短标签 */
  displayLabel?: string;
};

export type ChatdocPipelineStageDef = {
  id: ChatdocPipelineStageId;
  label: string;
  shortLabel: string;
  endpoint: string;
  method: string;
  hint: string;
  docAnchor?: string;
  fields: ChatdocPipelineFieldDef[];
};

const RETRIEVAL_FILTER_OPTIONS = [
  { value: 'STRICT', label: 'STRICT · 严格' },
  { value: 'REGULAR', label: 'REGULAR · 正常' },
  { value: 'LENIENT', label: 'LENIENT · 宽松' },
  { value: 'OFF', label: 'OFF · 关闭' },
] as const;

const QA_MODE_OPTIONS = [
  { value: 'QA_FIRST', label: 'QA_FIRST · QA 对优先' },
  { value: 'QA_SUMMARY', label: 'QA_SUMMARY · QA 总结' },
  { value: 'MIX', label: 'MIX · 混合' },
  { value: 'WIKI_ONLY', label: 'WIKI_ONLY · 仅 Wiki' },
] as const;

const PARSE_TYPE_OPTIONS = [
  { value: 'AUTO', label: 'AUTO · 智能判断 OCR' },
  { value: 'TEXT', label: 'TEXT · 直接读文本' },
  { value: 'OCR', label: 'OCR · 强制 OCR' },
] as const;

const EMB_TYPE_OPTIONS = [
  { value: 'QA', label: 'QA · 问题+答案' },
  { value: 'Q', label: 'Q · 仅问题' },
] as const;

export const CHATDOC_PIPELINE_STAGES: ChatdocPipelineStageDef[] = [
  {
    id: 'auth',
    label: '基础认证与通用',
    shortLabel: '鉴权',
    endpoint: 'chatdoc.xfyun.cn',
    method: 'Header / WSS Query',
    hint: 'HTTP 接口在 Header 携带 appId、timestamp、signature；WebSocket 文档问答在 URL Query 携带相同三参数。',
    docAnchor: 'https://chatdoc.xfyun.cn/docs#/docs/1.2快速接入.md',
    fields: [
      {
        key: 'appId',
        label: 'appId',
        description: '控制台应用 ID',
        type: 'text',
        placeholder: '{{APP_ID}}',
        locked: true,
        enabledByDefault: true,
        jsonPath: ['headers', 'appId'],
      },
      {
        key: 'timestamp',
        label: 'timestamp',
        description: 'Unix 秒级时间戳，与服务端相差不超过 5 分钟',
        type: 'text',
        placeholder: '{{UNIX_TIMESTAMP}}',
        locked: true,
        enabledByDefault: true,
        jsonPath: ['headers', 'timestamp'],
      },
      {
        key: 'signature',
        label: 'signature',
        description: 'HMAC-SHA1(MD5(appId+timestamp), APISecret) → Base64',
        type: 'text',
        placeholder: '{{SIGNATURE}}',
        locked: true,
        enabledByDefault: true,
        jsonPath: ['headers', 'signature'],
      },
      {
        key: 'domain',
        label: 'domain',
        description: '接口域名',
        type: 'text',
        defaultValue: 'chatdoc.xfyun.cn',
        locked: true,
        enabledByDefault: true,
        jsonPath: ['domain'],
      },
    ],
  },
  {
    id: 'upload_preprocess',
    label: '文档上传与预处理',
    shortLabel: '上传',
    endpoint: '/openapi/v1/file/upload · /openapi/v1/file/split',
    method: 'POST multipart · POST JSON',
    hint: '默认讯飞内置 wiki 切分（isSplitDefault=true，不传 extend）；不满意再开自定义。',
    docAnchor: 'https://chatdoc.xfyun.cn/docs#/docs/api/2.1文档接口列表?id=_1-文档上传',
    fields: [
      {
        key: 'fileType',
        label: 'fileType',
        displayLabel: '文档类型',
        description: '知识库文档传 wiki（与官方一致）',
        type: 'text',
        defaultValue: 'wiki',
        enabledByDefault: true,
        jsonPath: ['fileType'],
      },
      {
        key: 'parseType',
        label: 'parseType',
        displayLabel: '解析方式',
        description: 'PDF、Word 如何提取文字',
        type: 'select',
        defaultValue: 'AUTO',
        options: [...PARSE_TYPE_OPTIONS],
        enabledByDefault: true,
        jsonPath: ['parseType'],
      },
      {
        key: 'stepByStep',
        label: 'stepByStep',
        displayLabel: '分步处理',
        description: '开启后只切分不向量化，需手动激活',
        type: 'boolean',
        defaultValue: true,
        enabledByDefault: true,
        jsonPath: ['stepByStep'],
      },
      {
        key: 'callbackUrl',
        label: 'callbackUrl',
        displayLabel: '状态回调',
        description:
          '文档各阶段状态变化时，讯飞会 GET 通知此地址。本系统适用：前端手动上传、页面查看状态、手动触发向量化、手动核对切片，此项留空即可。',
        type: 'text',
        placeholder: 'https://your-api/webhooks/chatdoc/status',
        jsonPath: ['callbackUrl'],
      },
      {
        key: 'isSplitDefault',
        label: 'isSplitDefault (split)',
        displayLabel: '切分方式',
        description: 'true 用官方切分；false 才启用下方自定义',
        type: 'boolean',
        defaultValue: true,
        enabledByDefault: true,
        jsonPath: ['isSplitDefault'],
      },
      {
        key: 'chunkSize',
        label: 'wikiSplitExtends.chunkSize',
        displayLabel: '最大段长',
        description: '每段最多多少字（官方默认 2000）',
        type: 'number',
        defaultValue: 2000,
        min: 256,
        max: 8000,
        group: 'custom_split',
        dependsOn: { field: 'isSplitDefault', equals: 'false' },
        jsonPath: ['extend', 'wikiSplitExtends', 'chunkSize'],
      },
      {
        key: 'minChunkSize',
        label: 'wikiSplitExtends.minChunkSize',
        displayLabel: '最短段长',
        description: '短于该长度会向下段聚合（官方默认 200）',
        type: 'number',
        defaultValue: 200,
        min: 64,
        max: 2000,
        group: 'custom_split',
        dependsOn: { field: 'isSplitDefault', equals: 'false' },
        jsonPath: ['extend', 'wikiSplitExtends', 'minChunkSize'],
      },
      {
        key: 'chunkSeparators',
        label: 'wikiSplitExtends.chunkSeparators',
        displayLabel: '切分符号',
        description: '在哪些符号处切分，默认空行（\\n\\n）',
        type: 'string_list',
        defaultValue: 'DQo=',
        placeholder: '默认空行，每行一个',
        group: 'custom_split',
        dependsOn: { field: 'isSplitDefault', equals: 'false' },
        jsonPath: ['extend', 'wikiSplitExtends', 'chunkSeparators'],
      },
    ],
  },
  {
    id: 'extract_embed',
    label: '文档萃取与向量化',
    shortLabel: '萃取',
    endpoint: '/openapi/v1/qa/extract · /openapi/v1/file/embedding · /openapi/v1/qa/apply',
    method: 'POST JSON · POST form · POST JSON',
    hint: 'vectored 状态文档可提交萃取；splited 状态可 batch-embed；apply 将 QA 对写入索引。',
    docAnchor: 'https://chatdoc.xfyun.cn/docs#/docs/api/5.1萃取接口列表?id=_1-文档萃取',
    fields: [
      {
        key: 'extract_chunkSize',
        label: 'chunkSize (extract)',
        description: '萃取分块长度',
        type: 'number',
        defaultValue: 2000,
        min: 512,
        max: 8000,
        enabledByDefault: true,
        jsonPath: ['extract', 'chunkSize'],
      },
      {
        key: 'numPerChunk',
        label: 'numPerChunk',
        description: '每分块抽取问题数（非 100% 精确）',
        type: 'number',
        defaultValue: 2,
        min: 1,
        max: 10,
        enabledByDefault: true,
        jsonPath: ['extract', 'numPerChunk'],
      },
      {
        key: 'answerSize',
        label: 'answerSize',
        description: '答案长度上限（非 100% 精确）',
        type: 'number',
        defaultValue: 200,
        min: 50,
        max: 2000,
        jsonPath: ['extract', 'answerSize'],
      },
      {
        key: 'includeAnswer',
        label: 'includeAnswer',
        type: 'boolean',
        defaultValue: true,
        jsonPath: ['extract', 'includeAnswer'],
      },
      {
        key: 'topicPreference',
        label: 'topicPreference',
        description: '主题偏好，JSON 数组字符串',
        type: 'text',
        placeholder: '["深度学习","考试重点"]',
        jsonPath: ['extract', 'topicPreference'],
      },
      {
        key: 'notifyUrl',
        label: 'notifyUrl (extract)',
        type: 'text',
        placeholder: 'https://your-api/webhooks/chatdoc/extract',
        jsonPath: ['extract', 'notifyUrl'],
      },
      {
        key: 'embType',
        label: 'embType (apply)',
        description: 'QA 对向量类型',
        type: 'select',
        defaultValue: 'QA',
        options: [...EMB_TYPE_OPTIONS],
        jsonPath: ['apply', 'embType'],
      },
    ],
  },
  {
    id: 'retrieval',
    label: '检索过滤与排序',
    shortLabel: '检索',
    endpoint: '/openapi/v1/vector/search',
    method: 'POST JSON',
    hint: '智课未来学习室与管理端「检索测试」主链路；结果按 score 降序，retrievalFilterPolicy 控制过滤强度。',
    docAnchor: 'https://chatdoc.xfyun.cn/docs#/docs/api/2.1文档接口列表?id=_5-文档内容相似度检索',
    fields: [
      {
        key: 'topN',
        label: 'topN',
        description: '向量库召回条数',
        type: 'number',
        defaultValue: 5,
        min: 1,
        max: 20,
        enabledByDefault: true,
        jsonPath: ['topN'],
      },
      {
        key: 'content',
        label: 'content',
        description: '检索问句（预览占位）',
        type: 'text',
        placeholder: '什么是跳字模型？',
        enabledByDefault: true,
        jsonPath: ['content'],
      },
      {
        key: 'embedding',
        label: 'embedding',
        description: '是否返回向量检索结果',
        type: 'boolean',
        defaultValue: true,
        enabledByDefault: true,
        jsonPath: ['embedding'],
      },
      {
        key: 'es',
        label: 'es',
        description: '是否并行 ES 全文检索',
        type: 'boolean',
        defaultValue: false,
        jsonPath: ['es'],
      },
      {
        key: 'wikiFilterScore',
        label: 'chatExtends.wikiFilterScore',
        description: 'Wiki 相似度阈值 (0–1)，低于丢弃；与管理端「检索相似度阈值」联动',
        type: 'number',
        defaultValue: 0.82,
        min: 0,
        max: 1,
        step: 0.01,
        enabledByDefault: true,
        jsonPath: ['chatExtends', 'wikiFilterScore'],
      },
      {
        key: 'esFilterScore',
        label: 'chatExtends.esFilterScore',
        description: 'ES 全文检索分数阈值',
        type: 'number',
        defaultValue: 10,
        min: 0,
        max: 100,
        jsonPath: ['chatExtends', 'esFilterScore'],
      },
      {
        key: 'retrievalFilterPolicy',
        label: 'chatExtends.retrievalFilterPolicy',
        description: '检索过滤级别，越严格剩余片段越少',
        type: 'select',
        defaultValue: 'REGULAR',
        options: [...RETRIEVAL_FILTER_OPTIONS],
        enabledByDefault: true,
        jsonPath: ['chatExtends', 'retrievalFilterPolicy'],
      },
    ],
  },
  {
    id: 'qa_query',
    label: '文档问答 / 检索',
    shortLabel: '问答',
    endpoint: '/openapi/v1/qa/query',
    method: 'POST JSON',
    hint: 'HTTP 文档问答与检索过滤参数；WebSocket 等价路径 ws://…/openapi/chat。过滤参数与 vector/search 的 chatExtends 对齐。',
    docAnchor: 'https://chatdoc.xfyun.cn/docs#/docs/api/4.1问答接口列表?id=_1-文档问答',
    fields: [
      {
        key: 'qa_topN',
        label: 'topN',
        description: '参与问答的最大文本段数，最大 10',
        type: 'number',
        defaultValue: 6,
        min: 1,
        max: 10,
        enabledByDefault: true,
        jsonPath: ['topN'],
      },
      {
        key: 'qa_retrievalFilterPolicy',
        label: 'chatExtends.retrievalFilterPolicy',
        type: 'select',
        defaultValue: 'REGULAR',
        options: [...RETRIEVAL_FILTER_OPTIONS],
        enabledByDefault: true,
        jsonPath: ['chatExtends', 'retrievalFilterPolicy'],
      },
      {
        key: 'qa_wikiFilterScore',
        label: 'chatExtends.wikiFilterScore',
        type: 'number',
        defaultValue: 0.82,
        min: 0,
        max: 1,
        step: 0.01,
        jsonPath: ['chatExtends', 'wikiFilterScore'],
      },
      {
        key: 'qa_temperature',
        label: 'chatExtends.temperature',
        type: 'number',
        defaultValue: 0.2,
        min: 0,
        max: 1,
        step: 0.05,
        enabledByDefault: true,
        jsonPath: ['chatExtends', 'temperature'],
      },
      {
        key: 'qa_spark',
        label: 'chatExtends.spark',
        description: '无 Wiki 匹配时大模型兜底',
        type: 'boolean',
        defaultValue: false,
        jsonPath: ['chatExtends', 'spark'],
      },
      {
        key: 'qa_qaMode',
        label: 'chatExtends.qaMode',
        description: '检索到 QA 对时的回答策略',
        type: 'select',
        defaultValue: 'MIX',
        options: [...QA_MODE_OPTIONS],
        enabledByDefault: true,
        jsonPath: ['chatExtends', 'qaMode'],
      },
      {
        key: 'qa_wikiPromptTpl',
        label: 'chatExtends.wikiPromptTpl',
        description: '自定义 Prompt 模板',
        type: 'text',
        placeholder: '请将以下内容作为已知信息…',
        jsonPath: ['chatExtends', 'wikiPromptTpl'],
      },
    ],
  },
];

export function findChatdocPipelineStage(id: ChatdocPipelineStageId): ChatdocPipelineStageDef | undefined {
  return CHATDOC_PIPELINE_STAGES.find((stage) => stage.id === id);
}

const UPLOAD_WIKI_SPLIT_FIELD_KEYS = ['chunkSize', 'minChunkSize', 'chunkSeparators'] as const;

export function isChatdocPipelineFieldConfigurable(
  field: ChatdocPipelineFieldDef,
  values: Record<string, string>,
): boolean {
  if (!field.dependsOn) return true;
  const controlValue = values[field.dependsOn.field] ?? 'true';
  return controlValue === String(field.dependsOn.equals);
}

export function chatdocPipelineEnabledAfterValueChange(
  key: string,
  nextValue: string,
  enabled: Record<string, boolean>,
): Record<string, boolean> {
  if (key !== 'isSplitDefault' || nextValue !== 'true') return enabled;
  const next = { ...enabled };
  for (const fieldKey of UPLOAD_WIKI_SPLIT_FIELD_KEYS) {
    next[fieldKey] = false;
  }
  return next;
}

export function defaultChatdocPipelineFieldValues(): Record<string, string> {
  const values: Record<string, string> = {};
  for (const stage of CHATDOC_PIPELINE_STAGES) {
    for (const field of stage.fields) {
      if (field.defaultValue === undefined) {
        values[field.key] = '';
        continue;
      }
      if (typeof field.defaultValue === 'boolean') {
        values[field.key] = field.defaultValue ? 'true' : 'false';
      } else {
        values[field.key] = String(field.defaultValue);
      }
    }
  }
  values.content = values.content || '什么是跳字模型？';
  return values;
}

export function defaultChatdocPipelineFieldEnabled(): Record<string, boolean> {
  const enabled: Record<string, boolean> = {};
  for (const stage of CHATDOC_PIPELINE_STAGES) {
    for (const field of stage.fields) {
      enabled[field.key] = Boolean(field.locked || field.enabledByDefault);
    }
  }
  return enabled;
}
