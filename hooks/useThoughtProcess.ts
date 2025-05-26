import { useState, useEffect, useCallback, useRef } from 'react';
import { dispatchEvent, subscribeToEvent } from '@/services/eventService';
import { calculateProcessingTime, generateId, shouldFilterEvent } from '@/utils/thoughtProcessingUtils';

// Define ChartData interface
interface ChartData {
  chartType: string;
  config: {
    title?: string;
    description?: string;
    trend?: {
      percentage?: number;
      direction?: 'up' | 'down';
    };
    footer?: string;
    totalLabel?: string;
    xAxisKey?: string;
  };
  data: any[];
  chartConfig: Record<string, {
    label?: string;
    color?: string;
    stacked?: boolean;
  }>;
}

interface BaseThought {
  type: string;
  content: string;
  timestamp?: string;
  node?: string;
  from_router?: boolean;
  id: string;
  category?: 'setup' | 'analysis' | 'tool' | 'result' | 'error' | 'visualization_data' | 'screenshot' | 'user_input' | 'user_control';
  technical_details?: Record<string, any>;
  visualization?: {
    chart_data: ChartData;
    chart_type: string;
    chart_title?: string;
  };
}

type Thought = BaseThought;
type PartialThought = Omit<BaseThought, 'id'> & { id?: string };
type ThoughtEventData = Omit<BaseThought, 'id' | 'content'> & { 
  content?: string;
  message?: string;
};

