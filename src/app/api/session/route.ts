import { NextResponse } from 'next/server';

// Issues the backend's signed tenant token without the enrollment key ever reaching the browser.
// There is no sign-in yet, so whoever can call this route acts as the one configured tenant. It therefore
// fails closed: it answers only under `next dev`, or when CASHPILOT_OPEN_SESSION=1 marks a single-business
// deployment kept behind its own access control. Both are server-side settings; Host and Origin are
// client-supplied and never decide this. Replace with a real sign-in before serving several businesses.

export async function POST(req: Request) {
  const host = req.headers.get('host') ?? '';
  const origin = req.headers.get('origin');
  const isLoopback = host.startsWith('localhost:') || host.startsWith('127.0.0.1:') || host === 'localhost' || host === '127.0.0.1';
  if (process.env.NODE_ENV !== 'development' && process.env.CASHPILOT_OPEN_SESSION !== '1' && !isLoopback) return NextResponse.json({ error: 'SIGN_IN_REQUIRED' }, { status: 401 });
  // CSRF defence only: another site cannot mint a token through a visitor's browser.
  if (!origin || new URL(origin).host !== host) return NextResponse.json({ error: 'FORBIDDEN' }, { status: 403 });

  const api = (process.env.CASHPILOT_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
  const tenant = process.env.TENANT_ENROLLMENT_TENANT_ID;
  const key = process.env.TENANT_ENROLLMENT_KEY;
  if (!tenant || !key) return NextResponse.json({ error: 'NOT_CONFIGURED' }, { status: 503 });

  try {
    const res = await fetch(`${api}/api/v1/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Enrollment-Key': key },
      body: JSON.stringify({ tenant_id: tenant, ttl_seconds: 3600 }),
      cache: 'no-store',
    });
    if (!res.ok) return NextResponse.json({ error: 'ISSUANCE_FAILED' }, { status: 502 });
    const { access_token } = (await res.json()) as { access_token: string };
    return NextResponse.json({ token: access_token }, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json({ error: 'UNREACHABLE' }, { status: 502 });
  }
}
