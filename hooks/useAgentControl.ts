import { useState, useCallback } from 'react';
import { toast } from "@/hooks/use-toast";
import { apiRequest } from '@/utils/api';

interface AgentStatus {
  session_id: string;
  processing: boolean;
  can_stop: boolean;
  started_at?: number;
  details?: Record<string, any>;
}

interface UseAgentControlReturn {
  canStopAgent: boolean;
  isLoading: boolean;
  isStopInProgress: boolean;
  stopAgent: () => Promise<void>;
  setCanStopAgent: (canStop: boolean) => void;
  setIsStopInProgress: (inProgress: boolean) => void;
}

export function useAgentControl(sessionId?: string): UseAgentControlReturn {
  const [canStopAgent, setCanStopAgent] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isStopInProgress, setIsStopInProgress] = useState(false);

  // No status refresh needed - managed by ThoughtProcess events

  const stopAgent = useCallback(async () => {
    if (!sessionId || !canStopAgent) {
      return;
    }

    setIsLoading(true);
    try {
      const response = await apiRequest(`/agent/stop/${sessionId}`, {
        method: 'POST',
      });

      if (response.ok) {
        const data = await response.json();
        
        // Set stop in progress state
        setIsStopInProgress(true);
        
        toast({
          title: "Stop requested",
          description: "Agent is finishing current task and will stop gracefully.",
        });
        
        // Status will be updated via ThoughtProcess events when actually stopped
      } else {
        const errorData = await response.json();
        toast({
          title: "Failed to stop agent",
          description: errorData.detail || "Unable to stop agent.",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error('Failed to stop agent:', error);
      toast({
        title: "Error",
        description: "Failed to communicate with server.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, canStopAgent]);

  return {
    canStopAgent,
    isLoading,
    isStopInProgress,
    stopAgent,
    setCanStopAgent,
    setIsStopInProgress,
  };
}