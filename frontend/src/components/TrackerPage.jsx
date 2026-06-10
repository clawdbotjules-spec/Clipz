import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

export default function TrackerPage() {
  const [clips, setClips] = useState([])
  const [videos, setVideos] = useState([])
  const [edits, setEdits] = useState({}) // clipId -> {views, earnings, post_url}

  const refresh = () => {
    api.clips().then(setClips).catch(() => {})
    api.videos().then(setVideos).catch(() => {})
  }
  useEffect(() => { refresh() }, [])

  const videoTitle = useMemo(() => {
    const map = {}
    videos.forEach((v) => { map[v.id] = v.title || v.id })
    return map
  }, [videos])

  const posted = clips.filter((c) => c.posted_at || c.post_url)
  const totals = posted.reduce(
    (acc, c) => ({ views: acc.views + (c.views || 0), earnings: acc.earnings + (c.earnings || 0) }),
    { views: 0, earnings: 0 },
  )

  async function saveRow(c) {
    const e = edits[c.id] || {}
    await api.patchClip(c.id, {
      views: e.views !== undefined ? Number(e.views) : undefined,
      earnings: e.earnings !== undefined ? Number(e.earnings) : undefined,
      post_url: e.post_url,
    })
    setEdits((prev) => { const n = { ...prev }; delete n[c.id]; return n })
    refresh()
  }

  const setField = (id, field, value) =>
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], [field]: value } }))

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6">
        <h2 className="font-semibold text-lg">Clip tracker</h2>
        <span className="text-sm text-gray-400">
          {posted.length} posted · {totals.views.toLocaleString()} views · ${totals.earnings.toFixed(2)} earned
        </span>
        <button className="btn-ghost ml-auto" onClick={refresh}>Refresh</button>
      </div>

      {posted.length === 0 ? (
        <p className="text-sm text-gray-500">
          Nothing posted yet. Posted/exported clips appear here — log views and earnings
          manually to see which source videos and hook styles earn the most.
        </p>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-gray-400 border-b border-edge">
                <th className="py-2 pr-3">Source video</th>
                <th className="py-2 pr-3">Segment</th>
                <th className="py-2 pr-3">Hook</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Posted</th>
                <th className="py-2 pr-3">Post URL</th>
                <th className="py-2 pr-3">Views</th>
                <th className="py-2 pr-3">Earnings $</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {posted.map((c) => {
                const e = edits[c.id] || {}
                return (
                  <tr key={c.id} className="border-b border-edge/50">
                    <td className="py-2 pr-3 max-w-48 truncate">{videoTitle[c.video_id] || c.video_id}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{Math.round(c.start)}s–{Math.round(c.end)}s</td>
                    <td className="py-2 pr-3 max-w-56 truncate" title={c.hook}>{c.hook}</td>
                    <td className="py-2 pr-3">{c.virality_score}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{c.posted_at ? c.posted_at.slice(0, 10) : '—'}</td>
                    <td className="py-2 pr-3">
                      <input className="input !py-1 !text-xs !w-40"
                        value={e.post_url ?? c.post_url}
                        onChange={(ev) => setField(c.id, 'post_url', ev.target.value)} />
                    </td>
                    <td className="py-2 pr-3">
                      <input className="input !py-1 !text-xs !w-24" type="number"
                        value={e.views ?? c.views}
                        onChange={(ev) => setField(c.id, 'views', ev.target.value)} />
                    </td>
                    <td className="py-2 pr-3">
                      <input className="input !py-1 !text-xs !w-24" type="number" step="0.01"
                        value={e.earnings ?? c.earnings}
                        onChange={(ev) => setField(c.id, 'earnings', ev.target.value)} />
                    </td>
                    <td className="py-2">
                      {edits[c.id] && <button className="btn-primary !text-xs" onClick={() => saveRow(c)}>Save</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
