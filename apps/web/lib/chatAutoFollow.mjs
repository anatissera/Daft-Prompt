export const AUTO_FOLLOW_THRESHOLD_PX = 96;

export function distanceFromBottom({ scrollHeight, scrollTop, clientHeight }) {
  return Math.max(0, scrollHeight - scrollTop - clientHeight);
}

export function isNearConversationBottom(metrics, threshold = AUTO_FOLLOW_THRESHOLD_PX) {
  return distanceFromBottom(metrics) <= threshold;
}
