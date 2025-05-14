export const CONFIG = {
  API: {
    // Base URL without trailing /api prefix
    BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000',
    TIMEOUT: 10000,
    MAX_RETRIES: 3
  },
  SESSION: {
    STORAGE_KEY: 'session_id'
  }
};