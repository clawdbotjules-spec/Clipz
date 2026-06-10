import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import ClipCard from './ClipCard'

export default function ClipsPage({ jobs }) {
  const [clips, setClips] = useState([])
  const [videos, setVideos] = useState([])
  const [videoFilter, setVideoFilter] = useState('')
  const [accounts, setAccounts] = useState([])

  const refresh = () => {
    api.clips(videoFilter || undefined).then(setClips).catch(() => {})
    api.videos().then(setVideos).catch(() => {})
  }

  useEffect(() => { refresh() }, [videoFilter])
  useEffect(() => { api.tiktokAccounts().then(setAccounts).catch(() => {}) }, [])

  // refresh the grid whenever a job completes
  const doneCount = useMemo(() => jobs.filter((j) => j.status === 'done').length, [jobs])
  useEffect(() => { refresh() }, [doneCount])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="font-semibold text-lg">Generated clips</h2>
        <select className="input !w-auto" value={videoFilter} onChange={(e) => setVideoFilter(e.target.value)}>
          <option value="">All videos</option>
          {videos.map((v) => (
            <option key={v.id} value={v.id}>{v.title.slice(0, 60) || v.id}</option>
          ))}
        </select>
        <button className="btn-ghost" onClick={refresh}>Refresh</button>
      </div>

      {clips.length === 0 ? (
        <p className="text-gray-500 text-sm">No clips yet — process a video from the Create tab.</p>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {clips.map((c) => (
            <ClipCard key={c.id} clip={c} accounts={accounts} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  )
}
