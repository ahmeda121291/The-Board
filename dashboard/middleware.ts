import { NextRequest, NextResponse } from "next/server";

// Simple HTTP Basic Auth gate for the dashboard.
//
// - If DASHBOARD_PASSWORD is NOT set, the site stays open (so you're never
//   locked out before configuring it).
// - Once you set DASHBOARD_PASSWORD in the Vercel project env, every page
//   requires it. Username can be anything; only the password is checked.
export function middleware(req: NextRequest) {
  // The daily keep-alive cron must reach the DB without the dashboard password
  // (it carries its own CRON_SECRET check). Exempt it from Basic Auth.
  if (req.nextUrl.pathname === "/api/keepalive") return NextResponse.next();

  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) return NextResponse.next();

  const header = req.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const pass = decoded.slice(decoded.indexOf(":") + 1);
      if (pass === password) return NextResponse.next();
    } catch {
      // fall through to 401
    }
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Boardroom", charset="UTF-8"' },
  });
}

export const config = {
  // Protect everything except Next internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
