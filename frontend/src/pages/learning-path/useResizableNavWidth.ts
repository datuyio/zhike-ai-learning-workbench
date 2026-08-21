import { useCallback, useState } from 'react';
import { readLocalString, writeLocalString } from '../../utils/browser-storage';

const STORAGE_KEY = 'zhike-learning-path-nav-width';
const DEFAULT_WIDTH = 280;
const MIN_WIDTH = 240;
const MAX_WIDTH = 360;

function clampWidth(value: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value));
}

function readStoredWidth(): number {
  const raw = readLocalString(STORAGE_KEY);
  if (!raw) return DEFAULT_WIDTH;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? clampWidth(parsed) : DEFAULT_WIDTH;
}

/**
 * 学习路径左侧目录栏宽度：默认 280px，拖拽调节范围 240–360px，宽度写入 localStorage。
 */
export function useResizableNavWidth(): {
  navWidth: number;
  handleResizeStart: (event: React.PointerEvent<HTMLDivElement>) => void;
  minWidth: number;
  maxWidth: number;
} {
  const [navWidth, setNavWidth] = useState(readStoredWidth);

  const handleResizeStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = navWidth;
    let latestWidth = startWidth;

    const handleMove = (moveEvent: PointerEvent) => {
      latestWidth = clampWidth(startWidth + (moveEvent.clientX - startX));
      setNavWidth(latestWidth);
    };

    const handleUp = () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
      document.body.classList.remove('learning-path-page--resizing');
      writeLocalString(STORAGE_KEY, String(latestWidth));
    };

    document.body.classList.add('learning-path-page--resizing');
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
  }, [navWidth]);

  return { navWidth, handleResizeStart, minWidth: MIN_WIDTH, maxWidth: MAX_WIDTH };
}
