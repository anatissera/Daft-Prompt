export type ChatWorkflow = "research" | "composition" | "editing" | "answering";
export const WORKFLOW_STAGES: Record<ChatWorkflow, string[]>;
export function classifyChatWorkflow(message: string, options?: { hasCurrentSong?: boolean }): ChatWorkflow;
export function workflowBusyLabel(workflow: ChatWorkflow): string;
export function activeWorkflowStage(elapsedSeconds: number, stageCount: number): number;
