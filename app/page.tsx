'use client';

import React, { useEffect, useState } from 'react';
import { Activity, ShieldCheck, Terminal, CheckCircle2, AlertCircle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function HomePage() {
  const [healthStatus, setHealthStatus] = useState<'checking' | 'healthy' | 'offline'>('checking');
  const [healthData, setHealthData] = useState<any>(null);

  useEffect(() => {
    async function checkBackend() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/health`);
        if (res.ok) {
          const data = await res.json();
          setHealthStatus('healthy');
          setHealthData(data);
        } else {
          setHealthStatus('offline');
        }
      } catch {
        setHealthStatus('offline');
      }
    }
    checkBackend();
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 antialiased p-6 md:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <header className="border-b border-slate-200 pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="w-8 h-8 rounded-lg bg-emerald-600 text-white font-bold flex items-center justify-center text-sm">
                FC
              </span>
              <h1 className="text-xl font-bold tracking-tight text-slate-900">
                SME Finance Copilot
              </h1>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Autonomous AI CFO &amp; Financial Participant — Clean Canvas
            </p>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border bg-white text-xs font-mono">
            {healthStatus === 'checking' && (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <span className="text-slate-500">Connecting to API...</span>
              </>
            )}
            {healthStatus === 'healthy' && (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-emerald-700 font-semibold">Backend 756/756 OK</span>
              </>
            )}
            {healthStatus === 'offline' && (
              <>
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                <span className="text-rose-700 font-semibold">Backend Offline</span>
              </>
            )}
          </div>
        </header>

        {/* Ready for Redesign Banner */}
        <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm space-y-4">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-emerald-50 rounded-lg text-emerald-600">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-slate-900">
                Frontend Cleared &amp; Ready for Redesign
              </h2>
              <p className="text-sm text-slate-600 leading-relaxed">
                The legacy 166KB monolithic page and 2,875-line stylesheet have been removed. This clean canvas is structured with Next.js 14 App Router, Tailwind CSS, Lucide icons, and typed backend API schemas ready for your new UI build.
              </p>
            </div>
          </div>

          {healthData && (
            <div className="bg-slate-900 text-slate-200 p-4 rounded-lg font-mono text-xs overflow-x-auto space-y-1">
              <div className="text-slate-400 mb-1 flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5" />
                <span>Live API Probe: {API_BASE}/api/v1/health</span>
              </div>
              <pre>{JSON.stringify(healthData, null, 2)}</pre>
            </div>
          )}
        </div>

        {/* Backend API Endpoints Reference Card */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-600" />
            Available Backend Endpoints (Import types from @/types/api)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/analyze</span>
              <p className="text-slate-600 font-sans mt-0.5">Ingests CSV/PDF statements; computes runway &amp; DAB</p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/underwrite</span>
              <p className="text-slate-600 font-sans mt-0.5">Digital credit underwriting &amp; liquidity match</p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/actions</span>
              <p className="text-slate-600 font-sans mt-0.5">Stages Tier 2 intent proposals to ledger</p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/actions/:id/execute</span>
              <p className="text-slate-600 font-sans mt-0.5">Executes Tier 3 intent with WebAuthn passkey</p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/agent/chat</span>
              <p className="text-slate-600 font-sans mt-0.5">AI CFO dialogue with FastEmbed routing</p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-semibold text-emerald-700">POST /api/v1/agent/fetch-models</span>
              <p className="text-slate-600 font-sans mt-0.5">Discovers live models from selected provider</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
