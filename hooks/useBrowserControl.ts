import { useState, useCallback, useEffect } from 'react';
import { apiRequest } from '@/utils/api';
import { toast } from "@/hooks/use-toast";
import { createLogger } from '@/utils/logger';
import { ErrorHandler } from '@/utils/errorHandler';

const logger = createLogger('useBrowserControl');

export interface BrowserState {
  session_id: string;
  status: string;
  current_url: string;
  page_title: string;
  last_updated: number;
  error_message: string;
  has_screenshot: boolean;
  initialization_time?: number;
  is_headless: boolean;
  browser_initialized: boolean;
  has_active_session: boolean;
}

export interface BrowserControlState {
  isLoading: boolean;
  hasActiveSession: boolean;
  sessionId?: string;
  browserState?: BrowserState;
  isUserControlInProgress: boolean;
}

export interface BrowserControlActions {
  initializeBrowser: (headless?: boolean, url?: string) => Promise<void>;
  navigateToUrl: (url: string) => Promise<void>;
  takeScreenshot: (maxWidth?: number, quality?: number) => Promise<string>;
  executeAction: (instruction: string, maxSteps?: number) => Promise<void>;
  extractData: (description: string, schemaType?: string, customSchema?: any) => Promise<any>;
  closeBrowser: () => Promise<void>;
  restartBrowser: (headless?: boolean, url?: string) => Promise<void>;
  terminateSession: () => Promise<void>;
  validateSession: (sessionId: string) => Promise<boolean>;
  refreshStatus: () => Promise<void>;
  takeControl: () => Promise<void>;
  releaseControl: () => Promise<void>;
}

export interface UseBrowserControlReturn extends BrowserControlState {
  actions: BrowserControlActions;
}

