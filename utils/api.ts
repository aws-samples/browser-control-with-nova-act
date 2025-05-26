import { createLogger } from './logger';

const logger = createLogger('API');

export const API_BASE_URL = 'http://localhost:8000/api';

export async function apiRequest(path: string, options = {}) {
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  const response = await fetch(url, options);
  return response;
}