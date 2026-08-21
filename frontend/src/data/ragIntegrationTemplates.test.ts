import { describe, expect, it } from 'vitest';
import {
  getBundledRagIntegrationTemplates,
  isCredentialFieldLocked,
  shouldShowPresetTemplateApiBaseUrl,
} from './ragIntegrationTemplates';

describe('ragIntegrationTemplates', (): void => {
  const iflytek = getBundledRagIntegrationTemplates().find((item) => item.key === 'iflytek-chatdoc');
  const baseUrlField = iflytek?.credential_fields.find((field) => field.key === 'base_url');

  it('预置模板的 API 请求地址保持可编辑', (): void => {
    expect(iflytek).toBeDefined();
    expect(baseUrlField).toBeDefined();
    expect(baseUrlField && iflytek && isCredentialFieldLocked(iflytek, baseUrlField)).toBe(false);
  });

  it('模板包含 base_url 字段时不再重复展示只读预设地址', (): void => {
    expect(iflytek && shouldShowPresetTemplateApiBaseUrl(iflytek)).toBe(false);
  });
});
