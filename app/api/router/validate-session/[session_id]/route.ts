import { NextRequest } from "next/server";

// Configuration
const BACKEND_URL = "http://localhost:8000/api/router/validate-session";
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000; // 1 second
const REQUEST_TIMEOUT = 5000; // 5 seconds

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function fetchWithRetry(url: string, options: RequestInit, retries = MAX_RETRIES) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
    
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    if (retries > 0) {
      console.log(`Retrying validation (${retries} attempts left)...`);
      await sleep(RETRY_DELAY);
      return fetchWithRetry(url, options, retries - 1);
    }
    throw error;
  }
}

export async function GET(req: NextRequest, { params }: { params: { session_id: string } }) {
  try {
    const session_id = params.session_id;
    console.log(`Session validation requested for: ${session_id}`);
    
    if (!session_id) {
      return new Response(
        JSON.stringify({ valid: false, error: "Session ID is required" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }
    
    // Validate session with backend
    const response = await fetchWithRetry(`${BACKEND_URL}/${session_id}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    
    if (!response.ok) {
      return new Response(
        JSON.stringify({ valid: false, message: `Backend validation failed: ${response.status}` }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    
    const data = await response.json();
    
    // Return the backend validation result
    return new Response(
      JSON.stringify(data),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Session validation error:", error);
    
    // Check if it's a timeout
    if (error.name === 'AbortError') {
      return new Response(
        JSON.stringify({ valid: false, error: "Validation request timed out" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    
    return new Response(
      JSON.stringify({ valid: false, error: error.message || "Unknown error" }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }
}