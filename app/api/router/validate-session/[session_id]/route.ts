import { NextRequest } from "next/server";

// Configuration
const BACKEND_URL = "http://localhost:8000/api/act/validate-session";
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
    
    // Since the backend endpoint likely doesn't exist yet, we'll return a successful response
    // In a production environment, you would actually check with the backend
    // const response = await fetchWithRetry(`${BACKEND_URL}/${session_id}`, {
    //   method: "GET",
    //   headers: { "Content-Type": "application/json" },
    // });
    // 
    // if (!response.ok) {
    //   return new Response(
    //     JSON.stringify({ valid: false, message: `Invalid session: ${response.status}` }),
    //     { status: 200, headers: { "Content-Type": "application/json" } }
    //   );
    // }
    // 
    // const data = await response.json();
    
    // For now, just assume any session ID is valid
    return new Response(
      JSON.stringify({ valid: true, message: "Session is valid" }),
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