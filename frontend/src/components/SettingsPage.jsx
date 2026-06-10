import { useEffect, useState } from 'react'
import { api } from '../api'

export default function SettingsPage() {
  const [data, setData] = useState(null)
  const [ui, setUi] = useState({})
  const [accounts, setAccounts] = useState([])
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const refresh = async () => {
    const d = await api.settings()
    setData(d)
    setUi(d.ui)
    api.tiktokAccounts().then(setAccounts).catch(() => {})
  }
  useEffect(() => { refresh().catch((e) => setError(e.message)) }, [])

  async function save() {
    setSaved(false); setError('')
    try {
      await api.saveSettings(ui)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message)
    }
  }

  async function connectTiktok() {
    setError('')
    try {
      const { url } = await api.tiktokAuthUrl()
      window.open(url, '_blank')
    } catch (e) {
      setError(e.message)
    }
  }

  if (!data) return <p className="text-gray-500 text-sm">{error || 'Loading...'}</p>

  const set = (k, v) => setUi((prev) => ({ ...prev, [k]: v }))

  return (
    <div className="grid lg:grid-cols-2 gap-6 max-w-5xl">
      <div className="card space-y-3">
        <h2 className="font-semibold">Caption style</h2>
        <div>
          <label className="label">Font</label>
          <input className="input" value={ui.caption_font || ''} onChange={(e) => set('caption_font', e.target.value)} />
        </div>
        <div className="flex gap-4">
          <div>
            <label className="label">Font size</label>
            <input className="input !w-24" type="number" value={ui.caption_font_size || 72}
              onChange={(e) => set('caption_font_size', Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Text color</label>
            <input className="!h-9 !w-16 input !p-1" type="color" value={ui.caption_color || '#FFFFFF'}
              onChange={(e) => set('caption_color', e.target.value)} />
          </div>
          <div>
            <label className="label">Highlight</label>
            <input className="!h-9 !w-16 input !p-1" type="color" value={ui.caption_highlight_color || '#FFE600'}
              onChange={(e) => set('caption_highlight_color', e.target.value)} />
          </div>
          <div>
            <label className="label">Outline</label>
            <input className="!h-9 !w-16 input !p-1" type="color" value={ui.caption_outline_color || '#000000'}
              onChange={(e) => set('caption_outline_color', e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">Default hashtags (comma-separated)</label>
          <input className="input" value={(ui.default_hashtags || []).join(', ')}
            onChange={(e) => set('default_hashtags', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!ui.blur_background_default}
            onChange={(e) => set('blur_background_default', e.target.checked)} />
          Blurred background by default
        </label>
        <button className="btn-primary" onClick={save}>Save settings</button>
        {saved && <span className="text-sm text-emerald-400 ml-2">Saved ✓</span>}
      </div>

      <div className="space-y-6">
        <div className="card space-y-3">
          <h2 className="font-semibold">TikTok accounts</h2>
          {!data.env.tiktok_configured && (
            <p className="text-sm text-amber-300">
              TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET are not set in .env — register an
              app at developers.tiktok.com first (see README). Until then, use Export.
            </p>
          )}
          {accounts.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-ink border border-edge rounded-lg px-3 py-2 text-sm">
              <div>
                <div>{a.display_name || a.open_id}</div>
                <div className={`text-xs ${
                  a.status === 'connected' ? 'text-emerald-400'
                  : a.status === 'unaudited' ? 'text-amber-300'
                  : 'text-red-400'
                }`}>
                  {a.status === 'unaudited'
                    ? 'Connected — app unaudited: posts will be private/draft until TikTok approves your app'
                    : a.status === 'needs_reauth' ? 'Token expired — reconnect' : 'Connected — public posting available'}
                </div>
              </div>
              <button className="btn-danger" onClick={async () => { await api.disconnectTiktok(a.id); refresh() }}>
                Disconnect
              </button>
            </div>
          ))}
          <button className="btn-ghost" onClick={connectTiktok} disabled={!data.env.tiktok_configured}>
            Connect TikTok account
          </button>
        </div>

        <div className="card space-y-2 text-sm">
          <h2 className="font-semibold">Environment</h2>
          <div className="flex justify-between"><span className="text-gray-400">Anthropic API key</span>
            <span className={data.env.anthropic_key_set ? 'text-emerald-400' : 'text-red-400'}>
              {data.env.anthropic_key_set ? 'set ✓' : 'missing — set ANTHROPIC_API_KEY in .env'}
            </span>
          </div>
          <div className="flex justify-between"><span className="text-gray-400">Claude model</span><span>{data.env.anthropic_model}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Whisper model</span><span>{data.env.whisper_model}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Output folder</span><span className="truncate max-w-60" title={data.env.data_dir}>{data.env.data_dir}</span></div>
          <p className="text-xs text-gray-500 pt-1">
            API keys and folders are configured in <code>backend/.env</code> — never stored in the browser.
          </p>
        </div>
        {error && <div className="text-sm text-red-400">{error}</div>}
      </div>
    </div>
  )
}
