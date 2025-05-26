interface Thought {
  type: string;
  content: string;
  timestamp?: string;
  node?: string;
  id: string;
  category?: 'setup' | 'analysis' | 'tool' | 'result' | 'error' | 'visualization_data' | 'screenshot' | 'user_input' | 'user_control';
  technical_details?: Record<string, any>;
}

/**
 * Calculate processing time for answer nodes
 */
export function calculateProcessingTime(
  data: any,
  normalizedThought: Thought,
  thoughts: Thought[]
): void {
  if ((data.node === 'Answer' || data.category === 'result') && normalizedThought.timestamp) {
    // Find the last user question to calculate processing time
    const lastUserQuestion = [...thoughts].reverse().find(t => t.node === 'User' || t.type === 'question');
    
    // Only calculate if this is the first answer for this question (no existing processing time)
    const hasExistingAnswer = [...thoughts].reverse().find(t => 
      (t.node === 'Answer' || t.category === 'result') && 
      t.technical_details?.processing_time_sec &&
      lastUserQuestion?.timestamp &&
      t.timestamp &&
      new Date(t.timestamp).getTime() > new Date(lastUserQuestion.timestamp).getTime()
    );
    
    if (lastUserQuestion?.timestamp && !hasExistingAnswer) {
      try {
        const startTime = new Date(lastUserQuestion.timestamp).getTime();
        const endTime = new Date(normalizedThought.timestamp).getTime();
        const processingTimeMs = endTime - startTime;
        
        if (processingTimeMs > 0) {
          const processingTimeSec = (processingTimeMs / 1000).toFixed(2);
          normalizedThought.technical_details = {
            ...(normalizedThought.technical_details || {}),
            processing_time_ms: processingTimeMs,
            processing_time_sec: parseFloat(processingTimeSec)
          };
        }
      } catch (timeError) {
        console.error("Error calculating processing time:", timeError);
      }
    }
  }
}

/**
 * Generate unique ID for thoughts
 */
export function generateId(prefix: string = 'thought'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
}

/**
 * Check if event should be filtered out
 */
export function shouldFilterEvent(data: any): boolean {
  if (data.type === 'ping' || data.type === 'heartbeat') {
    return true;
  }
  
  const validTypes = ['thought', 'reasoning', 'tool_call', 'tool_result', 'question', 
                     'visualization', 'thinking', 'rationale', 'error', 'answer', 'result', 'browser_status', 'others', 'user_control'];
  const validNodes = ['User', 'Browser', 'Agent', 'NovaAct', 'Answer', 'complete', 'Router', 'Others', 'User Control'];
  
  if (!validTypes.includes(data.type) && 
      !validNodes.includes(data.node) && 
      data.category !== 'screenshot' &&
      data.category !== 'visualization_data' &&
      data.category !== 'user_control') {
    return true;
  }
  
  return false;
}