'use client'
import { useState, useRef, useEffect } from 'react'
import { chatWithAgent } from '@/lib/api'
import { useAppStore } from '@/lib/store'
import { Send, Bot, User, Trash2 } from 'lucide-react'

interface Msg { role: 'user' | 'assistant'; text: string; ts: string }

export default function AIChat({ clusterId }: { clusterId: string }) {
  const { aiConfig } = useAppStore()
  const [msgs,  setMsgs]  = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy,  setBusy]  = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  const send = async () => {
    const text = input.trim(); if (!text || busy) return
    setInput('')
    const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setMsgs(p => [...p, { role: 'user', text, ts }])
    setBusy(true)
    try {
      const r = await chatWithAgent({ cluster_id: clusterId, message: text, provider: aiConfig.provider, model: aiConfig.model })
      setMsgs(p => [...p, { role: 'assistant', text: r.response, ts: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }])
    } catch (e: any) {
      setMsgs(p => [...p, { role: 'assistant', text: `Error: ${e.message}`, ts: '' }])
    } finally { setBusy(false) }
  }

  const suggestions = [
    'What are the most critical issues right now?',
    'How do I fix unassigned shards?',
    'What is causing high JVM heap usage?',
    'Explain the disk watermark settings',
    'How should I set up ILM for my log indices?',
  ]

  return (
    <div className="eg-page" style={{ height: 'calc(100vh - 100px)', minHeight: 0 }}>
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">AI Chat</h1>
          <p className="eg-page-sub">Ask anything about your cluster · powered by {aiConfig.provider}</p>
        </div>
        {msgs.length > 0 && (
          <button className="eg-btn eg-btn-ghost" onClick={() => setMsgs([])} style={{ fontSize: 12 }}>
            <Trash2 size={12} />Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="eg-card" style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 14, minHeight: 300 }}>
        {msgs.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: 16, padding: 32 }}>
            <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--accent-soft)', border: '1px solid rgba(59,130,246,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={22} style={{ color: 'var(--accent)' }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Ask about your cluster</p>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>I have full context of your cluster health, issues and metrics.</p>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 480 }}>
              {suggestions.map(s => (
                <button key={s} onClick={() => setInput(s)} className="eg-btn eg-btn-ghost" style={{ fontSize: 12, padding: '5px 12px', borderRadius: 99 }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexDirection: m.role === 'user' ? 'row-reverse' : 'row' }}>
            <div style={{ width: 28, height: 28, borderRadius: 99, background: m.role === 'user' ? 'var(--accent-soft)' : 'var(--bg-raised)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              {m.role === 'user' ? <User size={13} style={{ color: 'var(--accent)' }} /> : <Bot size={13} style={{ color: 'var(--green)' }} />}
            </div>
            <div style={{ maxWidth: '78%' }}>
              <div style={{ padding: '10px 14px', borderRadius: m.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px', background: m.role === 'user' ? 'var(--accent-soft)' : 'var(--bg-raised)', border: '1px solid var(--border)', fontSize: 13, lineHeight: 1.65, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {m.text}
              </div>
              {m.ts && <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3, textAlign: m.role === 'user' ? 'right' : 'left' }}>{m.ts}</p>}
            </div>
          </div>
        ))}
        {busy && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{ width: 28, height: 28, borderRadius: 99, background: 'var(--bg-raised)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={13} style={{ color: 'var(--green)' }} />
            </div>
            <div style={{ padding: '10px 14px', borderRadius: '12px 12px 12px 4px', background: 'var(--bg-raised)', border: '1px solid var(--border)', display: 'flex', gap: 6, alignItems: 'center' }}>
              {[0,1,2].map(d => <div key={d} style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: `pulse 1.2s ease-in-out ${d*.2}s infinite` }} />)}
            </div>
          </div>
        )}
        <div ref={bottom} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input className="eg-input" style={{ flex: 1 }} value={input}
          onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask about your Elasticsearch cluster…" disabled={busy} />
        <button className="eg-btn eg-btn-primary" onClick={send} disabled={busy || !input.trim()} style={{ padding: '9px 16px' }}>
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}
