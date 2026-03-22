'use client'
import { useState, useEffect } from 'react'
import { useAppStore } from '@/lib/store'
import { configureNotifications, testNotification, configureAI } from '@/lib/api'
import { Bot, Bell, Save, TestTube, Eye, EyeOff, Check, ExternalLink, Info } from 'lucide-react'
import toast from 'react-hot-toast'

const AI_PROVIDERS = [
  {
    id: 'openai', label: 'OpenAI', color: '#10a37f',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    needsKey: true, keyHint: 'sk-...', keyLink: 'https://platform.openai.com/api-keys',
    description: 'Best overall quality. GPT-4o is recommended.',
  },
  {
    id: 'gemini', label: 'Google Gemini', color: '#4285F4',
    models: ['gemini-2.0-flash', 'gemini-2.5-pro-preview-03-25', 'gemini-1.5-flash-latest'],
    needsKey: true, keyHint: 'AIza...', keyLink: 'https://aistudio.google.com/app/apikey',
    description: 'Fast and capable. gemini-2.0-flash is the recommended default.',
  },
  {
    id: 'anthropic', label: 'Anthropic Claude', color: '#d97706',
    models: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
    needsKey: true, keyHint: 'sk-ant-...', keyLink: 'https://console.anthropic.com/settings/keys',
    description: 'Excellent reasoning and safety. Sonnet is the best balance.',
  },
  {
    id: 'ollama', label: 'Ollama (Local)', color: '#8b5cf6',
    models: ['llama3.2', 'llama3.1', 'llama3.1:70b', 'mistral', 'mixtral', 'codellama', 'phi3', 'deepseek-r1'],
    needsKey: false, needsUrl: true,
    description: 'Free, runs locally. No API key needed. Requires Ollama installed.',
  },
  {
    id: 'custom', label: 'Custom Endpoint', color: '#6b7280',
    models: [],
    needsKey: true, needsUrl: true,
    description: 'Any OpenAI-compatible API (LM Studio, vLLM, Together AI, etc.)',
  },
]

