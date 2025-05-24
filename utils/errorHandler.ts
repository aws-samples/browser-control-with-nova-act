/**
 * Frontend error handling utilities to work with standardized backend error responses
 */

import { createLogger } from './logger';

const logger = createLogger('ErrorHandler');

export interface StandardErrorResponse {
  success: boolean;
  error_code: string;
  message: string;
  details?: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  session_id?: string;
  timestamp: string;
  retry_after?: number;
}

export interface ErrorDisplayOptions {
  showDetails?: boolean;
  showRetry?: boolean;
  showSupport?: boolean;
}

export class ErrorHandler {
  /**
   * Extract error information from various response types
   */
  static extractError(error: any): StandardErrorResponse | null {
    // Handle HTTP error responses
    if (error.response?.data) {
      return this.parseErrorResponse(error.response.data);
    }
    
    // Handle direct error objects
    if (error.detail) {
      return this.parseErrorResponse(error.detail);
    }
    
    // Handle standard Error objects
    if (error instanceof Error) {
      return this.createFallbackError(error.message);
    }
    
    // Handle string errors
    if (typeof error === 'string') {
      return this.createFallbackError(error);
    }
    
    return this.createFallbackError('An unknown error occurred');
  }
  
  /**
   * Parse standardized error response from backend
   */
  static parseErrorResponse(response: any): StandardErrorResponse {
    if (this.isStandardErrorResponse(response)) {
      return response as StandardErrorResponse;
    }
    
    // Handle legacy error formats
    if (response.error || response.message) {
      return this.createFallbackError(response.error || response.message);
    }
    
    return this.createFallbackError('Unknown error format');
  }
  
  /**
   * Check if response matches our standard error format
   */
  static isStandardErrorResponse(response: any): boolean {
    return (
      response &&
      typeof response === 'object' &&
      'success' in response &&
      'error_code' in response &&
      'message' in response &&
      'severity' in response
    );
  }
  
  /**
   * Create fallback error for non-standard error formats
   */
  static createFallbackError(message: string): StandardErrorResponse {
    return {
      success: false,
      error_code: 'UNKNOWN_ERROR',
      message: message || 'An unexpected error occurred',
      severity: 'medium',
      timestamp: new Date().toISOString()
    };
  }
  
  /**
   * Get user-friendly error message with appropriate formatting
   */
  static getDisplayMessage(error: StandardErrorResponse, options: ErrorDisplayOptions = {}): string {
    let message = error.message;
    
    // Add details if requested and available
    if (options.showDetails && error.details) {
      message += `\n\nDetails: ${error.details}`;
    }
    
    // Add retry information if available
    if (options.showRetry && error.retry_after) {
      message += `\n\nPlease try again in ${error.retry_after} seconds.`;
    }
    
    // Add support information for critical errors
    if (options.showSupport && error.severity === 'critical') {
      message += '\n\nIf this problem persists, please contact support.';
    }
    
    return message;
  }
  
  /**
   * Determine if error should be retryable based on error code
   */
  static isRetryable(error: StandardErrorResponse): boolean {
    const retryableErrors = [
      'AGENT_TIMEOUT_ERROR',
      'SERVER_CONNECTION_ERROR',
      'SERVICE_UNAVAILABLE',
      'BROWSER_CONNECTION_ERROR'
    ];
    
    return retryableErrors.includes(error.error_code);
  }
  
  /**
   * Get appropriate toast variant based on error severity
   */
  static getToastVariant(error: StandardErrorResponse): 'default' | 'destructive' {
    return error.severity === 'high' || error.severity === 'critical' ? 'destructive' : 'default';
  }
  
  /**
   * Log error to console with appropriate level
   */
  static logError(error: StandardErrorResponse, context?: string): void {
    const logContext = {
      error_code: error.error_code,
      severity: error.severity,
      session_id: error.session_id,
      timestamp: error.timestamp,
      context
    };
    
    switch (error.severity) {
      case 'critical':
        logger.error(error.message, logContext, new Error(error.details || error.message));
        break;
      case 'high':
        logger.error(error.message, logContext);
        break;
      case 'medium':
        logger.warn(error.message, logContext);
        break;
      case 'low':
        logger.info(error.message, logContext);
        break;
    }
  }
  
  /**
   * Handle error with consistent logging and user notification
   */
  static handleError(
    error: any, 
    context: string,
    options: ErrorDisplayOptions & { 
      showToast?: boolean;
      toast?: (args: any) => void;
    } = {}
  ): StandardErrorResponse {
    const standardError = this.extractError(error);
    
    if (!standardError) {
      const fallbackError = this.createFallbackError('Failed to process error');
      this.logError(fallbackError, context);
      return fallbackError;
    }
    
    // Log the error
    this.logError(standardError, context);
    
    // Show toast notification if requested
    if (options.showToast && options.toast) {
      options.toast({
        title: "Error",
        description: this.getDisplayMessage(standardError, options),
        variant: this.getToastVariant(standardError),
      });
    }
    
    return standardError;
  }
}

// Export convenience functions
export const extractError = ErrorHandler.extractError.bind(ErrorHandler);
export const handleError = ErrorHandler.handleError.bind(ErrorHandler);
export const isRetryable = ErrorHandler.isRetryable.bind(ErrorHandler);