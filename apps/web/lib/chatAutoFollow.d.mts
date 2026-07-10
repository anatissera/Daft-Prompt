export interface ScrollMetrics { scrollHeight: number; scrollTop: number; clientHeight: number; }
export const AUTO_FOLLOW_THRESHOLD_PX: number;
export function distanceFromBottom(metrics: ScrollMetrics): number;
export function isNearConversationBottom(metrics: ScrollMetrics, threshold?: number): boolean;