export default function SettingsPanel() {
  const { aiConfig, setAIConfig } = useAppStore()
  const [localAI,  setLocalAI]  = useState(() => ({ ...aiConfig }))
  const [showKey,  setShowKey]  = useState(false)
  const [savedAI,  setSavedAI]  = useState(false)
  const [savingAI, setSavingAI] = useState(false)

  const [notif, setNotif] = useState({
    discord_webhook_url: '', discord_bot_token: '', discord_channel_id: '',
    slack_webhook_url: '',   slack_bot_token: '',   slack_channel_id: '',
    smtp_host: '', smtp_port: 587, smtp_user: '', smtp_pass: '', notification_emails: '',
  })
  const [testingChannel, setTestingChannel] = useState<string | null>(null)
  const [savingNotif,    setSavingNotif]    = useState(false)

  const provider = AI_PROVIDERS.find(p => p.id === localAI.provider) || AI_PROVIDERS[0]

  const saveAIConfig = async () => {
    setSavingAI(true)
    setAIConfig(localAI)
    try {
      const clusterId = useAppStore.getState().activeClusterId || 'default'
      await configureAI(clusterId, {
        provider: localAI.provider,
        model:    localAI.model,
        api_key:  localAI.api_key,
        base_url: localAI.base_url,
      })
      setSavedAI(true)
      toast.success('AI configuration saved')
      setTimeout(() => setSavedAI(false), 2500)
    } catch (e: any) {
      toast.error(`Save failed: ${e.message}`)
    } finally {
      setSavingAI(false)
    }
  }

  const saveNotifications = async () => {
    setSavingNotif(true)
    try {
      await configureNotifications(notif)
      toast.success('Notification settings saved')
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setSavingNotif(false)
    }
  }

  const testChannel = async (channel: string) => {
    setTestingChannel(channel)
    try {
      await testNotification(channel)
      toast.success(`Test notification sent to ${channel}`)
    } catch (e: any) {
      toast.error(`${channel} test failed: ${e.message}`)
    } finally {
      setTestingChannel(null)
    }
  }

  const inp = (extra?: React.CSSProperties): React.CSSProperties => ({
    width: '100%', padding: '9px 12px', borderRadius: 8, fontSize: 13,
    background: 'var(--bg-app)', border: '1px solid var(--border-mid)',
    color: 'var(--text-primary)', outline: 'none', ...extra,
  })

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Settings</h1>
          <p className="eg-page-sub">Configure AI provider, API keys, and notification channels</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>

        {/* ── LEFT COLUMN: AI Provider ─────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          <div className="eg-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <Bot size={15} style={{ color: 'var(--accent)' }} />
              <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>AI Provider</h2>
            </div>

            {/* Provider grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 18 }}>
              {AI_PROVIDERS.map(p => {
                const active = localAI.provider === p.id
                return (
                  <button key={p.id} onClick={() => setLocalAI(c => ({
                    ...c, provider: p.id,
                    model: p.models[0] || c.model || '',
                    api_key: '',
                    base_url: '',
                  }))}
                    style={{
                      padding: '10px 14px', borderRadius: 10, cursor: 'pointer',
                      background: active ? `color-mix(in srgb, ${p.color} 12%, var(--bg-raised))` : 'var(--bg-raised)',
                      border: `1.5px solid ${active ? p.color : 'var(--border)'}`,
                      textAlign: 'left', transition: 'all .15s',
                    }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: active ? p.color : 'var(--text-primary)', marginBottom: 2 }}>
                      {p.label}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>
                      {p.description.split('.')[0]}
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Provider description */}
            <div style={{ padding: '10px 12px', borderRadius: 8, background: `color-mix(in srgb, ${provider.color} 8%, var(--bg-raised))`, border: `1px solid color-mix(in srgb, ${provider.color} 20%, transparent)`, marginBottom: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{provider.description}</p>
              {provider.id === 'ollama' && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                  <div>Start: <code style={{ color: 'var(--green)', fontSize: 11 }}>ollama serve</code></div>
                  <div style={{ marginTop: 4 }}>Pull model: <code style={{ color: 'var(--green)', fontSize: 11 }}>ollama pull llama3.2</code></div>
                </div>
              )}
            </div>

            {/* Model */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 500 }}>Model</label>
              {provider.models.length > 0 ? (
                <select value={localAI.model || provider.models[0]}
                  onChange={e => setLocalAI(c => ({ ...c, model: e.target.value }))}
                  style={inp()}>
                  {provider.models.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              ) : (
                <input type="text" value={localAI.model || ''}
                  onChange={e => setLocalAI(c => ({ ...c, model: e.target.value }))}
                  placeholder="e.g. llama3.2, mistral-7b"
                  style={inp()} />
              )}
            </div>

            {/* API Key */}
            {provider.needsKey && (
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 500 }}>
                  <span>API Key</span>
                  {provider.keyLink && (
                    <a href={provider.keyLink} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 3 }}>
                      Get key <ExternalLink size={10} />
                    </a>
                  )}
                </label>
                <div style={{ position: 'relative' }}>
                  <input type={showKey ? 'text' : 'password'}
                    value={localAI.api_key || ''}
                    onChange={e => setLocalAI(c => ({ ...c, api_key: e.target.value }))}
                    placeholder={provider.keyHint || 'Enter API key'}
                    style={{ ...inp(), paddingRight: 38, fontFamily: 'monospace' }} />
                  <button onClick={() => setShowKey(s => !s)}
                    style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            )}

            {/* Base URL */}
            {provider.needsUrl && (
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 500 }}>
                  Base URL {provider.id === 'ollama' ? '(default: http://localhost:11434)' : ''}
                </label>
                <input type="text"
                  value={localAI.base_url || ''}
                  onChange={e => setLocalAI(c => ({ ...c, base_url: e.target.value }))}
                  placeholder={provider.id === 'ollama' ? 'http://localhost:11434' : 'https://api.example.com/v1'}
                  style={{ ...inp(), fontFamily: 'monospace' }} />
              </div>
            )}

            <button onClick={saveAIConfig} disabled={savingAI}
              style={{
                width: '100%', padding: '10px 0', borderRadius: 8, border: 'none', cursor: savingAI ? 'not-allowed' : 'pointer',
                background: savedAI ? 'var(--green)' : 'var(--accent)',
                color: '#fff', fontWeight: 600, fontSize: 13,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                opacity: savingAI ? .7 : 1, transition: 'background .2s',
              }}>
              {savingAI ? <><div style={{ width: 13, height: 13, border: '2px solid rgba(255,255,255,.4)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />Saving…</>
                : savedAI ? <><Check size={14} />Saved!</>
                : <><Save size={14} />Save AI Configuration</>}
            </button>
          </div>

          {/* Current active config summary */}
          <div className="eg-card" style={{ padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
              <Info size={13} style={{ color: 'var(--text-muted)' }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Active Configuration</span>
            </div>
            {[
              { label: 'Provider', value: AI_PROVIDERS.find(p => p.id === aiConfig.provider)?.label || aiConfig.provider },
              { label: 'Model',    value: aiConfig.model || '(default)' },
              { label: 'API Key',  value: aiConfig.api_key ? '••••••••' + aiConfig.api_key.slice(-4) : 'Not set' },
              { label: 'Base URL', value: aiConfig.base_url || '(default)' },
            ].filter(r => r.label !== 'Base URL' || aiConfig.base_url).map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ fontSize: 12, color: 'var(--text-primary)', fontFamily: label === 'API Key' || label === 'Base URL' ? 'monospace' : 'inherit' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── RIGHT COLUMN: Notifications ──────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          <div className="eg-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Bell size={15} style={{ color: 'var(--yellow)' }} />
              <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Notifications &amp; Approvals</h2>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 18, lineHeight: 1.6 }}>
              When ElasticGuard detects critical issues it sends alerts here. You can approve or reject
              suggested fixes directly from these channels — or always use the Approvals tab in the UI.
            </p>

            {/* Discord */}
            <NotifSection title="Discord" color="#5865F2" hint="Server Settings → Integrations → Webhooks → New Webhook">
              <NField label="Webhook URL" value={notif.discord_webhook_url} onChange={v => setNotif(n => ({ ...n, discord_webhook_url: v }))} placeholder="https://discord.com/api/webhooks/..." />
              <NField label="Bot Token (optional — for interactive buttons)" value={notif.discord_bot_token} onChange={v => setNotif(n => ({ ...n, discord_bot_token: v }))} placeholder="Bot token" type="password" />
              <NField label="Channel ID (required for bot)" value={notif.discord_channel_id} onChange={v => setNotif(n => ({ ...n, discord_channel_id: v }))} placeholder="Channel snowflake ID" />
              <TestBtn channel="discord" testing={testingChannel === 'discord'} onTest={() => testChannel('discord')} />
            </NotifSection>

            {/* Slack */}
            <NotifSection title="Slack" color="#9c2e9e">
              <NField label="Webhook URL" value={notif.slack_webhook_url} onChange={v => setNotif(n => ({ ...n, slack_webhook_url: v }))} placeholder="https://hooks.slack.com/services/..." />
              <NField label="Bot Token (for interactive approval)" value={notif.slack_bot_token} onChange={v => setNotif(n => ({ ...n, slack_bot_token: v }))} placeholder="xoxb-your-slack-bot-token" type="password" />
              <NField label="Channel ID" value={notif.slack_channel_id} onChange={v => setNotif(n => ({ ...n, slack_channel_id: v }))} placeholder="C1234567890" />
              <TestBtn channel="slack" testing={testingChannel === 'slack'} onTest={() => testChannel('slack')} />
            </NotifSection>

            {/* Email */}
            <NotifSection title="Email (SMTP)" color="#EA4335">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px', gap: 10 }}>
                <NField label="SMTP Host" value={notif.smtp_host} onChange={v => setNotif(n => ({ ...n, smtp_host: v }))} placeholder="smtp.gmail.com" />
                <NField label="Port" value={String(notif.smtp_port)} onChange={v => setNotif(n => ({ ...n, smtp_port: Number(v) }))} placeholder="587" type="number" />
              </div>
              <NField label="Username" value={notif.smtp_user} onChange={v => setNotif(n => ({ ...n, smtp_user: v }))} placeholder="you@gmail.com" />
              <NField label="App Password" value={notif.smtp_pass} onChange={v => setNotif(n => ({ ...n, smtp_pass: v }))} placeholder="Gmail 16-char app password" type="password" />
              <NField label="Recipient Emails (comma-separated)" value={notif.notification_emails} onChange={v => setNotif(n => ({ ...n, notification_emails: v }))} placeholder="admin@company.com, ops@company.com" />
              <TestBtn channel="email" testing={testingChannel === 'email'} onTest={() => testChannel('email')} />
            </NotifSection>

            <button onClick={saveNotifications} disabled={savingNotif}
              style={{
                width: '100%', padding: '10px 0', borderRadius: 8,
                cursor: savingNotif ? 'not-allowed' : 'pointer',
                background: 'color-mix(in srgb, var(--yellow) 20%, var(--bg-raised))',
                border: '1px solid color-mix(in srgb, var(--yellow) 30%, transparent)',
                color: 'var(--yellow)', fontWeight: 600, fontSize: 13,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                opacity: savingNotif ? .7 : 1, marginTop: 4,
              } as any}>
              {savingNotif
                ? <><div style={{ width: 13, height: 13, border: '2px solid rgba(251,191,36,.4)', borderTopColor: 'var(--yellow)', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />Saving…</>
                : <><Save size={14} />Save Notification Settings</>}
            </button>
          </div>
        </div>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}

function NotifSection({ title, color, hint, children }: { title: string; color: string; hint?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginBottom: 10, border: `1px solid color-mix(in srgb, ${color} 25%, var(--border))`, borderRadius: 10, overflow: 'hidden' }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', background: `color-mix(in srgb, ${color} 8%, var(--bg-raised))`, border: 'none', cursor: 'pointer' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>{title}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{open ? '▲ collapse' : '▼ expand'}</span>
      </button>
      {open && (
        <div style={{ padding: '14px 14px 10px', background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {hint && <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>💡 {hint}</p>}
          {children}
        </div>
      )}
    </div>
  )
}

function NField({ label, value, onChange, placeholder, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; placeholder: string; type?: string
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 5, fontWeight: 500 }}>{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={{ width: '100%', padding: '8px 11px', borderRadius: 7, fontSize: 12, background: 'var(--bg-app)', border: '1px solid var(--border-mid)', color: 'var(--text-primary)', outline: 'none', fontFamily: type === 'password' ? 'monospace' : 'inherit' }} />
    </div>
  )
}

function TestBtn({ channel, testing, onTest }: { channel: string; testing: boolean; onTest: () => void }) {
  return (
    <button onClick={onTest} disabled={testing}
      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 7, fontSize: 12, cursor: testing ? 'not-allowed' : 'pointer', background: 'var(--bg-raised)', border: '1px solid var(--border)', color: testing ? 'var(--text-muted)' : 'var(--accent)' }}>
      {testing
        ? <><div style={{ width: 11, height: 11, border: '2px solid rgba(59,130,246,.3)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />Sending…</>
        : <><TestTube size={12} />Test {channel}</>
      }
    </button>
  )
}
