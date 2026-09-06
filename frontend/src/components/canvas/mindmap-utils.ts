import { downloadTextFile } from './document-export';
import { tryParseJsonValue } from '../../utils/json-parse';

export type MindmapNode = {
  id: string;
  title: string;
  level: number;
  children: MindmapNode[];
};

export type MindmapLayoutNode = Omit<MindmapNode, 'children'> & {
  x: number;
  y: number;
  width: number;
  height: number;
  side: 'root' | 'left' | 'right';
  colorIndex: number;
  children: MindmapLayoutNode[];
};

export type MindmapLayout = {
  root: MindmapLayoutNode;
  width: number;
  height: number;
  branchCount: number;
  leafCount: number;
};

export type MindmapSvgDocument = {
  svg: string;
  width: number;
  height: number;
  branchCount: number;
  leafCount: number;
};

export type MindmapSourceDocument = {
  syntax: 'mermaid' | 'markdown';
  source: string;
};

const SVG_WIDTH = 1120;
const ROOT_X = SVG_WIDTH / 2;
const ROOT_WIDTH = 190;
const ROOT_HEIGHT = 68;
const BRANCH_WIDTH = 176;
const BRANCH_HEIGHT = 54;
const LEAF_WIDTH = 186;
const LEAF_HEIGHT = 38;
const BRANCH_OFFSET = 246;
const LEAF_OFFSET = 466;
const BRANCH_SPACING = 22;
const LEAF_SPACING = 44;

const LINK_COLORS = ['#2563eb', '#16a34a', '#ea580c', '#0891b2', '#be123c', '#7c3aed', '#4f46e5', '#0f766e'];
let mermaidRenderSerial = 0;

function cleanTitle(value: string): string {
  return value
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/<[^>]+>/g, '')
    .replace(/[*_`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function safeFileName(value: string, fallback: string): string {
  const normalized = cleanTitle(value).replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, '-');
  return (normalized || fallback).slice(0, 80);
}

function stripCodeFence(value: string): string {
  return value
    .replace(/^```(?:mermaid|json|markdown)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim();
}

function normalizeMermaidSource(value: string): string {
  return stripCodeFence(value)
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.replace(/\s+$/, ''))
    .filter((line) => line.trim().length > 0)
    .join('\n')
    .trim();
}

/** 解析新 Mermaid JSON 外壳，并兼容旧 Markdown 导图内容。 */
export function resolveMindmapSource(content: string): MindmapSourceDocument {
  const raw = (content || '').trim();
  if (!raw) return { syntax: 'markdown', source: '' };
  const parsed = tryParseJsonValue(stripCodeFence(raw)) as {
    chart_type?: string;
    syntax?: string;
    source_code?: unknown;
  };
  if (parsed && parsed.chart_type === 'mindmap' && parsed.syntax === 'mermaid' && typeof parsed.source_code === 'string') {
    return { syntax: 'mermaid', source: normalizeMermaidSource(parsed.source_code) };
  }
  // 旧资源可能仍是 Markdown 正文，解析失败时直接走兼容渲染。
  const normalized = normalizeMermaidSource(raw);
  if (normalized.startsWith('mindmap\n') || normalized === 'mindmap') {
    return { syntax: 'mermaid', source: normalized };
  }
  return { syntax: 'markdown', source: raw };
}

/** 统计 Mermaid mindmap 的主要分支与叶节点数量。 */
export function countMermaidMindmapNodes(source: string): { branchCount: number; leafCount: number } {
  let branchCount = 0;
  let leafCount = 0;
  for (const line of normalizeMermaidSource(source).split('\n').slice(2)) {
    const indent = line.length - line.trimStart().length;
    if (indent === 4) branchCount += 1;
    if (indent >= 6) leafCount += 1;
  }
  return { branchCount, leafCount };
}

