import { useEffect, useState } from 'react'
import { api } from '../api'

const EMPTY = {
  name: '',
  required_hashtags: [],
  required_mentions: [],
  required_text: [],
  banned_words: [],
  min_clip_seconds: 0,
  max_clip_seconds: 0,
  watermark_position: 'bottom-right',
  is_active: false,
}

function ListInput({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input"
        placeholder={placeholder}
        value={value.join(', ')}
        onChange={(e) => onChange(e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
      />
    </div>
  )
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([])
  const [editing, setEditing] = useState(null) // null | {id?, ...fields}
  const [error, setError] = useState('')

  const refresh = () => api.campaigns().then(setCampaigns).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function save() {
    setError('')
    try {
      if (editing.id) await api.updateCampaign(editing.id, editing)
      else await api.createCampaign(editing)
      setEditing(null)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  async function uploadWm(id, file) {
    try {
      await api.uploadWatermark(id, file)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-lg">Campaign profiles</h2>
        <button className="btn-primary" onClick={() => setEditing({ ...EMPTY })}>New campaign</button>
      </div>
      <p className="text-sm text-gray-400">
        Save Whop campaign rules once — every render and post is validated against the
        selected campaign (hashtags, mentions, banned words, length, watermark).
      </p>

      {editing && (
        <div className="card space-y-3 max-w-2xl">
          <div>
            <label className="label">Name</label>
            <input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
          </div>
          <ListInput label="Required hashtags (comma-separated)" placeholder="#whop, #creatorname"
            value={editing.required_hashtags} onChange={(v) => setEditing({ ...editing, required_hashtags: v })} />
          <ListInput label="Required @mentions" placeholder="@creator"
            value={editing.required_mentions} onChange={(v) => setEditing({ ...editing, required_mentions: v })} />
          <div>
            <label className="label">Required caption text (one phrase per line)</label>
            <textarea
              className="input h-20 text-sm"
              placeholder={'Phrases the post caption must contain, e.g.\nclips from the official podcast\nlink in bio'}
              value={(editing.required_text || []).join('\n')}
              onChange={(e) => setEditing({ ...editing, required_text: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
            />
          </div>
          <ListInput label="Banned words" placeholder="word1, word2"
            value={editing.banned_words} onChange={(v) => setEditing({ ...editing, banned_words: v })} />
          <div className="flex gap-4">
            <div>
              <label className="label">Min clip seconds</label>
              <input className="input !w-28" type="number" value={editing.min_clip_seconds}
                onChange={(e) => setEditing({ ...editing, min_clip_seconds: Number(e.target.value) })} />
            </div>
            <div>
              <label className="label">Max clip seconds (0 = none)</label>
              <input className="input !w-28" type="number" value={editing.max_clip_seconds}
                onChange={(e) => setEditing({ ...editing, max_clip_seconds: Number(e.target.value) })} />
            </div>
            <div>
              <label className="label">Watermark position</label>
              <select className="input !w-auto" value={editing.watermark_position}
                onChange={(e) => setEditing({ ...editing, watermark_position: e.target.value })}>
                {['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center'].map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={editing.is_active}
              onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />
            Set as active campaign (preselected on new videos)
          </label>
          <div className="flex gap-2">
            <button className="btn-primary" onClick={save} disabled={!editing.name}>Save</button>
            <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
          </div>
          {error && <div className="text-sm text-red-400">{error}</div>}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {campaigns.map((c) => (
          <div key={c.id} className="card space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{c.name}</span>
              {c.is_active && <span className="text-xs bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full">active</span>}
            </div>
            <div className="text-xs text-gray-400 space-y-1">
              {c.required_hashtags.length > 0 && <div>Hashtags: {c.required_hashtags.join(' ')}</div>}
              {c.required_mentions.length > 0 && <div>Mentions: {c.required_mentions.join(' ')}</div>}
              {(c.required_text || []).length > 0 && <div>Required text: {c.required_text.map((t) => `"${t}"`).join(', ')}</div>}
              {c.banned_words.length > 0 && <div>Banned: {c.banned_words.join(', ')}</div>}
              <div>
                Length: {c.min_clip_seconds || 0}s – {c.max_clip_seconds || '∞'}s
                · Watermark: {c.watermark_path ? `✓ ${c.watermark_position}` : 'none'}
              </div>
            </div>
            <div className="flex gap-2 items-center">
              <button className="btn-ghost" onClick={() => setEditing({ ...c })}>Edit</button>
              <label className="btn-ghost cursor-pointer">
                {c.watermark_path ? 'Replace watermark' : 'Upload watermark'}
                <input type="file" accept="image/*" className="hidden"
                  onChange={(e) => e.target.files[0] && uploadWm(c.id, e.target.files[0])} />
              </label>
              <button className="btn-danger ml-auto" onClick={async () => { await api.deleteCampaign(c.id); refresh() }}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
