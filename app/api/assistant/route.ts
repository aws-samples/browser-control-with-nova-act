import { NextRequest, NextResponse } from "next/server";
import { redirect } from "next/navigation";

// This route is deprecated in favor of /api/router
export async function POST(req: NextRequest) {
  // Redirect to the /api/router endpoint
  const { protocol, host } = new URL(req.url);
  const routerUrl = `${protocol}//${host}/api/router`;
  
  console.log(`Assistant API is deprecated. Redirecting request to ${routerUrl}`);
  
  return NextResponse.redirect(routerUrl, { status: 308 }); // 308 is Permanent Redirect
}