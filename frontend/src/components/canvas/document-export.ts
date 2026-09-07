export function downloadTextFile(filename: string, content: string, mime = 'text/plain;charset=utf-8'): void {
  const blob = new Blob([content], { type: mime });
  downloadBlobFile(filename, blob);
}

function downloadBlobFile(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

type MarkdownBlock = {
  type: 'heading' | 'paragraph' | 'list' | 'code';
  level?: number;
  text: string;
};

type SlideModel = {
  title: string;
  bullets: string[];
};

function htmlEscape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function stripMarkdownInline(value: string): string {
  return value
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/[>#]/g, '')
    .trim();
}

function safeExportBaseName(title: string): string {
  const normalized = stripMarkdownInline(title || 'resource')
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
  return normalized.slice(0, 80) || 'resource';
}

function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  let inCode = false;
  const codeLines: string[] = [];

  for (const rawLine of markdown.replace(/\r\n/g, '\n').split('\n')) {
    const line = rawLine.trimEnd();
    if (/^```/.test(line.trim())) {
      if (inCode) {
        blocks.push({ type: 'code', text: codeLines.join('\n') });
        codeLines.length = 0;
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!line.trim()) {
      continue;
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line.trim());
    if (heading) {
      blocks.push({ type: 'heading', level: Math.min(3, heading[1].length), text: stripMarkdownInline(heading[2]) });
      continue;
    }
    const list = /^[-*+]\s+(.+)$/.exec(line.trim()) || /^\d+[.)]\s+(.+)$/.exec(line.trim());
    if (list) {
      blocks.push({ type: 'list', text: stripMarkdownInline(list[1]) });
      continue;
    }
    blocks.push({ type: 'paragraph', text: stripMarkdownInline(line) });
  }
  if (codeLines.length) {
    blocks.push({ type: 'code', text: codeLines.join('\n') });
  }
  return blocks.filter((block) => block.text.trim().length > 0);
}

async function buildDocxBlob(title: string, markdown: string): Promise<Blob> {
  const {
    AlignmentType,
    Document,
    HeadingLevel,
    LevelFormat,
    Packer,
    Paragraph,
    TextRun,
  } = await import('docx');
  const docxHeadingLevel = (level = 2): (typeof HeadingLevel)[keyof typeof HeadingLevel] => {
    if (level <= 1) return HeadingLevel.HEADING_1;
    if (level === 2) return HeadingLevel.HEADING_2;
    return HeadingLevel.HEADING_3;
  };
  const createDocxParagraph = (block: MarkdownBlock): InstanceType<typeof Paragraph> => {
    if (block.type === 'heading') {
      return new Paragraph({
        heading: docxHeadingLevel(block.level),
        spacing: { before: 320, after: 140 },
        children: [
          new TextRun({
            text: block.text,
            bold: true,
            font: { ascii: 'Microsoft YaHei', hAnsi: 'Microsoft YaHei', eastAsia: 'Microsoft YaHei' },
          }),
        ],
      });
    }

    if (block.type === 'list') {
      return new Paragraph({
        numbering: { reference: 'resource-bullets', level: 0 },
        spacing: { after: 120 },
        children: [
          new TextRun({
            text: block.text,
            font: { ascii: 'Microsoft YaHei', hAnsi: 'Microsoft YaHei', eastAsia: 'Microsoft YaHei' },
            size: 22,
          }),
        ],
      });
    }

    if (block.type === 'code') {
      return new Paragraph({
        shading: { fill: 'F8FAFC' },
        spacing: { before: 120, after: 120 },
        children: [
          new TextRun({
            text: block.text,
            font: 'Consolas',
            size: 20,
          }),
        ],
      });
    }

    return new Paragraph({
      spacing: { after: 140, line: 320 },
      children: [
        new TextRun({
          text: block.text,
          font: { ascii: 'Microsoft YaHei', hAnsi: 'Microsoft YaHei', eastAsia: 'Microsoft YaHei' },
          size: 22,
        }),
      ],
    });
  };
  const children = [
    new Paragraph({
      heading: HeadingLevel.TITLE,
      alignment: AlignmentType.LEFT,
      spacing: { after: 260 },
      children: [
        new TextRun({
          text: title || '学习资源',
          bold: true,
          font: { ascii: 'Microsoft YaHei', hAnsi: 'Microsoft YaHei', eastAsia: 'Microsoft YaHei' },
          size: 36,
        }),
      ],
    }),
    ...parseMarkdownBlocks(markdown).map(createDocxParagraph),
  ];

  const doc = new Document({
    title,
    creator: '智课未来',
    description: '由 ArtifactCanvas 通过 docx 库导出',
    numbering: {
      config: [
        {
          reference: 'resource-bullets',
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: '•',
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: 720, hanging: 360 },
                },
              },
            },
          ],
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            margin: { top: 1440, right: 1200, bottom: 1440, left: 1200 },
          },
        },
        children,
      },
    ],
  });

  return Packer.toBlob(doc);
}

function chunkLines(lines: string[], size: number): string[][] {
  const chunks: string[][] = [];
  for (let index = 0; index < lines.length; index += size) {
    chunks.push(lines.slice(index, index + size));
  }
  return chunks.length ? chunks : [[]];
}

function markdownToSlides(title: string, markdown: string): SlideModel[] {
  const blocks = parseMarkdownBlocks(markdown);
  const slides: SlideModel[] = [{ title, bullets: ['由资源画布导出', '可在 PowerPoint 中继续编辑'] }];
  let current: SlideModel | null = null;

  for (const block of blocks) {
    if (block.type === 'heading') {
      if (current) slides.push(current);
      current = { title: block.text || title, bullets: [] };
      continue;
    }
    if (!current) current = { title: '学习要点', bullets: [] };
    current.bullets.push(block.text);
  }
  if (current) slides.push(current);

  return slides.flatMap((slide) => {
    const bullets = slide.bullets.filter(Boolean);
    return chunkLines(bullets, 6).map((chunk, index) => ({
      title: index === 0 ? slide.title : `${slide.title}（续）`,
      bullets: chunk,
    }));
  }).slice(0, 24);
}

async function buildPptxFile(title: string, markdown: string): Promise<void> {
  const { default: pptxgen } = await import('pptxgenjs');
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = '智课未来';
  pptx.company = '智课未来';
  pptx.subject = '学习资源导出';
  pptx.title = title || '学习资源';
  pptx.theme = {
    headFontFace: 'Microsoft YaHei',
    bodyFontFace: 'Microsoft YaHei',
  };

  const slides = markdownToSlides(title || '学习资源', markdown);
  for (const [index, slideModel] of slides.entries()) {
    const slide = pptx.addSlide();
    slide.background = { color: 'FFFFFF' };
    slide.addText(slideModel.title, {
      x: 0.7,
      y: 0.45,
      w: 11.8,
      h: 0.55,
      fontFace: 'Microsoft YaHei',
      fontSize: index === 0 ? 26 : 24,
      bold: true,
      color: '0F172A',
      margin: 0,
      fit: 'shrink',
    });
    slide.addShape(pptx.ShapeType.line, {
      x: 0.7,
      y: 1.18,
      w: 11.8,
      h: 0,
      line: { color: 'E2E8F0', width: 1 },
    });

    const bullets = slideModel.bullets.length ? slideModel.bullets : ['暂无正文内容'];
    slide.addText(
      bullets.map((text) => ({ text, options: { bullet: { indent: 18 }, breakLine: true } })),
      {
        x: 0.86,
        y: 1.45,
        w: 11.45,
        h: 4.95,
        fontFace: 'Microsoft YaHei',
        fontSize: 15,
        color: '334155',
        fit: 'shrink',
        margin: [4, 6, 4, 6],
        breakLine: false,
        paraSpaceAfter: 8,
      },
    );
    slide.addText(`智课未来 · ${index + 1}/${slides.length}`, {
      x: 0.7,
      y: 6.95,
      w: 11.8,
      h: 0.25,
      fontFace: 'Microsoft YaHei',
      fontSize: 9,
      color: '94A3B8',
      align: 'right',
      margin: 0,
    });
  }

  await pptx.writeFile({ fileName: `${safeExportBaseName(title)}.pptx`, compression: true });
}

export async function downloadDocxFromMarkdown(title: string, markdown: string): Promise<void> {
  const blob = await buildDocxBlob(title, markdown);
  downloadBlobFile(`${safeExportBaseName(title)}.docx`, blob);
}

export async function downloadPptxFromMarkdown(title: string, markdown: string): Promise<void> {
  await buildPptxFile(title, markdown);
}

export async function copyMarkdown(content: string): Promise<void> {
  await navigator.clipboard.writeText(content);
}

export function printMarkdownAsPdf(title: string, markdown: string): void {
  const popup = window.open('', '_blank', 'noopener,noreferrer,width=900,height=700');
  if (!popup) return;
  popup.document.write(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>${htmlEscape(title)}</title>
<style>
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.7; padding: 32px; color: #0f172a; }
  pre { white-space: pre-wrap; word-break: break-word; font-size: 14px; }
  @media print { body { padding: 18px; } }
</style></head><body><pre>${htmlEscape(markdown)}</pre></body></html>`);
  popup.document.close();
  popup.focus();
  popup.print();
}
