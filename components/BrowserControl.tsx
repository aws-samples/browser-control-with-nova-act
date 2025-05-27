'use client';

import React, { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator 
} from "@/components/ui/dropdown-menu";
import { 
  Globe, 
  Hand, 
  Square,
  Settings,
  ChevronUp,
  X
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { useBrowserControl } from "@/hooks/useBrowserControl";
import { useAgentControl } from "@/hooks/useAgentControl";
import { subscribeToEvent } from '@/services/eventService';

interface BrowserControlProps {
  sessionId?: string;
  isThinking?: boolean;
  onStopAgent?: () => void;
  onTakeControl?: () => void;
  onUserControlStatusChange?: (isInProgress: boolean) => void;
}

function BrowserControl({ 
  sessionId, 
  isThinking = false, 
  onStopAgent,
  onTakeControl,
  onUserControlStatusChange 
}: BrowserControlProps) {
  const [isOpen, setIsOpen] = useState(false);
  const browserControl = useBrowserControl(sessionId);
  const agentControl = useAgentControl(sessionId);

  // Notify parent component about user control status changes
  useEffect(() => {
    if (onUserControlStatusChange) {
      onUserControlStatusChange(browserControl.isUserControlInProgress);
    }
  }, [browserControl.isUserControlInProgress, onUserControlStatusChange]);

  // Subscribe to task status events to manage agent control state
  useEffect(() => {
    if (!sessionId) return;

    const unsubscribe = subscribeToEvent.taskStatusUpdate(({ status }) => {
      if (status === 'start') {
        agentControl.setCanStopAgent(true);
      } else if (status === 'complete') {
        agentControl.setCanStopAgent(false);
      }
    });

    return unsubscribe;
  }, [sessionId, agentControl]);


  const handleStopAgent = async () => {
    // Use the new agent control hook
    await agentControl.stopAgent();
    
    // Call the original callback if provided
    if (onStopAgent) {
      onStopAgent();
    }
    
    setIsOpen(false);
  };

  const handleTakeControl = async () => {
    try {
      await browserControl.actions.takeControl();
      if (onTakeControl) {
        onTakeControl();
      }
      // Refresh status after control change
      await browserControl.actions.refreshStatus();
      setIsOpen(false);
    } catch (error) {
      console.error('Take control failed:', error);
    }
  };

  const handleReleaseControl = async () => {
    try {
      await browserControl.actions.releaseControl();
      // The toast is already handled in the hook
      // Refresh status after control change
      await browserControl.actions.refreshStatus();
      setIsOpen(false);
    } catch (error) {
      console.error('Release control failed:', error);
      toast({
        title: "Error",
        description: "Failed to release control.",
        variant: "destructive"
      });
    }
  };

  const handleCloseBrowser = async () => {
    try {
      await browserControl.actions.closeBrowser();
      setIsOpen(false);
    } catch (error) {
      console.error('Browser close failed:', error);
    }
  };


  const hasActiveSession = browserControl.hasActiveSession;

  const handleDropdownOpenChange = async (open: boolean) => {
    if (open && sessionId && !isThinking) {
      // Only refresh browser status when not thinking/processing
      // Agent status is managed by ThoughtProcess events
      await browserControl.actions.refreshStatus();
    }
    setIsOpen(open);
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <DropdownMenu open={isOpen} onOpenChange={handleDropdownOpenChange}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="bg-background/80 backdrop-blur-sm border-border/50 hover:bg-accent/80 transition-all duration-200 shadow-lg"
          >
            <Globe className="h-4 w-4 mr-2" />
            Browser
            <ChevronUp className={`h-3 w-3 ml-2 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
          </Button>
        </DropdownMenuTrigger>
        
        <DropdownMenuContent 
          align="end" 
          className="w-56 bg-background/95 backdrop-blur-sm border-border/50"
          sideOffset={8}
        >
          <div className="px-2 py-1.5 text-sm font-medium text-muted-foreground">
            Browser Controls
          </div>
          
          <DropdownMenuSeparator />
          
          {isThinking ? (
            <DropdownMenuItem 
              disabled={true}
              className="cursor-not-allowed opacity-50"
            >
              <Hand className="h-4 w-4 mr-2" />
              Browser Control
              <span className="ml-auto text-xs text-muted-foreground">
                Processing...
              </span>
            </DropdownMenuItem>
          ) : browserControl.browserState?.is_headless ? (
            <DropdownMenuItem 
              onClick={handleTakeControl}
              disabled={!hasActiveSession}
              className="cursor-pointer"
            >
              <Hand className="h-4 w-4 mr-2" />
              Take Control
              <span className="ml-auto text-xs text-muted-foreground">
                Show Browser
              </span>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem 
              onClick={handleReleaseControl}
              disabled={!hasActiveSession}
              className="cursor-pointer"
            >
              <Hand className="h-4 w-4 mr-2" />
              Release Control
              <span className="ml-auto text-xs text-muted-foreground">
                Hide Browser
              </span>
            </DropdownMenuItem>
          )}
          
          <DropdownMenuItem 
            onClick={handleStopAgent}
            disabled={!isThinking || !agentControl.canStopAgent}
            className="cursor-pointer"
          >
            <Square className="h-4 w-4 mr-2" />
            Stop Agent
            {isThinking && agentControl.canStopAgent && (
              <span className="ml-auto text-xs bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 px-1.5 py-0.5 rounded">
                Active
              </span>
            )}
          </DropdownMenuItem>
          
          <DropdownMenuSeparator />
          
          <DropdownMenuItem 
            onClick={handleCloseBrowser}
            disabled={isThinking || !hasActiveSession || browserControl.isLoading}
            className="cursor-pointer"
          >
            <X className="h-4 w-4 mr-2" />
            {isThinking ? "Processing..." : "Close Browser"}
          </DropdownMenuItem>
          
          
          {!hasActiveSession && (
            <div className="px-2 py-1.5 text-xs text-muted-foreground">
              No active browser session
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export default BrowserControl;