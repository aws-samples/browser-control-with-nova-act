import { useState, useCallback, useRef, useEffect } from 'react';
import { apiRequest } from '@/utils/api';
import { toast } from "@/hooks/use-toast";
import { readFileAsText, readFileAsBase64, readFileAsPDFText } from "@/utils/fileHandling";
import type { Message, FileUpload, AnalyzeAPIResponse, APIResponse } from '@/types/chat';
import { subscribeToEvent, dispatchEvent } from '@/services/eventService';
import { createLogger } from '@/utils/logger';
import { ErrorHandler } from '@/utils/errorHandler';
import { resetThinkingTimer, calculateProcessingTime as calcProcessingTime } from '@/utils/timerUtils';
import {
  prepareApiMessages,
  createUserMessage,
  createAssistantTextMessage,
  createErrorMessage,
  createVisualizationMessage
} from '@/utils/messageUtils';

const logger = createLogger('useChat');

interface ChatState {
  messages: Message[];
  input: string;
  isLoading: boolean;
  isThinking: boolean;
  currentUpload: FileUpload | null;
  isUploading: boolean;
  queryDetails: AnalyzeAPIResponse[];
  sessionId?: string;
}

interface ChatActions {
  setInput: (input: string) => void;
  handleSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleReset: () => void;
  setCurrentUpload: (upload: FileUpload | null) => void;
  terminateSession: () => Promise<void>;
  stopAgent: () => void;
  takeControl: () => void;
}

export interface UseChatReturn extends ChatState {
  actions: ChatActions;
  fileInputRef: React.RefObject<HTMLInputElement>;
}

type ApiResponseHandler = ({
  apiMessages,
  responseData,
  setterFunctions,
}: {
  apiMessages: any[];
  responseData: any;
  setterFunctions: {
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
    setQueryDetails: React.Dispatch<React.SetStateAction<AnalyzeAPIResponse[]>>;
    setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
    setIsThinking: React.Dispatch<React.SetStateAction<boolean>>;
    setCurrentUpload: React.Dispatch<React.SetStateAction<FileUpload | null>>;
    setSessionId?: React.Dispatch<React.SetStateAction<string | undefined>>;
    originalQuestion: string;
    selectedModel: string;
    selectedRegion: string;
  };
}) => Promise<{
  analyzeTime?: number;
  visualizeTime?: number;
}>;

