import { useState } from 'react'
import { api } from '../api'

function ScoreBadge({ score }) {
  const color = score >= 75 ? 'bg-emerald-500/20 text-emerald-300'
    : score >= 55 ? 'bg-amber-500/20 text-amber-300'
    : 'bg-gray-500/20 text-gray-300'
  return <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${color}`}>{score}</span>
}

export default function ClipCard({ clip, accounts, onChanged }) {
  const [hook, setHook] = useState(clip.hook)
  const [captionIdx, setCaptionIdx] = useState(0)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState(null) // {type: 'ok'|'warn'|'err', text}
  const [pendingPost, setPendingPost] = useState(null) // warnings awaiting confirm

  const dirtyHook = hook !== clip.hook
  const caption = clip.captions[captionIdx] || ''

  async function run(label, fn) {
    setBusy(label); setMsg(null)
    try {
      await fn()
      onChanged?.()
    } catch (e) {
      setMsg({ type: 'err', text: e.message })
    } finally {
      setBusy('')
    }
  }

  const saveHookAndRerender = () => run('hook', async () => {
    await api.patchClip(clip.id, { hook })
    await api.rerender(clip.id, true) // text-only: fast
    setMsg({ type: 'ok', text: 'Hook saved — re-rendering text layer...' })
  })

  const doExport = () => run('export', async () => {
    const res = await api.exportClip(clip.id, captionIdx)
    await navigator.clipboard.writeText(res.caption)
    window.open(res.download_url, '_blank')
    const warn = res.warnings.length ? ` Warnings: ${res.warnings.join('; ')}` : ''
    setMsg({ type: res.warnings.length ? 'warn' : 'ok', text: `Caption copied to clipboard, download started.${warn}` })
  })

  const doPost = (ignoreWarnings = false) => run('post', async () => {
    const res = await api.postClip(clip.id, {
      platform: 'tiktok',
      caption,
      account_id: accounts[0]?.id ?? null,
      ignore_warnings: ignoreWarnings,
    })
    if (res.blocked) {
      setPendingPost({ warnings: res.warnings, duplicates: res.duplicates })
      return
    }
    setPendingPost(null)
    setMsg({ type: 'ok', text: res.note || `Posted (${res.status})` })
  })

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <ScoreBadge score={clip.virality_score} />
          <span className="text-xs text-gray-400">
            {Math.floor(clip.start / 60)}:{String(Math.floor(clip.start % 60)).padStart(2, '0')} → {Math.floor(clip.end / 60)}:{String(Math.floor(clip.end % 60)).padStart(2, '0')} ({clip.duration}s)
          </span>
        </div>
        <span className={`text-xs ${
          clip.status === 'ready' ? 'text-emerald-400'
          : clip.status === 'failed' ? 'text-red-400'
          : clip.status === 'posted' ? 'text-cyan-300'
          : 'text-amber-300'
        }`}>{clip.status}</span>
      </div>

      {clip.has_file && clip.status !== 'rendering' ? (
        <video controls preload="metadata" className="w-full rounded-xl bg-black aspect-[9/16] max-h-96 object-contain"
               src={`/api/clips/${clip.id}/file`} />
      ) : (
        <div className="w-full rounded-xl bg-black/40 aspect-[9/16] max-h-96 flex items-center justify-center text-sm text-gray-500">
          {clip.status === 'failed' ? (clip.error || 'Render failed') : 'Rendering...'}
        </div>
      )}

      <p className="text-xs text-gray-400 italic">“{clip.reason}”</p>

      {clip.duplicates.length > 0 && (
        <div className="text-xs text-amber-400 bg-amber-900/20 rounded-lg p-2">
          ⚠️ You already posted an overlapping segment of this video
          ({clip.duplicates.map((d) => `clip #${d.clip_id} ${d.overlap_pct}%`).join(', ')}).
        </div>
      )}

      <div>
        <label className="label">Hook headline (inline-editable)</label>
        <div className="flex gap-2">
          <input className="input" value={hook} onChange={(e) => setHook(e.target.value)} />
          <button className="btn-primary whitespace-nowrap" disabled={!dirtyHook || !!busy} onClick={saveHookAndRerender}>
            {busy === 'hook' ? '...' : 'Apply'}
          </button>
        </div>
        {clip.hook_variants.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {clip.hook_variants.map((v, i) => (
              <button key={i} onClick={() => setHook(v)}
                className="text-xs px-2 py-1 rounded-lg bg-edge hover:bg-gray-700 text-left">
                {v}
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <label className="label">Caption ({captionIdx + 1}/{clip.captions.length || 1})</label>
        <textarea className="input h-20 text-xs" readOnly value={caption} />
        {clip.captions.length > 1 && (
          <div className="flex gap-1 mt-1">
            {clip.captions.map((_, i) => (
              <button key={i} onClick={() => setCaptionIdx(i)}
                className={`w-6 h-6 rounded text-xs ${i === captionIdx ? 'bg-accent text-black' : 'bg-edge'}`}>
                {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-400 text-xs">Trim:</span>
        <button className="btn-ghost !px-2" disabled={!!busy} onClick={() => run('trim', () => api.trimClip(clip.id, -1, 0))}>start −1s</button>
        <button className="btn-ghost !px-2" disabled={!!busy} onClick={() => run('trim', () => api.trimClip(clip.id, 1, 0))}>start +1s</button>
        <button className="btn-ghost !px-2" disabled={!!busy} onClick={() => run('trim', () => api.trimClip(clip.id, 0, -1))}>end −1s</button>
        <button className="btn-ghost !px-2" disabled={!!busy} onClick={() => run('trim', () => api.trimClip(clip.id, 0, 1))}>end +1s</button>
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" disabled={!!busy} onClick={() => run('captions', async () => {
          await api.regenerateCaptions(clip.id)
          setMsg({ type: 'ok', text: 'Regenerating captions...' })
        })}>Regen captions</button>
        <button className="btn-ghost" disabled={!!busy} onClick={() => run('rerender', async () => {
          await api.rerender(clip.id, false)
          setMsg({ type: 'ok', text: 'Full re-render queued' })
        })}>Re-render</button>
        <button className="btn-ghost" disabled={!clip.has_file || !!busy} onClick={doExport}>
          {busy === 'export' ? '...' : 'Export'}
        </button>
        <button className="btn-primary" disabled={clip.status !== 'ready' || !!busy || accounts.length === 0}
                title={accounts.length === 0 ? 'Connect a TikTok account in Settings' : ''}
                onClick={() => doPost(false)}>
          {busy === 'post' ? '...' : 'Post to TikTok'}
        </button>
        <button className="btn-danger ml-auto" disabled={!!busy}
                onClick={() => run('delete', () => api.deleteClip(clip.id))}>✕</button>
      </div>

      {pendingPost && (
        <div className="text-xs bg-amber-900/20 border border-amber-700/40 rounded-lg p-2 space-y-1">
          <div className="font-semibold text-amber-300">Blocked before posting:</div>
          {pendingPost.warnings.map((w, i) => <div key={i}>• {w}</div>)}
          {pendingPost.duplicates.map((d, i) => (
            <div key={`d${i}`}>• Duplicate of posted clip #{d.clip_id} ({d.overlap_pct}% overlap)</div>
          ))}
          <div className="flex gap-2 pt-1">
            <button className="btn-ghost !text-xs" onClick={() => doPost(true)}>Post anyway</button>
            <button className="btn-ghost !text-xs" onClick={() => setPendingPost(null)}>Cancel</button>
          </div>
        </div>
      )}

      {msg && (
        <div className={`text-xs ${
          msg.type === 'err' ? 'text-red-400' : msg.type === 'warn' ? 'text-amber-300' : 'text-emerald-400'
        }`}>{msg.text}</div>
      )}
    </div>
  )
}