function svgDimensions(svg: string): { width: number; height: number } {
  const viewBox = /viewBox=["']([^"']+)["']/i.exec(svg)?.[1]?.split(/\s+/).map(Number);
  if (viewBox && viewBox.length === 4 && viewBox.every(Number.isFinite)) {
    return { width: Math.max(1, viewBox[2]), height: Math.max(1, viewBox[3]) };
  }
  const width = Number(/width=["']([\d.]+)/i.exec(svg)?.[1] ?? 1120);
  const height = Number(/height=["']([\d.]+)/i.exec(svg)?.[1] ?? 720);
  return { width: Number.isFinite(width) ? width : 1120, height: Number.isFinite(height) ? height : 720 };
}

/** 使用 Mermaid 官方渲染器生成 SVG，供预览和导出复用。 */
export async function renderMermaidMindmapSvg(source: string): Promise<MindmapSvgDocument> {
  const mermaid = (await import('mermaid')).default;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: {
      fontFamily: '"Microsoft YaHei", "Segoe UI", sans-serif',
      primaryColor: '#ffffff',
      primaryTextColor: '#0f172a',
      primaryBorderColor: '#2563eb',
      lineColor: '#2563eb',
      tertiaryColor: '#f8fafc',
    },
  });
  const normalized = normalizeMermaidSource(source);
  await mermaid.parse(normalized);
  const result = await mermaid.render(`mindmap-render-${Date.now()}-${mermaidRenderSerial++}`, normalized);
  const dimensions = svgDimensions(result.svg);
  const count = countMermaidMindmapNodes(normalized);
  return { svg: result.svg, width: dimensions.width, height: dimensions.height, ...count };
}

function textUnits(value: string): number {
  return Array.from(value).reduce((sum, char) => sum + (/[A-Za-z0-9]/.test(char) ? 0.58 : 1), 0);
}

function wrapText(value: string, maxUnits: number, maxLines: number): string[] {
  const chars = Array.from(cleanTitle(value) || '未命名节点');
  const lines: string[] = [];
  let current = '';
  for (const char of chars) {
    if (current && textUnits(current + char) > maxUnits) {
      lines.push(current);
      current = char;
      if (lines.length === maxLines) break;
      continue;
    }
    current += char;
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (chars.join('').length > lines.join('').length && lines.length > 0) {
    const last = lines.length - 1;
    lines[last] = `${Array.from(lines[last]).slice(0, Math.max(1, lines[last].length - 1)).join('')}…`;
  }
  return lines.length ? lines : ['未命名节点'];
}

function nodeId(index: number): string {
  return `mindmap-node-${index}`;
}

function leafFallbackNodes(markdown: string): MindmapNode[] {
  return markdown
    .split(/\r?\n/)
    .map((line) => cleanTitle(line.replace(/^[-*+]\s+/, '').replace(/^\d+[.)]\s+/, '')))
    .filter(Boolean)
    .slice(0, 8)
    .map((title, index) => ({ id: `mindmap-fallback-leaf-${index}`, title, level: 3, children: [] }));
}

/** 将 Markmap 风格 Markdown 标题解析为三层思维导图树。 */
export function parseMindmapMarkdown(markdown: string, fallbackTitle: string): MindmapNode {
  let serial = 0;
  const root: MindmapNode = {
    id: nodeId(serial),
    title: cleanTitle(fallbackTitle) || '知识思维导图',
    level: 1,
    children: [],
  };
  const stack: MindmapNode[] = [root];
  let hasRootHeading = false;
  let hasHeading = false;

  for (const line of markdown.split(/\r?\n/)) {
    const match = /^(#{1,6})\s+(.+?)\s*$/.exec(line.trim());
    if (!match) continue;
    hasHeading = true;
    const rawLevel = match[1].length;
    const title = cleanTitle(match[2].replace(/\s+#+$/, ''));
    if (!title) continue;

    if (rawLevel === 1 && !hasRootHeading && root.children.length === 0) {
      root.title = title;
      hasRootHeading = true;
      stack.splice(1);
      continue;
    }

    const level = rawLevel === 1 ? 2 : Math.min(rawLevel, 3);
    const node: MindmapNode = { id: nodeId(++serial), title, level, children: [] };
    while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop();
    const parent = stack[stack.length - 1] ?? root;
    parent.children.push(node);
    stack.push(node);
  }

  if (!hasHeading) {
    root.children.push({
      id: nodeId(++serial),
      title: '核心要点',
      level: 2,
      children: leafFallbackNodes(markdown),
    });
  }

  if (root.children.length === 0) {
    root.children.push({ id: nodeId(++serial), title: '暂无分支', level: 2, children: [] });
  }

  return root;
}

function branchSpan(node: MindmapNode): number {
  return Math.max(92, node.children.length > 0 ? node.children.length * LEAF_SPACING + 28 : 92);
}

function sideSpan(nodes: MindmapNode[]): number {
  if (nodes.length === 0) return 0;
  return nodes.reduce((sum, node) => sum + branchSpan(node), 0) + (nodes.length - 1) * BRANCH_SPACING;
}

function layoutBranch(
  node: MindmapNode,
  side: 'left' | 'right',
  y: number,
  colorIndex: number,
): MindmapLayoutNode {
  const direction = side === 'right' ? 1 : -1;
  const branch: MindmapLayoutNode = {
    ...node,
    x: ROOT_X + direction * BRANCH_OFFSET,
    y,
    width: BRANCH_WIDTH,
    height: BRANCH_HEIGHT,
    side,
    colorIndex,
    children: [],
  };
  const childStart = y - ((node.children.length - 1) * LEAF_SPACING) / 2;
  branch.children = node.children.map((child, index) => ({
    ...child,
    x: ROOT_X + direction * LEAF_OFFSET,
    y: childStart + index * LEAF_SPACING,
    width: LEAF_WIDTH,
    height: LEAF_HEIGHT,
    side,
    colorIndex,
    children: [],
  }));
  return branch;
}

/** 为思维导图树计算稳定的左右布局坐标。 */
export function buildMindmapLayout(root: MindmapNode): MindmapLayout {
  const right = root.children.filter((_, index) => index % 2 === 0);
  const left = root.children.filter((_, index) => index % 2 === 1);
  const height = Math.max(560, Math.max(sideSpan(left), sideSpan(right)) + 140);
  const rootLayout: MindmapLayoutNode = {
    ...root,
    x: ROOT_X,
    y: height / 2,
    width: ROOT_WIDTH,
    height: ROOT_HEIGHT,
    side: 'root',
    colorIndex: 0,
    children: [],
  };

  function placeSide(nodes: MindmapNode[], side: 'left' | 'right'): MindmapLayoutNode[] {
    const total = sideSpan(nodes);
    let cursor = (height - total) / 2;
    return nodes.map((node, index) => {
      const span = branchSpan(node);
      const branch = layoutBranch(node, side, cursor + span / 2, index,);
      cursor += span + BRANCH_SPACING;
      return branch;
    });
  }

  rootLayout.children = [...placeSide(left, 'left'), ...placeSide(right, 'right')];
  const leafCount = rootLayout.children.reduce((sum, branch) => sum + branch.children.length, 0);
  return { root: rootLayout, width: SVG_WIDTH, height, branchCount: root.children.length, leafCount };
}

function connectionPath(source: MindmapLayoutNode, target: MindmapLayoutNode): string {
  const direction = target.side === 'right' ? 1 : -1;
  const sourceX = source.x + direction * (source.width / 2);
  const targetX = target.x - direction * (target.width / 2);
  const midX = sourceX + direction * Math.max(72, Math.abs(targetX - sourceX) * 0.48);
  return `M ${sourceX} ${source.y} C ${midX} ${source.y}, ${midX} ${target.y}, ${targetX} ${target.y}`;
}

function renderText(title: string, maxUnits: number, maxLines: number, yOffset = 0): string {
  const lines = wrapText(title, maxUnits, maxLines);
  const firstY = yOffset - ((lines.length - 1) * 16) / 2;
  return lines
    .map((line, index) => `<tspan x="0" y="${firstY + index * 16}">${escapeXml(line)}</tspan>`)
    .join('');
}

function renderNode(node: MindmapLayoutNode): string {
  const palette = LINK_COLORS[node.colorIndex % LINK_COLORS.length];
  const isRoot = node.side === 'root';
  const isLeaf = node.level >= 3;
  const fill = isRoot ? '#0f172a' : isLeaf ? '#f8fafc' : '#ffffff';
  const stroke = isRoot ? '#0f172a' : palette;
  const textColor = isRoot ? '#ffffff' : isLeaf ? '#334155' : '#0f172a';
  const fontSize = isRoot ? 16 : isLeaf ? 11 : 12;
  const fontWeight = isRoot ? 900 : isLeaf ? 760 : 860;
  const text = renderText(node.title, isRoot ? 12 : isLeaf ? 18 : 13, isRoot ? 2 : 2);
  return `<g class="mindmap-svg-node mindmap-svg-node--${node.side}" transform="translate(${node.x} ${node.y})">
    <rect x="${-node.width / 2}" y="${-node.height / 2}" width="${node.width}" height="${node.height}" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="${isRoot ? 1.5 : 1.3}" />
    <text text-anchor="middle" dominant-baseline="middle" fill="${textColor}" font-size="${fontSize}" font-weight="${fontWeight}">${text}</text>
  </g>`;
}

function renderLinks(node: MindmapLayoutNode): string {
  return node.children
    .map((child) => {
      const color = LINK_COLORS[child.colorIndex % LINK_COLORS.length];
      return `<path d="${connectionPath(node, child)}" fill="none" stroke="${color}" stroke-width="${node.side === 'root' ? 2.8 : 1.7}" stroke-linecap="round" opacity="${node.side === 'root' ? 0.88 : 0.56}" />${renderLinks(child)}`;
    })
    .join('');
}

function renderNodes(node: MindmapLayoutNode): string {
  return `${renderNode(node)}${node.children.map(renderNodes).join('')}`;
}

/** 构建可下载、可内嵌展示的 SVG 思维导图文档。 */
export function buildMindmapSvgDocument(markdown: string, title: string): MindmapSvgDocument {
  const tree = parseMindmapMarkdown(markdown, title);
  const layout = buildMindmapLayout(tree);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}" role="img" aria-label="${escapeXml(layout.root.title)} 思维导图">
  <defs>
    <filter id="mindmap-shadow" x="-20%" y="-35%" width="140%" height="170%">
      <feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.09" />
    </filter>
    <pattern id="mindmap-grid" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M 34 0 L 0 0 0 34" fill="none" stroke="#e2e8f0" stroke-width="0.8" opacity="0.45" />
    </pattern>
  </defs>
  <style>
    .mindmap-svg-node rect { filter: url(#mindmap-shadow); }
    .mindmap-svg-node text { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; letter-spacing: 0; }
  </style>
  <rect width="100%" height="100%" fill="#fbfdff" />
  <rect width="100%" height="100%" fill="url(#mindmap-grid)" />
  <g>${renderLinks(layout.root)}${renderNodes(layout.root)}</g>
</svg>`;
  return {
    svg,
    width: layout.width,
    height: layout.height,
    branchCount: layout.branchCount,
    leafCount: layout.leafCount,
  };
}

/** 下载思维导图 SVG 文件。 */
export async function downloadMindmapSvg(title: string, content: string): Promise<void> {
  const source = resolveMindmapSource(content);
  const document = source.syntax === 'mermaid'
    ? await renderMermaidMindmapSvg(source.source)
    : buildMindmapSvgDocument(source.source, title);
  downloadTextFile(`${safeFileName(title, 'mindmap')}.svg`, document.svg, 'image/svg+xml;charset=utf-8');
}

/** 下载思维导图 PNG 文件。 */
export async function downloadMindmapPng(title: string, content: string): Promise<void> {
  const source = resolveMindmapSource(content);
  const svgDocument = source.syntax === 'mermaid'
    ? await renderMermaidMindmapSvg(source.source)
    : buildMindmapSvgDocument(source.source, title);
  const blob = new Blob([svgDocument.svg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    image.decoding = 'async';
    const loaded = new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('思维导图图片加载失败'));
    });
    image.src = url;
    await loaded;
    const scale = 2;
    const canvas = documentCreateCanvas(svgDocument.width * scale, svgDocument.height * scale);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('浏览器不支持 Canvas 导出');
    context.fillStyle = '#fbfdff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.scale(scale, scale);
    context.drawImage(image, 0, 0);
    const pngBlob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) resolve(result);
        else reject(new Error('PNG 导出失败'));
      }, 'image/png');
    });
    const pngUrl = URL.createObjectURL(pngBlob);
    const anchor = window.document.createElement('a');
    anchor.href = pngUrl;
    anchor.download = `${safeFileName(title, 'mindmap')}.png`;
    anchor.click();
    URL.revokeObjectURL(pngUrl);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function documentCreateCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = window.document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}
