import { NextRequest } from "next/server";
export const dynamic = 'force-dynamic'; 
export const fetchCache = 'force-no-store';

async function connectWithRetry(backendUrl: string, maxAttempts = 5) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);
      
      const response = await fetch(backendUrl, {
        cache: "no-store",
        headers: { "Accept": "text/event-stream" },
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) return response;
      
      console.log(`Connection attempt ${attempt + 1}/${maxAttempts} failed with status: ${response.status} ${response.statusText}`);
      
    } catch (error) {
      console.log(`Connection attempt ${attempt + 1}/${maxAttempts} failed with error:`, error);
    }
    
    if (attempt < maxAttempts - 1) {
      await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempt)));
    }
  }
  throw new Error('Failed to connect after maximum attempts');
}

export async function GET(
  req: NextRequest,
  { params }: { params: { session_id: string } }
) {
  const param = await params;
  const session_id = await param.session_id;

  if (!session_id) {
    return new Response(JSON.stringify({ error: "Session ID is required" }), {
      status: 400,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  console.log(`Setting up SSE thought stream for session: ${session_id}`);

  try {
    const headers = new Headers({
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-store, must-revalidate",
      "Connection": "keep-alive",
      "Transfer-Encoding": "chunked",
      "X-Accel-Buffering": "no",
      "Access-Control-Allow-Origin": "*",
      "Content-Encoding": "identity"
    });

    const encoder = new TextEncoder();
    let isStreamActive = true;

    const stream = new ReadableStream({
      async start(controller) {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({
            type: "connected", 
            message: "SSE stream initialized"
          })}\n\n`));
        } catch (err) {
          console.log(`Failed to send initial message: ${err.message}`);
          isStreamActive = false;
          return;
        }

        try {
          const apiBaseUrl = process.env.API_BASE_URL || 'http://127.0.0.1:8000';
          const backendUrl = `${apiBaseUrl}/api/assistant/thoughts/${session_id}`;
          console.log(`Attempting backend connection: ${backendUrl}`);
          
          const response = await connectWithRetry(backendUrl);
          const reader = response.body?.getReader();
          
          if (!reader) {
            throw new Error("No response stream available");
          }

          let decoder = new TextDecoder();
          let buffer = "";

          while (isStreamActive) {
            const { done, value } = await reader.read();
            
            if (done) {
              if (buffer.length > 0 && isStreamActive) {
                try {
                  controller.enqueue(encoder.encode(buffer));
                } catch (err) {
                  if (err.code === 'ERR_INVALID_STATE') {
                    console.log(`Stream already closed for session ${session_id}`);
                    isStreamActive = false;
                  } else {
                    throw err;
                  }
                }
              }
              break;
            }
            
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            const messages = buffer.split('\n\n');
            buffer = messages.pop() || "";
            
            if (messages.length > 0 && isStreamActive) {
              const completeMessages = messages.join('\n\n') + '\n\n';
              try {
                controller.enqueue(encoder.encode(completeMessages));
              } catch (err) {
                if (err.code === 'ERR_INVALID_STATE') {
                  console.log(`Stream already closed for session ${session_id}`);
                  isStreamActive = false;
                  break;
                } else {
                  throw err;
                }
              }
            }
          }
        } catch (error) {
          console.error(`Error in SSE stream for session ${session_id}:`, error);
          if (isStreamActive) {
            try {
              const errorMessage = error instanceof Error ? error.message : "Unknown error";
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({type: "error", message: errorMessage})}\n\n`));
            } catch (err) {
              if (err.code !== 'ERR_INVALID_STATE') {
                console.error(`Failed to send error message: ${err.message}`);
              }
            }
          }
        } finally {

          isStreamActive = false;
        }
      },
      cancel() {
        console.log(`SSE stream canceled for session: ${session_id}`);
        isStreamActive = false
      }
    });

    return new Response(stream, { headers });
  } catch (error) {
    console.error(`Error setting up SSE stream: ${error}`);
    return new Response(
      JSON.stringify({ error: "Failed to set up thought stream" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