export const useBrowserControl = (sessionId?: string): UseBrowserControlReturn => {
  const [isLoading, setIsLoading] = useState(false);
  const [hasActiveSession, setHasActiveSession] = useState(false);
  const [browserState, setBrowserState] = useState<BrowserState | undefined>();
  const [isUserControlInProgress, setIsUserControlInProgress] = useState(false);

  const validateSession = useCallback(async (targetSessionId: string): Promise<boolean> => {
    try {
      const response = await apiRequest(`/router/validate-session/${targetSessionId}`, {
        method: 'GET'
      });
      
      const data = await response.json();
      return data.valid === true;
    } catch (error) {
      logger.error('Error validating session:', error);
      return false;
    }
  }, []);

  const checkBrowserStatus = useCallback(async (targetSessionId: string) => {
    try {
      logger.info('Checking browser status for session:', { sessionId: targetSessionId });
      const response = await apiRequest(`/browser/session/${targetSessionId}/browser-status`, {
        method: 'GET'
      });
      
      if (!response.ok) {
        logger.error('Browser status API failed:', { status: response.status, statusText: response.statusText });
        setHasActiveSession(false);
        return;
      }
      
      const data = await response.json();
      logger.info('Browser status API response:', data);
      
      if (data.status === 'success') {
        const hasActive = data.has_active_session;
        setHasActiveSession(hasActive);
        
        // Update browser state if available
        if (data.browser_state) {
          setBrowserState(data.browser_state);
        }
        
        logger.info('Browser status updated', { 
          sessionId: targetSessionId, 
          hasActiveSession: hasActive,
          browserInitialized: data.browser_initialized,
          currentUrl: data.current_url,
          isHeadless: data.is_headless,
          rawData: data
        });
      } else {
        logger.warn('Browser status API returned error:', data);
        setHasActiveSession(false);
        setBrowserState(undefined);
      }
    } catch (error) {
      logger.error('Error checking browser status:', error);
      setHasActiveSession(false);
    }
  }, []);

  // Check browser status only when sessionId changes
  useEffect(() => {
    if (sessionId) {
      checkBrowserStatus(sessionId);
    } else {
      setHasActiveSession(false);
      setBrowserState(undefined);
    }
  }, [sessionId, checkBrowserStatus]);

  const handleMCPCall = useCallback(async (toolName: string, args: any = {}) => {
    if (!sessionId) {
      throw new Error('No active session available');
    }

    // Skip validation for close_browser as session might already be terminating
    if (toolName !== 'close_browser') {
      const isValid = await validateSession(sessionId);
      if (!isValid) {
        throw new Error('Session is not valid or has expired');
      }
    }

    try {
      const response = await apiRequest(`/browser/session/${sessionId}/browser/${toolName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          args: args
        })
      });

      if (!response.ok) {
        throw new Error(`Browser tool API failed with status ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      logger.error(`Error executing browser tool ${toolName}:`, error);
      throw error;
    }
  }, [sessionId, validateSession]);

  const initializeBrowser = useCallback(async (headless: boolean = true, url?: string) => {
    if (!sessionId) {
      throw new Error('No session ID provided');
    }

    setIsLoading(true);
    try {
      await handleMCPCall('initialize_browser', { headless, url });
      
      // Check browser status after initialization
      await checkBrowserStatus(sessionId);
      
      toast({
        title: "Browser initialized",
        description: `Browser session started${url ? ` and navigated to ${url}` : ''}`,
      });
      
      logger.info('Browser initialized successfully', { sessionId, headless, url });
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_initialization', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to initialize browser:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall, checkBrowserStatus]);

  const navigateToUrl = useCallback(async (url: string) => {
    setIsLoading(true);
    try {
      await handleMCPCall('navigate', { url });
      
      toast({
        title: "Navigation successful",
        description: `Navigated to ${url}`,
      });
      
      logger.info('Navigation completed', { sessionId, url });
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_navigation', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to navigate:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall]);

  const takeScreenshot = useCallback(async (maxWidth?: number, quality?: number): Promise<string> => {
    setIsLoading(true);
    try {
      const result = await handleMCPCall('take_screenshot', { 
        max_width: maxWidth, 
        quality 
      });
      
      logger.info('Screenshot taken', { sessionId, maxWidth, quality });
      return result.screenshot || result.data?.screenshot || '';
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_screenshot', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to take screenshot:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall]);

  const executeAction = useCallback(async (instruction: string, maxSteps: number = 10) => {
    setIsLoading(true);
    try {
      await handleMCPCall('act', { instruction, max_steps: maxSteps });
      
      toast({
        title: "Action executed",
        description: `Completed: ${instruction}`,
      });
      
      logger.info('Browser action executed', { sessionId, instruction, maxSteps });
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_action', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to execute action:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall]);

  const extractData = useCallback(async (description: string, schemaType?: string, customSchema?: any) => {
    setIsLoading(true);
    try {
      const result = await handleMCPCall('extract_data', { 
        description, 
        schema_type: schemaType, 
        custom_schema: customSchema 
      });
      
      toast({
        title: "Data extracted",
        description: `Extracted data: ${description}`,
      });
      
      logger.info('Data extraction completed', { sessionId, description });
      return result.data || result;
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'data_extraction', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to extract data:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall]);

  const closeBrowser = useCallback(async () => {
    setIsLoading(true);
    try {
      await handleMCPCall('close_browser');
      
      // Check browser status after closing
      if (sessionId) {
        await checkBrowserStatus(sessionId);
      }
      
      toast({
        title: "Browser closed",
        description: "Browser window has been closed. Session remains active.",
      });
      
      logger.info('Browser closed successfully', { sessionId });
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_close', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to close browser:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall, checkBrowserStatus]);

  const restartBrowser = useCallback(async (headless: boolean = true, url?: string) => {
    setIsLoading(true);
    try {
      await handleMCPCall('restart_browser', { headless, url });
      setHasActiveSession(true);
      
      toast({
        title: "Browser restarted",
        description: `Browser session restarted${url ? ` and navigated to ${url}` : ''}`,
      });
      
      logger.info('Browser restarted successfully', { sessionId, headless, url });
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'browser_restart', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to restart browser:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleMCPCall]);

  const terminateSession = useCallback(async () => {
    if (!sessionId) {
      throw new Error('No active session to terminate');
    }

    setIsLoading(true);
    try {
      const response = await apiRequest(`/router/session/${sessionId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();

      if (data.status === 'success') {
        setHasActiveSession(false);
        
        toast({
          title: "Session terminated",
          description: "Browser session has been successfully terminated",
        });
        
        logger.info('Session terminated successfully', { sessionId });
      } else {
        throw new Error(data.message || 'Failed to terminate session');
      }
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'session_termination', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to terminate session:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const refreshStatus = useCallback(async () => {
    if (sessionId) {
      await checkBrowserStatus(sessionId);
    }
  }, [sessionId, checkBrowserStatus]);

  const takeControl = useCallback(async () => {
    if (!sessionId) {
      throw new Error('No active session available');
    }

    setIsLoading(true);
    setIsUserControlInProgress(true);
    try {
      logger.info('Taking manual control of browser', { sessionId });
      
      const response = await apiRequest(`/browser/session/${sessionId}/take-control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`Take control API failed with status ${response.status}`);
      }

      const data = await response.json();
      
      if (data.status === 'success') {
        // Force refresh browser status after taking control
        await checkBrowserStatus(sessionId);
        
        toast({
          title: "Manual control activated",
          description: "Browser is now visible and ready for manual interaction. You can directly control the browser window.",
        });
        
        logger.info('Manual control activated successfully', { sessionId });
      } else {
        throw new Error(data.message || 'Failed to take control');
      }
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'take_control', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to take control:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
      setIsUserControlInProgress(false);
    }
  }, [sessionId, checkBrowserStatus]);


  const releaseControl = useCallback(async () => {
    if (!sessionId) {
      throw new Error('No active session available');
    }

    setIsLoading(true);
    setIsUserControlInProgress(true);
    try {
      logger.info('Releasing manual control of browser', { sessionId });
      
      const response = await apiRequest(`/browser/session/${sessionId}/release-control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`Release control API failed with status ${response.status}`);
      }

      const data = await response.json();
      
      if (data.status === 'success') {
        // Force refresh browser status after releasing control
        await checkBrowserStatus(sessionId);
        
        toast({
          title: "Control released",
          description: "Browser returned to headless mode.",
        });
        
        logger.info('Manual control released successfully', { sessionId });
      } else {
        throw new Error(data.message || 'Failed to release control');
      }
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'release_control', {
        showToast: true,
        toast,
        showDetails: true
      });
      
      logger.error('Failed to release control:', standardError);
      throw error;
    } finally {
      setIsLoading(false);
      setIsUserControlInProgress(false);
    }
  }, [sessionId, checkBrowserStatus]);

  return {
    isLoading,
    hasActiveSession,
    sessionId,
    browserState,
    isUserControlInProgress,
    actions: {
      initializeBrowser,
      navigateToUrl,
      takeScreenshot,
      executeAction,
      extractData,
      closeBrowser,
      restartBrowser,
      terminateSession,
      validateSession,
      refreshStatus,
      takeControl,
      releaseControl,
    },
  };
};