import { CONFIG } from '../config';

class ApiClient {
  private baseUrl: string;
  private defaultTimeout: number;
  private maxRetries: number;

  constructor() {
    this.baseUrl = CONFIG.API.BASE_URL;
    this.defaultTimeout = CONFIG.API.TIMEOUT;
    this.maxRetries = CONFIG.API.MAX_RETRIES;
  }

  async request(path: string, options: RequestInit = {}, retries = this.maxRetries): Promise<Response> {
    const url = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort('Request timeout'), this.defaultTimeout);
      
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      if (retries > 0 && (error instanceof Error && error.name !== 'AbortError')) {
        console.log(`Retrying request to ${path} (${retries} attempts left)...`);
        await new Promise(resolve => setTimeout(resolve, 1000));
        return this.request(path, options, retries - 1);
      }
      throw error;
    }
  }
}

export const apiClient = new ApiClient();