export function useThoughtProcess(sessionId?: string) {
  const [thoughts, setThoughts] = useState<Thought[]>([]);
  const [connected, setConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [visualization, setVisualization] = useState<ChartData | null>(null);
  const [screenshots, setScreenshots] = useState<Record<string, string>>({});
  const eventSourceRef = useRef<EventSource | null>(null);
  const previousSessionRef = useRef<string | undefined>(undefined);
  const thoughtsRef = useRef<Thought[]>(thoughts);

  // Update thoughtsRef when thoughts change
  useEffect(() => {
    thoughtsRef.current = thoughts;
  }, [thoughts]);


  const updateThoughts = useCallback((newThought: PartialThought) => {
    const thoughtWithId = {
      ...newThought,
      id: newThought.id || generateId('thought')
    } as Thought;
    
    setThoughts(prevThoughts => [...prevThoughts, thoughtWithId]);
  }, [generateId]);
  
  const normalizeThoughtData = useCallback((data: ThoughtEventData): Thought => {
    // Add timestamp if not present
    const currentTimestamp = data.timestamp || new Date().toISOString();
    
    // User input handling
    if (data.type === 'question') {
      return {
        ...data,
        id: generateId('user-question'),
        type: 'question',
        node: 'User',
        category: 'user_input',
        content: data.content || '',
        timestamp: currentTimestamp
      } as Thought;
    } 
    
    // Browser screenshot handling
    if (data.type === 'visualization' || 
        data.category === 'screenshot' || 
        (data.category === 'visualization_data' && 
         data.technical_details?.screenshot)) {
      
      let content = data.content || 'Browser screenshot';
      let url = '';
      
      if (data.technical_details?.url) {
        url = data.technical_details.url;
      } else if (data.technical_details?.result?.url) {
        url = data.technical_details.result.url;
      } else if (data.technical_details?.screenshot?.url) {
        url = data.technical_details.screenshot.url;
      } else if (data.technical_details?.arguments?.url) {
        url = data.technical_details.arguments.url;
      }
      
      return {
        ...data,
        id: generateId('browser-shot'),
        type: 'visualization',
        node: 'Browser',
        category: 'screenshot',
        content,
        timestamp: currentTimestamp,
        technical_details: {
          ...(data.technical_details || {}),
          url 
        }
      } as Thought;
    }
    
    // Tool call handling - specific to Agent
    if (data.type === 'tool_call' && data.technical_details?.tool_name) {
      const toolName = data.technical_details.tool_name;
      const args = data.technical_details.arguments || {};
      
      // Parse tool arguments to display natural language request
      let content = data.content || '';
      if (toolName === 'act' && typeof args.instruction === 'string') {
        content = `Instructing browser: "${args.instruction}"`;
      } else if (toolName === 'navigate' && typeof args.url === 'string') {
        content = `Navigating to: ${args.url}`;
      } else if (toolName === 'extract_data' && typeof args.description === 'string') {
        content = `Extracting data: ${args.description}`;
      }
    
      return {
        ...data,
        id: generateId('agent-tool'),
        type: 'tool_call',
        node: 'Agent',
        category: 'tool',
        content,
        timestamp: currentTimestamp
      } as Thought;
    }
    
    // Tool result handling - for NovaAct responses
    if (data.type === 'tool_result' && data.technical_details?.tool_name) {
      const result = data.technical_details.result || {};
      return {
        ...data,
        id: generateId('nova-result'),
        type: 'tool_result',
        node: 'NovaAct',
        category: 'tool',
        content: result.message || data.content || 'Tool execution complete',
        timestamp: currentTimestamp
      } as Thought;
    }
    
    // Handle reasoning/thinking from llm
    if (data.type === 'reasoning' || data.type === 'thinking' || data.type === 'rationale') {
      return {
        ...data,
        id: generateId('reasoning'),
        type: 'reasoning',
        node: data.node || 'Agent',
        category: data.category || 'analysis',
        content: data.content || '',
        timestamp: currentTimestamp
      } as Thought;
    }
    
    // Handle user control events (Take Control/Release Control)
    if (data.type === 'user_control' || data.category === 'user_control') {
      return {
        ...data,
        id: generateId('user-control'),
        type: 'user_control',
        node: data.node || 'User Control',
        category: 'user_control',
        content: data.content || '',
        timestamp: currentTimestamp
      } as Thought;
    }
    
    // Default case - catch all other callbacks
    const nodeType = data.node?.toLowerCase() || '';
    let nodeCategory = 'Others';
    
    if (nodeType.includes('browser')) nodeCategory = 'Browser';
    else if (nodeType.includes('nova') || nodeType.includes('act')) nodeCategory = 'NovaAct';
    else if (nodeType.includes('agent') || nodeType.includes('llm')) nodeCategory = 'Agent';
    
    if (data.node === 'Others') {
      return {
        ...data,
        id: generateId('others-event'),
        type: data.type,
        node: 'Others',
        content: data.content || data.message || '',
        timestamp: currentTimestamp
      } as Thought;
    }
  
    return {
      ...data,
      id: generateId('thought'),
      type: data.type || 'reasoning',
      node: nodeCategory, 
      content: data.content || data.message || '',
      timestamp: currentTimestamp
    } as Thought;
  }, [generateId]);
  
  // Handle direct user message additions
  useEffect(() => {
    const unsubscribeUserMessage = subscribeToEvent.userMessageAdded((detail) => {
      const normalizedThought: Thought = {
        id: generateId('user-question'),
        type: 'question',
        node: 'User',
        category: 'user_input',
        content: detail.content,
        timestamp: detail.timestamp,
        technical_details: detail.fileUpload ? { fileUpload: detail.fileUpload } : undefined
      };
      
      updateThoughts(normalizedThought);
    });
    
    return () => {
      unsubscribeUserMessage();
    };
  }, [generateId, updateThoughts]);
  

  const handleEventData = useCallback((data: any) => {
    try {
      // Handle task status events
      if (data.type === 'task_status') {
        if (data.status === 'start') {
          dispatchEvent.taskStatusUpdate({
            status: 'start',
            sessionId: sessionId || ''
          });
        } else if (data.status === 'complete' || data.final_answer) {
          dispatchEvent.taskStatusUpdate({
            status: 'complete',
            sessionId: sessionId || '',
            final_answer: data.final_answer
          });
        }
        return; // Early return for task_status events
      }
      
      if (data.type === 'connected') {
        setConnected(true);
        setError(null);
        return; 
      } else if (data.type === 'error') {
        setError(data.message);
        return;
      } else if (data.type === 'complete') {
        setIsComplete(true);
        return;
      }
      
      if (shouldFilterEvent(data)) {
        return;
      }
      
      // Ensure timestamp exists and is standardized
      if (!data.timestamp) {
        data.timestamp = new Date().toISOString();
      }
      
      const normalizedThought = normalizeThoughtData(data);
      
      // Calculate processing time if needed
      calculateProcessingTime(data, normalizedThought, thoughtsRef.current);
      
      if ((data.category === 'screenshot' || data.category === 'visualization_data') && 
          data.technical_details && data.technical_details.screenshot) {
        
        const screenshotData = data.technical_details.screenshot;
        if (screenshotData && screenshotData.data) {
          const screenshotId = `screenshot-${Date.now()}`;
          setScreenshots(prev => ({
            ...prev,
            [screenshotId]: screenshotData.data
          }));
          
          let url = '';
          if (data.technical_details?.url) {
            url = data.technical_details.url;
          } else if (data.technical_details?.result?.url) {
            url = data.technical_details.result.url;
          } else if (screenshotData.url) {
            url = screenshotData.url;
          } else if (data.technical_details?.arguments?.url) {
            url = data.technical_details.arguments.url;
          }
          
          // Store screenshot reference in thought
          normalizedThought.technical_details = {
            ...(normalizedThought.technical_details || {}),
            screenshotId: screenshotId,
            url: url 
          };
  
          if (url && !normalizedThought.content.includes(url)) {
            normalizedThought.content = `Browser screenshot from: ${url}`;
          }
        }
      }
      
      // Handle chart visualizations
      if (data.category === 'visualization_data' && data.visualization) {
        setVisualization(data.visualization.chart_data);
  
        const chartData = data.visualization.chart_data;
        if (chartData && chartData.chartType && chartData.data && Array.isArray(chartData.data)) {
          dispatchEvent.visualizationReady({
            chartData: chartData,
            chartTitle: data.visualization.chart_title
          });
          
          if (sessionId) {
            // Include processing time in the completion event if available
            let content = `Visualization generated: ${data.visualization.chart_title || 'Chart'}`;
            if (normalizedThought.technical_details?.processing_time_sec) {
              content += ` (${normalizedThought.technical_details.processing_time_sec}s)`;
            }
            
            dispatchEvent.thoughtCompletion({
              type: 'result',
              content,
              sessionId: sessionId
            });
          }
        }
      }
      
      if (sessionId && 
          ((data.node === 'Answer' || data.category === 'result') || 
           (data.type === 'answer' || data.type === 'result'))) {
        
        // Include processing time in the completion event if available
        let content = normalizedThought.content || '';
        
        dispatchEvent.thoughtCompletion({
          type: 'answer',
          content,
          sessionId: sessionId,
          technical_details: normalizedThought.technical_details
        });
      }
      
      updateThoughts(normalizedThought);
    } catch (err) {
      console.error(`Error processing event data:`, err);
    }
  }, [updateThoughts, normalizeThoughtData, sessionId]);
  

  const setupEventSource = useCallback((sessionId: string) => {
    if (!sessionId) return null;
    
    const sseUrl = `/api/assistant/thoughts/${sessionId}`;
    
    try {
      const eventSource = new EventSource(sseUrl, { withCredentials: false });
      
      eventSource.onopen = () => {
        setConnected(true);
        setError(null);
      };
      
      eventSource.onerror = () => {
        if (eventSource.readyState === EventSource.CLOSED) {
          setConnected(false);
          setError('Connection to thought process stream failed');
        }
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleEventData(data);
        } catch (err) {
          console.error(`Error processing SSE message:`, err);
        }
      };
      
      return eventSource;
    } catch (error) {
      console.error(`Error setting up EventSource:`, error);
      setError('Failed to establish connection');
      return null;
    }
  }, [handleEventData]);
  
  useEffect(() => {
    if (sessionId && sessionId !== previousSessionRef.current) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      
      // Only clear thoughts when switching to a completely different session
      // Don't clear when first sessionId is set (previousSessionRef.current is undefined)
      if (previousSessionRef.current !== undefined) {
        setThoughts([]);
        setScreenshots({});
      }
      
      setError(null);
      setIsComplete(false);
      
      const newEventSource = setupEventSource(sessionId);
      if (newEventSource) {
        eventSourceRef.current = newEventSource;
        previousSessionRef.current = sessionId;
      }
    }
    
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [sessionId, setupEventSource]);

  return { 
    thoughts, 
    connected, 
    error, 
    isComplete,
    visualization,
    screenshots
  };
}

export default useThoughtProcess;