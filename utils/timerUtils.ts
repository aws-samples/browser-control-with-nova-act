import type { MutableRefObject } from 'react';

/**
 * Reset thinking timer and state
 */
export function resetThinkingTimer(
  setIsThinking: (value: boolean) => void,
  thinkingStartTime: MutableRefObject<number | null>
): void {
  setIsThinking(false);
  thinkingStartTime.current = null;
}

/**
 * Calculate processing time from start time
 */
export function calculateProcessingTime(thinkingStartTime: MutableRefObject<number | null>): string | null {
  if (thinkingStartTime.current) {
    const processingTimeMs = Date.now() - thinkingStartTime.current;
    return (processingTimeMs / 1000).toFixed(2);
  }
  return null;
}