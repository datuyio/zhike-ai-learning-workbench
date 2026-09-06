import { useEffect, useReducer } from 'react';
import {
  ONBOARDING_COMPLETED_KEY_PREFIX,
  ONBOARDING_STORAGE_KEY_PREFIX,
  buildUserScopedStorageKey,
} from '../constants/storage-keys';
import { readLocalString, writeLocalString } from '../utils/browser-storage';
import { tryParseJsonValue } from '../utils/json-parse';
import type {
  OnboardingDimensionBrief,
  OnboardingRound,
  OnboardingState,
} from '../types/onboarding';

export const initialOnboardingState: OnboardingState = {
  skipped: false,
  phase: 'idle',
  round: 1,
  rounds: [],
  completedAt: null,
  completedDimensions: [],
  selectedCourseSlug: null,
};

export type OnboardingAction =
  | { type: 'DETECT_COLD_START'; payload: { profileDimensions: number; skipDetection?: boolean } }
  | {
      type: 'SUBMIT_ROUND';
      payload: {
        question: string;
        answer: string;
        extractedDimensions: string[];
        history: Array<{ role: 'user' | 'assistant'; content: string }>;
      };
    }
  | { type: 'RECEIVE_META'; payload: { done: boolean; currentDimensions: OnboardingDimensionBrief[] } }
  | { type: 'SKIP' }
  | { type: 'RESTORE'; payload: OnboardingState }
  | { type: 'CLOSE' };

/** 将引导状态写入 localStorage，每轮必须包含完整 history。按 userId 隔离避免多账号污染。 */
export function persistOnboarding(state: OnboardingState, userId: string): void {
  const storageKey = buildUserScopedStorageKey(ONBOARDING_STORAGE_KEY_PREFIX, userId);
  const completedKey = buildUserScopedStorageKey(ONBOARDING_COMPLETED_KEY_PREFIX, userId);
  writeLocalString(storageKey, JSON.stringify(state));
  if (state.completedAt) {
    writeLocalString(completedKey, state.completedAt);
  }
}

/** 从 localStorage 恢复引导状态。按 userId 隔离读取。 */
export function restoreOnboarding(userId: string): OnboardingState | null {
  const storageKey = buildUserScopedStorageKey(ONBOARDING_STORAGE_KEY_PREFIX, userId);
  const raw = readLocalString(storageKey);
  if (!raw) return null;
  const parsed = tryParseJsonValue(raw);
  if (!isOnboardingState(parsed)) return null;
  return parsed;
}

/** 校验本地恢复出的对象是否具备完整引导状态骨架。 */
function isOnboardingState(value: unknown): value is OnboardingState {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<OnboardingState>;
  return (
    typeof candidate.skipped === 'boolean'
    && (candidate.phase === 'idle' || candidate.phase === 'active' || candidate.phase === 'closing')
    && typeof candidate.round === 'number'
    && Array.isArray(candidate.rounds)
    && Array.isArray(candidate.completedDimensions)
  );
}

export function onboardingReducer(state: OnboardingState, action: OnboardingAction): OnboardingState {
  switch (action.type) {
    case 'DETECT_COLD_START':
      if (action.payload.skipDetection) return state;
      if (state.skipped || state.completedAt) return state;
      if (action.payload.profileDimensions >= 3) return { ...state, phase: 'idle' };
      return { ...state, phase: 'active', round: 1 };

    case 'SUBMIT_ROUND': {
      if (state.phase !== 'active') return state;
      if (!action.payload.history.length) return state;
      const newRound: OnboardingRound = {
        round: state.round,
        question: action.payload.question,
        answer: action.payload.answer,
        extractedDimensions: action.payload.extractedDimensions,
        history: action.payload.history,
      };
      const nextRound = state.round + 1;
      if (state.round >= 3) {
        return {
          ...state,
          phase: 'closing',
          rounds: [...state.rounds, newRound],
          completedDimensions: [
            ...new Set([...state.completedDimensions, ...action.payload.extractedDimensions]),
          ],
        };
      }
      return {
        ...state,
        round: nextRound,
        rounds: [...state.rounds, newRound],
        completedDimensions: [
          ...new Set([...state.completedDimensions, ...action.payload.extractedDimensions]),
        ],
      };
    }

    case 'RECEIVE_META':
      if (action.payload.done) {
        return {
          ...state,
          phase: 'closing',
          completedAt: new Date().toISOString(),
          completedDimensions: action.payload.currentDimensions.map((d) => d.key),
        };
      }
      return {
        ...state,
        completedDimensions: action.payload.currentDimensions.map((d) => d.key),
      };

    case 'SKIP':
      return { ...state, skipped: true, phase: 'idle' };

    case 'RESTORE':
      return action.payload;

    case 'CLOSE':
      return {
        ...state,
        phase: 'idle',
        completedAt: state.completedAt ?? new Date().toISOString(),
      };

    default:
      return state;
  }
}

export function countValidProfileDimensions(
  dimensions: Array<{ confidence?: number }> | undefined,
): number {
  if (!dimensions?.length) return 0;
  return dimensions.filter((item) => (item.confidence ?? 0) >= 0.4).length;
}

/** 冷启动检测与状态机 Hook */
export function useOnboardingWizard(options: {
  userId: string;
  profileDimensions: number;
  loading: boolean;
  skipDetection?: boolean;
}): {
  state: OnboardingState;
  dispatch: React.Dispatch<OnboardingAction>;
  showWizard: boolean;
} {
  const [state, dispatch] = useReducer(onboardingReducer, initialOnboardingState);

  useEffect(() => {
    if (options.loading) return;
    const saved = restoreOnboarding(options.userId);
    if (saved) {
      dispatch({ type: 'RESTORE', payload: saved });
      if (saved.phase === 'idle' && !saved.skipped && !saved.completedAt) {
        dispatch({
          type: 'DETECT_COLD_START',
          payload: {
            profileDimensions: options.profileDimensions,
            skipDetection: options.skipDetection,
          },
        });
      }
    } else {
      dispatch({
        type: 'DETECT_COLD_START',
        payload: {
          profileDimensions: options.profileDimensions,
          skipDetection: options.skipDetection,
        },
      });
    }
  }, [options.loading, options.profileDimensions, options.skipDetection, options.userId]);

  useEffect(() => {
    if (state.phase !== 'idle' || state.skipped || state.rounds.length > 0) {
      persistOnboarding(state, options.userId);
    }
  }, [state, options.userId]);

  const showWizard = state.phase === 'active' || state.phase === 'closing';

  return { state, dispatch, showWizard };
}

/** 从已完成轮次拼接 onboarding_history 供后端无状态恢复 */
export function buildOnboardingHistoryFromRounds(
  rounds: OnboardingRound[],
): Array<{ role: 'user' | 'assistant'; content: string }> {
  const history: Array<{ role: 'user' | 'assistant'; content: string }> = [];
  for (const round of rounds) {
    history.push(...round.history);
  }
  return history;
}