export const useChat = (selectedModel: string, selectedRegion: string): UseChatReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [currentUpload, setCurrentUpload] = useState<FileUpload | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [queryDetails, setQueryDetails] = useState<AnalyzeAPIResponse[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isSubmitting = useRef(false);
  const thinkingStartTime = useRef<number | null>(null);

  useEffect(() => {
    if (!isThinking && thinkingStartTime.current) {
      thinkingStartTime.current = null;
    }
  }, [isThinking]);
  

  const terminateSession = useCallback(async () => {
    if (!sessionId) {
      throw new Error('No active session to terminate');
    }

    try {
      const response = await apiRequest(`/router/session/${sessionId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();

      if (data.status === 'success') {
        // Clear session-related state
        setSessionId(undefined);
        setIsThinking(false);
        setMessages([]);
        setQueryDetails([]);
        thinkingStartTime.current = null;
        
        logger.info('Session terminated successfully');
      } else {
        throw new Error(data.message || 'Failed to terminate session');
      }
    } catch (error) {
      logger.error('Error terminating session:', error);
      throw error;
    }
  }, [sessionId]);

  const stopAgent = useCallback(() => {
    if (isThinking) {
      setIsThinking(false);
      thinkingStartTime.current = null;
      
      // Dispatch event to stop any ongoing tasks
      dispatchEvent.taskStatusUpdate({
        status: 'stopped',
        sessionId: sessionId || ''
      });
      
      logger.info('Agent task stopped');
    }
  }, [isThinking, sessionId]);

  const takeControl = useCallback(() => {
    // This could be extended to implement actual browser control transfer
    // For now, it's a placeholder that stops the agent
    stopAgent();
    
    toast({
      title: "Control taken",
      description: "You can now interact with the browser manually. The agent has been paused.",
    });
    
    logger.info('Browser control taken by user');
  }, [stopAgent]);

  useEffect(() => {
    const unsubscribeVisualization = subscribeToEvent.visualizationReady(({ chartData, chartTitle }) => {
      if (chartData) {
        const processingTime = calcProcessingTime(thinkingStartTime);
        const timestamp = new Date().toISOString();
        const message = createVisualizationMessage(
          "Here's the visualization based on the data:", 
          { 
            chart_data: chartData, 
            chart_type: chartData.chartType,
            chart_title: chartTitle || chartData.config?.title
          }
        );
        
        if (processingTime) {
          message.technical_details = {
            ...(message.technical_details || {}),
            processing_time_sec: parseFloat(processingTime),
            processing_time_ms: parseFloat(processingTime) * 1000
          };
        }
        
        message.timestamp = timestamp;
        
        setMessages(prev => [...prev, message]);
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      }
    });
    
    const unsubscribeThoughtCompletion = subscribeToEvent.thoughtCompletion(({ type, content, sessionId: eventSessionId, technical_details }) => {
      if (
        (type === 'answer' || type === 'result') && 
        eventSessionId === sessionId &&
        content
      ) {
        const timestamp = new Date().toISOString();
        const message = createAssistantTextMessage(content);
        
        if (technical_details) {
          message.technical_details = {
            ...(message.technical_details || {}),
            ...technical_details
          };
        } else {
          const processingTime = calcProcessingTime(thinkingStartTime);
          if (processingTime) {
            message.technical_details = {
              ...(message.technical_details || {}),
              processing_time_sec: parseFloat(processingTime),
              processing_time_ms: parseFloat(processingTime) * 1000
            };
          }
        }
        
        message.timestamp = timestamp;
        setMessages(prev => [...prev, message]);
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      }
    });
  
    const unsubscribeThoughtStreamComplete = subscribeToEvent.thoughtStreamComplete(({ sessionId: eventSessionId, finalAnswer }) => {
      if (eventSessionId === sessionId) {
        if (finalAnswer) {
          const processingTime = calcProcessingTime(thinkingStartTime);
          const timestamp = new Date().toISOString();
          const message = createAssistantTextMessage(finalAnswer);
          
          if (processingTime) {
            message.technical_details = {
              ...(message.technical_details || {}),
              processing_time_sec: parseFloat(processingTime),
              processing_time_ms: parseFloat(processingTime) * 1000
            };
          }
          
          message.timestamp = timestamp;
          
          setMessages(prev => [...prev, message]);
        }
        
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      }
    });
    
    const unsubscribeTaskStatus = subscribeToEvent.taskStatusUpdate(({ status, sessionId: eventSessionId }) => {
      if (eventSessionId === sessionId) {
        if (status === 'start') {
          // Timer is already started in handleSubmit
          setIsThinking(true);
        } else if (status === 'complete') {
          resetThinkingTimer(setIsThinking, thinkingStartTime);
        }
      }
    });

    // Session cleanup on page unload
    const handleBeforeUnload = async () => {
      if (sessionId) {
        try {
          // Use sendBeacon for reliable cleanup on page unload
          const url = `/api/router/session/${sessionId}/terminate`;
          navigator.sendBeacon(url, '');
        } catch (error) {
          console.error('Failed to terminate session on unload:', error);
        }
      }
    };

    if (sessionId) {
      window.addEventListener('beforeunload', handleBeforeUnload);
      window.addEventListener('pagehide', handleBeforeUnload);
    }
    
    return () => {
      unsubscribeVisualization();
      unsubscribeThoughtCompletion();
      unsubscribeThoughtStreamComplete();
      unsubscribeTaskStatus();
      
      if (sessionId) {
        window.removeEventListener('beforeunload', handleBeforeUnload);
        window.removeEventListener('pagehide', handleBeforeUnload);
      }
    };
  }, [sessionId]);  

  const responseHandlers: Record<string, ApiResponseHandler> = {
    'task_supervisor': async ({ apiMessages, responseData, setterFunctions }) => {
      const { setSessionId, setIsThinking } = setterFunctions;
      const responseSessionId = responseData.input?.session_id;
      const directAnswer = responseData.input?.direct_answer;
  
      if (responseSessionId) {
        setSessionId(responseSessionId);
      } else {
        logger.warn('Missing sessionId in response', { responseData });
      }
      
      if (directAnswer && directAnswer !== "processing") {
        const processingTime = calcProcessingTime(thinkingStartTime);
        const timestamp = new Date().toISOString();
        const message = createAssistantTextMessage(directAnswer);
        
        if (processingTime) {
          message.technical_details = {
            ...(message.technical_details || {}),
            processing_time_sec: parseFloat(processingTime),
            processing_time_ms: parseFloat(processingTime) * 1000
          };
        }
        
        message.timestamp = timestamp;
        
        setMessages(prev => [...prev, message]);
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      } else {
        logger.info('Received processing response, waiting for SSE stream', { sessionId: responseSessionId });
      }
    
      return { analyzeTime: 0 };
    },
    
    'act_agent': async ({ apiMessages, responseData, setterFunctions }) => {
      const { setSessionId, setIsThinking } = setterFunctions;
      const responseSessionId = responseData.input?.session_id;
      const directAnswer = responseData.input?.direct_answer;
  
      if (responseSessionId) {
        setSessionId(responseSessionId);
      } else {
        logger.warn('Missing sessionId in response', { responseData });
      }
      
      if (directAnswer && directAnswer !== "processing") {
        const processingTime = calcProcessingTime(thinkingStartTime);
        const timestamp = new Date().toISOString();
        const message = createAssistantTextMessage(directAnswer);
        
        if (processingTime) {
          message.technical_details = {
            ...(message.technical_details || {}),
            processing_time_sec: parseFloat(processingTime),
            processing_time_ms: parseFloat(processingTime) * 1000
          };
        }
        
        message.timestamp = timestamp;
        
        setMessages(prev => [...prev, message]);
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      } else {
        logger.info('Received processing response, waiting for SSE stream', { sessionId: responseSessionId });
      }
    
      return { analyzeTime: 0 };
    },
    
    'assistant': async ({ apiMessages, responseData, setterFunctions }) => {
      const { setSessionId, setIsThinking } = setterFunctions;
      const responseSessionId = responseData.input?.session_id;
      const directAnswer = responseData.input?.direct_answer;
  
      if (responseSessionId) {
        setSessionId(responseSessionId);
      } else {
        logger.warn('Missing sessionId in response', { responseData });
      }
      
      if (directAnswer && directAnswer !== "processing") {
        const processingTime = calcProcessingTime(thinkingStartTime);
        const timestamp = new Date().toISOString();
        const message = createAssistantTextMessage(directAnswer);
        
        if (processingTime) {
          message.technical_details = {
            ...(message.technical_details || {}),
            processing_time_sec: parseFloat(processingTime),
            processing_time_ms: parseFloat(processingTime) * 1000
          };
        }
        
        message.timestamp = timestamp;
        
        setMessages(prev => [...prev, message]);
        resetThinkingTimer(setIsThinking, thinkingStartTime);
      } else {
        logger.info('Received processing response, waiting for SSE stream', { sessionId: responseSessionId });
      }
    
      return { analyzeTime: 0 };
    }
  };

  const handleSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    
    if (isSubmitting.current || isThinking) return; 
    isSubmitting.current = true;
    
    let answeringTool = 'chat';
  
    if ((!input.trim() && !currentUpload) || isLoading) {
      isSubmitting.current = false;
      return;
    }
    
    const timestamp = new Date().toISOString();
    const userInput = input; // Store input before clearing
    const userMessage = {
      ...createUserMessage(userInput, currentUpload || undefined),
      timestamp
    };
    
    setMessages(prev => [...prev, userMessage]);
    
    // Dispatch user message immediately to thought process
    dispatchEvent.userMessageAdded({
      type: 'question',
      content: userInput,
      node: 'User',
      category: 'user_input',
      timestamp,
      sessionId: sessionId || '', // Empty string if no sessionId yet
      fileUpload: currentUpload || undefined
    });
    
    setInput("");
    setIsLoading(true);
    setIsThinking(true);
    thinkingStartTime.current = Date.now();
  
    try {
      const apiMessages = prepareApiMessages(messages, userMessage);
  
      const routerResponse = await apiRequest('/router', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: apiMessages,
          model: selectedModel,
          region: selectedRegion,
          session_id: sessionId
        }),
      });
      
      if (!routerResponse.ok) {
        throw new Error(`Router API error! status: ${routerResponse.status}`);
      }
      
      const responseData = await routerResponse.json();
      logger.debug('Router API response received', { responseData });
      
      answeringTool = responseData.input?.answering_tool || 'chat';
      
      if (responseData.input?.session_id) {
        setSessionId(responseData.input.session_id);
      } 
      
      if (responseHandlers[answeringTool]) {
        await responseHandlers[answeringTool]({
          apiMessages,
          responseData,
          setterFunctions: {
            setMessages,
            setQueryDetails,
            setIsLoading,
            setIsThinking,
            setCurrentUpload,
            setSessionId,
            originalQuestion: input,
            selectedModel,
            selectedRegion,
          }
        });
      } else {
        throw new Error("Unexpected response type from API");
      }
      
    } catch (error) {
      const standardError = ErrorHandler.handleError(error, 'chat_submission', {
        showToast: true,
        toast,
        showDetails: true,
        showRetry: true
      });
      
      // Create error message with structured error information
      const errorMessage = createErrorMessage(standardError.message);
      if (errorMessage.technical_details) {
        errorMessage.technical_details.error_code = standardError.error_code;
        errorMessage.technical_details.severity = standardError.severity;
      }
      
      setMessages(prev => [...prev, errorMessage]);
      resetThinkingTimer(setIsThinking, thinkingStartTime);
    } finally {
      setIsLoading(false);
      setCurrentUpload(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = ''; 
      }
      
      // Ensure timer is reset in case of any error
      thinkingStartTime.current = null;
  
      setTimeout(() => {
        isSubmitting.current = false;
      }, 500);
    }
  }, [messages, input, currentUpload, isLoading, isThinking, selectedModel, selectedRegion, sessionId]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    let loadingToastRef: { dismiss: () => void } | undefined;

    if (file.type === "application/pdf") {
      loadingToastRef = toast({
        title: "Processing PDF",
        description: "Extracting text content...",
        duration: Infinity,
      });
    }

    try {
      const isImage = file.type.startsWith("image/");
      const isPDF = file.type === "application/pdf";
      let base64Data = "";
      let isText = false;

      if (isImage) {
        base64Data = await readFileAsBase64(file);
        isText = false;
      } else if (isPDF) {
        try {
          const pdfText = await readFileAsPDFText(file);
          base64Data = btoa(encodeURIComponent(pdfText));
          isText = true;
        } catch (error) {
          logger.error('Failed to parse PDF', { fileName: file.name, error: error instanceof Error ? error.message : error }, error instanceof Error ? error : undefined);
          toast({
            title: "PDF parsing failed",
            description: "Unable to extract text from the PDF",
            variant: "destructive",
          });
          return;
        }
      } else {
        try {
          const textContent = await readFileAsText(file);
          base64Data = btoa(encodeURIComponent(textContent));
          isText = true;
        } catch (error) {
          logger.error('Failed to read file as text', { fileName: file.name, fileType: file.type, error: error instanceof Error ? error.message : error }, error instanceof Error ? error : undefined);
          toast({
            title: "Invalid file type",
            description: "File must be readable as text, PDF, or be an image",
            variant: "destructive",
          });
          return;
        }
      }

      setCurrentUpload({
        base64: base64Data,
        fileName: file.name,
        mediaType: isText ? "text/plain" : file.type,
        isText,
      });

      toast({
        title: "File uploaded",
        description: `${file.name} ready to analyze`,
      });
    } catch (error) {
      logger.error('Error processing file', { fileName: file?.name, error: error instanceof Error ? error.message : error }, error instanceof Error ? error : undefined);
      toast({
        title: "Upload failed",
        description: "Failed to process the file",
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
      if (loadingToastRef) {
        loadingToastRef.dismiss();
        if (file.type === "application/pdf") {
          toast({
            title: "PDF Processed",
            description: "Text extracted successfully",
          });
        }
      }
    }
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() || currentUpload) {
        const form = e.currentTarget.form;
        if (form) {
          const submitEvent = new Event("submit", {
            bubbles: true,
            cancelable: true,
          });
          form.dispatchEvent(submitEvent);
        }
      }
    }
  }, [input, currentUpload]);

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const textarea = event.target;
      setInput(textarea.value);
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 300)}px`;
    },
    []
  );

  const handleReset = useCallback(() => {
    setMessages([]);
    setQueryDetails([]);
    setInput("");
    setCurrentUpload(null);
    setIsThinking(false);
    setSessionId(undefined);
    thinkingStartTime.current = null;
        
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    toast({
      title: "Chat Reset",
      description: "All chat history and visualizations have been cleared.",
    });
  }, []);

  return {
    messages,
    input,
    isLoading,
    isThinking, 
    currentUpload,
    isUploading,
    queryDetails,
    sessionId,
    
    actions: {
      setInput,
      handleSubmit,
      handleFileSelect,
      handleKeyDown,
      handleInputChange,
      handleReset,
      setCurrentUpload,
      terminateSession,
      stopAgent,
      takeControl,
    },
    
    fileInputRef,
  };
};