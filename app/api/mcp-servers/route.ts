import path from 'path';
import { promises as fs } from 'fs';
import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

// Path to our JSON file
const dataFilePath = path.join(process.cwd(), 'app/api/mcp-servers/mcp-servers.json');

async function readServersData() {
  try {
    const data = await fs.readFile(dataFilePath, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error reading MCP servers file:', error);
    return [];
  }
}

async function writeServersData(data: any) {
  try {
    await fs.writeFile(dataFilePath, JSON.stringify(data, null, 2), 'utf8');
    return true;
  } catch (error) {
    console.error('Error writing MCP servers file:', error);
    return false;
  }
}

// GET /api/mcp-servers
export async function GET() {
  try {
    const data = await readServersData();
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: 'Failed to fetch MCP servers' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// POST /api/mcp-servers
export async function POST(request: NextRequest) {
  try {
    const data = await request.json();
    const success = await writeServersData(data);
    
    if (success) {
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    } else {
      throw new Error('Failed to save servers');
    }
  } catch (error) {
    return new Response(JSON.stringify({ error: 'Failed to save MCP servers' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}