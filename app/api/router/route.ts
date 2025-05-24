import { NextRequest } from "next/server";
import { apiClient } from "@/utils/apiClient";

// Route path to the backend router API
const ROUTER_API_PATH = "/api/router";


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
    
    // Use the API client for consistent error handling and retries
    const response = await apiClient.request(ROUTER_API_PATH, {
      method: "POST",
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
    
    // Handle different error types
    const errorName = error.name;
    const errorMessage = error.message;
    
    // Check if it's an abort error (timeout)
    if (errorName === 'AbortError') {
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
        details: errorMessage || "Unknown error"
      }),
      { status: 500 }
    );
  }
}
