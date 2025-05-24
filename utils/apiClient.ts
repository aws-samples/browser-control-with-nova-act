import { CONFIG } from '../config';
import { createLogger } from './logger';

const logger = createLogger('ApiClient');

class ApiClient {
  private baseUrl: string;
  private defaultTimeout: number;
  private maxRetries: number;

  constructor() {
    this.baseUrl = CONFIG.API.BASE_URL;
    this.defaultTimeout = CONFIG.API.TIMEOUT;
    this.maxRetries = CONFIG.API.MAX_RETRIES;
    
    logger.info('API Client initialized', { 
      baseUrl: this.baseUrl, 
      timeout: this.defaultTimeout, 
      maxRetries: this.maxRetries 
    });
  }

  async request(path: string, options: RequestInit = {}, retries = this.maxRetries): Promise<Response> {
    const url = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort('Request timeout'), this.defaultTimeout);
      
      // Add default headers if not provided
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      };
      
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      if (retries > 0 && (error instanceof Error && error.name !== 'AbortError')) {
        logger.warn('Retrying request', { path, retriesLeft: retries, error: error.message });
        await new Promise(resolve => setTimeout(resolve, 1000));
        return this.request(path, options, retries - 1);
      }
      throw error;
    }
  }
}

export const apiClient = new ApiClient();