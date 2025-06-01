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
  const [lastBrowserState, setLastBrowserState] = useState<{url: string, title: string} | null>(null);
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
        // Don't reset stop in progress here - only when task actually completes
      } else if (status === 'complete' || status === 'stopped') {
        // Only clear states when task is actually completed or stopped
        agentControl.setCanStopAgent(false);
        agentControl.setIsStopInProgress(false);
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
      // Save current browser state before taking control
      if (browserControl.browserState?.current_url) {
        setLastBrowserState({
          url: browserControl.browserState.current_url,
          title: browserControl.browserState.page_title || ''
        });
        console.log('Saved browser state before taking control:', {
          url: browserControl.browserState.current_url,
          title: browserControl.browserState.page_title
        });
      }
      
      await browserControl.actions.takeControl();
      if (onTakeControl) {
        onTakeControl();
      }
      setIsOpen(false);
    } catch (error) {
      console.error('Take control failed:', error);
    }
  };

  const handleReleaseControl = async () => {
    try {
      // First try to release control normally
      try {
        await browserControl.actions.releaseControl();
        console.log('Released control successfully');
        setIsOpen(false);
        return;
      } catch (releaseError) {
        console.log('Failed to release control, checking if browser was closed:', releaseError);
        
        // If release fails, it might be because the browser was closed
        // Check current browser status
        await browserControl.actions.refreshStatus();
        
        // Wait a moment for status to update
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // If browser is not active and we have saved state, reinitialize
        if (!browserControl.hasActiveSession && lastBrowserState) {
          console.log('Browser was closed, reinitializing with saved state:', lastBrowserState);
          
          toast({
            title: "Browser Recovery",
            description: "Browser was closed. Reinitializing with last known state...",
          });
          
          // Initialize browser in headless mode with the last known URL
          await browserControl.actions.initializeBrowser(true, lastBrowserState.url);
          
          toast({
            title: "Browser Recovered",
            description: `Browser reinitialized at ${lastBrowserState.url}`,
          });
          
          // Clear saved state after successful recovery
          setLastBrowserState(null);
        } else {
          // If we can't recover, just show the original error
          throw releaseError;
        }
      }
      
      setIsOpen(false);
    } catch (error) {
      console.error('Release control failed:', error);
      toast({
        title: "Error",
        description: "Failed to release control and recover browser.",
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

  const handleDropdownOpenChange = (open: boolean) => {
    // Refresh browser status when dropdown opens, but only if not thinking
    if (open && !isThinking && sessionId) {
      console.log('Refreshing browser status for session:', sessionId);
      browserControl.actions.refreshStatus();
    }
    setIsOpen(open);
  };

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <DropdownMenu open={isOpen} onOpenChange={handleDropdownOpenChange}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="lg"
            className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 backdrop-blur-md border-blue-200/30 dark:border-blue-700/30 hover:from-blue-500/20 hover:to-purple-500/20 hover:border-blue-300/50 dark:hover:border-blue-600/50 transition-all duration-300 shadow-xl shadow-blue-500/10 dark:shadow-blue-400/5 px-6 py-3 text-base font-medium"
          >
            <Globe className="h-5 w-5 mr-3 text-blue-600 dark:text-blue-400" />
            <span className="text-foreground/90">Browser Control</span>
            <ChevronUp className={`h-4 w-4 ml-3 transition-transform duration-300 text-blue-600 dark:text-blue-400 ${isOpen ? 'rotate-180' : ''}`} />
          </Button>
        </DropdownMenuTrigger>
        
        <DropdownMenuContent 
          align="end" 
          className="w-64 bg-background/95 backdrop-blur-md border-blue-200/30 dark:border-blue-700/30 shadow-xl shadow-blue-500/10 dark:shadow-blue-400/5 rounded-xl"
          sideOffset={12}
        >
          <div className="px-4 py-3 text-sm font-semibold text-blue-700 dark:text-blue-300 bg-blue-50/50 dark:bg-blue-950/50 rounded-t-xl">
            Browser Controls
          </div>
          
          <DropdownMenuSeparator />
          
          {isThinking ? (
            <DropdownMenuItem 
              disabled={true}
              className="cursor-not-allowed opacity-50 px-4 py-3 text-base"
            >
              <Hand className="h-5 w-5 mr-3 text-gray-400" />
              <div className="flex-1">
                <div className="font-medium">Browser Control</div>
                <div className="text-sm text-muted-foreground">Processing...</div>
              </div>
            </DropdownMenuItem>
          ) : browserControl.browserState?.is_headless ? (
            <DropdownMenuItem 
              onClick={handleTakeControl}
              disabled={!hasActiveSession}
              className="cursor-pointer px-4 py-3 text-base hover:bg-green-50 dark:hover:bg-green-950/30"
            >
              <Hand className="h-5 w-5 mr-3 text-green-600 dark:text-green-400" />
              <div className="flex-1">
                <div className="font-medium">Take Control</div>
                <div className="text-sm text-muted-foreground">Show Browser</div>
              </div>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem 
              onClick={handleReleaseControl}
              disabled={!hasActiveSession}
              className="cursor-pointer px-4 py-3 text-base hover:bg-orange-50 dark:hover:bg-orange-950/30"
            >
              <Hand className="h-5 w-5 mr-3 text-orange-600 dark:text-orange-400" />
              <div className="flex-1">
                <div className="font-medium">Release Control</div>
                <div className="text-sm text-muted-foreground">Hide Browser</div>
              </div>
            </DropdownMenuItem>
          )}
          
          <DropdownMenuItem 
            onClick={handleStopAgent}
            disabled={!isThinking || !agentControl.canStopAgent || agentControl.isStopInProgress}
            className="cursor-pointer px-4 py-3 text-base hover:bg-red-50 dark:hover:bg-red-950/30"
          >
            <Square className="h-5 w-5 mr-3 text-red-600 dark:text-red-400" />
            <div className="flex-1">
              <div className="font-medium flex items-center gap-2">
                Stop Agent
                {agentControl.isStopInProgress ? (
                  <span className="text-xs bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 px-2 py-1 rounded-full font-semibold">
                    Stopping...
                  </span>
                ) : isThinking && agentControl.canStopAgent ? (
                  <span className="text-xs bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 px-2 py-1 rounded-full font-semibold">
                    Active
                  </span>
                ) : null}
              </div>
              <div className="text-sm text-muted-foreground">
                {agentControl.isStopInProgress ? "Finishing current task..." : "Stop current task"}
              </div>
            </div>
          </DropdownMenuItem>
          
          <DropdownMenuSeparator />
          
          <DropdownMenuItem 
            onClick={handleCloseBrowser}
            disabled={isThinking || !hasActiveSession || browserControl.isLoading}
            className="cursor-pointer px-4 py-3 text-base hover:bg-gray-50 dark:hover:bg-gray-950/30"
          >
            <X className="h-5 w-5 mr-3 text-gray-600 dark:text-gray-400" />
            <div className="flex-1">
              <div className="font-medium">{isThinking ? "Processing..." : "Close Browser"}</div>
              <div className="text-sm text-muted-foreground">End browser session</div>
            </div>
          </DropdownMenuItem>
          
          
          {!hasActiveSession && (
            <div className="px-4 py-3 text-sm text-muted-foreground bg-gray-50/50 dark:bg-gray-950/50 rounded-b-xl">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
                No active browser session
              </div>
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export default BrowserControl;