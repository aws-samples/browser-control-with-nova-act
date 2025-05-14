import { NextRequest } from "next/server";

// Configuration
const BACKEND_URL = "http://localhost:8000/api/router";
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000; // 1 second
const REQUEST_TIMEOUT = 10000; // 10 seconds

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
      console.log(`Retrying connection to backend (${retries} attempts left)...`);
      await sleep(RETRY_DELAY);
      return fetchWithRetry(url, options, retries - 1);
    }
    throw error;
  }
}

export async function POST(req: NextRequest) {
  try {
    console.log("Router API called directly");
    const body = await req.json();
    
    if (!body.messages || !Array.isArray(body.messages)) {
      return new Response(
        JSON.stringify({ error: "Messages array is required" }),
        { status: 400 }
      );
    }
    
    if (!body.model || !body.region) {
      return new Response(
        JSON.stringify({ error: "Model and region are required" }),
        { status: 400 }
      );
    }
    
    console.log("Router API forwarding request to backend:", body.messages.length, "messages");
    
    // Use the retry logic
    const response = await fetchWithRetry(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    
    if (!response.ok) {
      throw new Error(`Router backend API error! status: ${response.status}`);
    }
    
    const responseData = await response.json();
    
    return new Response(JSON.stringify(responseData), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error("Router API: Error in POST handler:", error);
    
    // Check if it's an abort error (timeout)
    if (error.name === 'AbortError') {
      return new Response(
        JSON.stringify({ error: "Request to backend timed out. Please try again." }),
        { status: 504 }
      );
    }
    
    // Handle ECONNREFUSED specifically
    if (error.code === 'ECONNREFUSED' || error.cause?.code === 'ECONNREFUSED') {
      return new Response(
        JSON.stringify({ 
          error: "Could not connect to backend server. Make sure the backend service is running.",
          details: "Connection refused"
        }),
        { status: 502 }
      );
    }
    
    return new Response(
      JSON.stringify({ 
        error: "An error occurred while processing the request",
        details: error.message
      }),
      { status: 500 }
    );
  }
}
