'use client';

import React, { useState } from 'react';
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
  Power, 
  Hand, 
  Square,
  Settings,
  ChevronUp
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

interface BrowserControlProps {
  sessionId?: string;
  isThinking?: boolean;
  onTerminateSession?: () => Promise<void>;
  onStopAgent?: () => void;
  onTakeControl?: () => void;
}

function BrowserControl({ 
  sessionId, 
  isThinking = false, 
  onTerminateSession,
  onStopAgent,
  onTakeControl 
}: BrowserControlProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleTerminateSession = async () => {
    if (!sessionId) {
      toast({
        title: "No active session",
        description: "There's no browser session to terminate.",
        variant: "destructive"
      });
      return;
    }

    try {
      setIsLoading(true);
      if (onTerminateSession) {
        await onTerminateSession();
      }
      
      toast({
        title: "Session terminated",
        description: "Browser session has been successfully terminated.",
      });
      setIsOpen(false);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to terminate browser session.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopAgent = () => {
    if (onStopAgent) {
      onStopAgent();
    }
    toast({
      title: "Agent stopped",
      description: "Agent task has been interrupted.",
    });
    setIsOpen(false);
  };

  const handleTakeControl = () => {
    if (onTakeControl) {
      onTakeControl();
    }
    toast({
      title: "Control taken",
      description: "You now have manual control over the browser.",
    });
    setIsOpen(false);
  };

  const hasActiveSession = Boolean(sessionId);

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
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
          
          <DropdownMenuItem 
            onClick={handleTakeControl}
            disabled={!hasActiveSession}
            className="cursor-pointer"
          >
            <Hand className="h-4 w-4 mr-2" />
            Take Control
          </DropdownMenuItem>
          
          <DropdownMenuItem 
            onClick={handleStopAgent}
            disabled={!isThinking}
            className="cursor-pointer"
          >
            <Square className="h-4 w-4 mr-2" />
            Stop Agent
            {isThinking && (
              <span className="ml-auto text-xs bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 px-1.5 py-0.5 rounded">
                Active
              </span>
            )}
          </DropdownMenuItem>
          
          <DropdownMenuSeparator />
          
          <DropdownMenuItem 
            onClick={handleTerminateSession}
            disabled={!hasActiveSession || isLoading}
            className="cursor-pointer text-destructive focus:text-destructive"
          >
            <Power className="h-4 w-4 mr-2" />
            {isLoading ? "Terminating..." : "Terminate Session"}
            {hasActiveSession && (
              <span className="ml-auto text-xs bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-1.5 py-0.5 rounded">
                Active
              </span>
            )}
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