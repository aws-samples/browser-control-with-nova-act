import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

// POST /api/mcp-servers/test
export async function POST(request: NextRequest) {
  try {
    const { hostname } = await request.json();
    
    if (!hostname) {
      return new Response(JSON.stringify({ success: false, error: 'Hostname is required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    
    // Try to connect to the server with a timeout
    try {
      // We need to ensure the URL is properly formatted
      let url = hostname;
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = `http://${url}`;
      }
      
      // Add a health check endpoint path if needed
      if (!url.includes('/health') && !url.endsWith('/')) {
        url = `${url}/health`;
      } else if (url.endsWith('/')) {
        url = `${url}health`;
      }
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout
      
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      // Check if the response is ok (status in the range 200-299)
      const success = response.ok;
      
      return new Response(JSON.stringify({ success }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (error) {
      console.error('Error testing server connection:', error);
      return new Response(JSON.stringify({ success: false, error: 'Failed to connect to server' }), {
        status: 200, // We return 200 but with success: false to indicate the test failed
        headers: { 'Content-Type': 'application/json' },
      });
    }
  } catch (error) {
    return new Response(JSON.stringify({ success: false, error: 'Invalid request' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}