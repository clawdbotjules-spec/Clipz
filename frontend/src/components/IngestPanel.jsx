import { useEffect, useState } from 'react'
import { api } from '../api'
import JobList from './JobList'

function fmtDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}

export default function IngestPanel({ jobs }) {
  const [mode, setMode] = useState('single') // single | batch | upload
  const [url, setUrl] = useState('')
  const [batchUrls, setBatchUrls] = useState('')
  const [preview, setPreview] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [localFile, setLocalFile] = useState(null)      // File chosen from disk
  const [uploaded, setUploaded] = useState(null)        // server response after upload
  const [uploading, setUploading] = useState(false)
  const [useRange, setUseRange] = useState(false)
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [blurBg, setBlurBg] = useState(false)
  const [campaigns, setCampaigns] = useState([])
  const [campaignId, setCampaignId] = useState('')
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    api.campaigns().then((cs) => {
      setCampaigns(cs)
      const active = cs.find((c) => c.is_active)
      if (active) setCampaignId(String(active.id))
    }).catch(() => {})
  }, [])

  async function doPreview() {
    setError(''); setPreview(null); setLoadingPreview(true)
    try {
      const meta = await api.preview(url)
      setPreview(meta)
      if (meta.too_long) setUseRange(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoadingPreview(false)
    }
  }

  async function submit() {
    setError(''); setSubmitted(false)
    try {
      if (mode === 'batch') {
        const urls = batchUrls.split('\n').map((u) => u.trim()).filter(Boolean)
        await api.batch({ urls, campaign_id: campaignId ? Number(campaignId) : null, blur_background: blurBg })
      } else {
        const payload = {
          campaign_id: campaignId ? Number(campaignId) : null,
          blur_background: blurBg,
        }
        if (useRange && rangeStart !== '' && rangeEnd !== '') {
          payload.start_minute = Number(rangeStart)
          payload.end_minute = Number(rangeEnd)
        }
        if (mode === 'upload') {
          let meta = uploaded
          if (!meta) {
            setUploading(true)
            try {
              meta = await api.uploadVideo(localFile)
              setUploaded(meta)
              if (meta.too_long && !(useRange && rangeStart !== '' && rangeEnd !== '')) {
                setUseRange(true)
                setError(`File is over ${meta.max_hours}h — pick a time range, then hit the button again.`)
                return
              }
            } finally {
              setUploading(false)
            }
          }
          payload.video_id = meta.id
        } else {
          payload.url = url
        }
        await api.process(payload)
      }
      setSubmitted(true)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="space-y-4">
        <div className="card space-y-4">
          <div className="flex gap-2">
            <button className={mode === 'single' ? 'btn-primary' : 'btn-ghost'} onClick={() => setMode('single')}>
              Single video
            </button>
            <button className={mode === 'batch' ? 'btn-primary' : 'btn-ghost'} onClick={() => setMode('batch')}>
              Batch mode
            </button>
            <button className={mode === 'upload' ? 'btn-primary' : 'btn-ghost'} onClick={() => setMode('upload')}>
              Upload file
            </button>
          </div>

          {mode === 'upload' && (
            <>
              <label className="block border-2 border-dashed border-edge rounded-xl p-6 text-center cursor-pointer hover:border-accent transition-colors">
                <input
                  type="file"
                  accept=".mp4,.mov,.mkv,.webm,.avi,.m4v,video/*"
                  className="hidden"
                  onChange={(e) => {
                    setLocalFile(e.target.files[0] || null)
                    setUploaded(null)
                    setError('')
                  }}
                />
                {localFile ? (
                  <div>
                    <div className="font-medium">{localFile.name}</div>
                    <div className="text-sm text-gray-400">
                      {(localFile.size / 1024 / 1024).toFixed(1)} MB — click to choose a different file
                    </div>
                  </div>
                ) : (
                  <div className="text-gray-400 text-sm">
                    Click to choose a video file from your computer
                    <div className="text-xs text-gray-500 mt-1">mp4, mov, mkv, webm, avi</div>
                  </div>
                )}
              </label>
              {uploaded && (
                <div className="text-sm text-emerald-400">
                  Uploaded: {uploaded.title} ({fmtDuration(uploaded.duration)})
                </div>
              )}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useRange} onChange={(e) => setUseRange(e.target.checked)} />
                Time-range mode (process only minutes X–Y)
              </label>
              {useRange && (
                <div className="flex items-center gap-2 text-sm">
                  <span>From minute</span>
                  <input className="input !w-24" type="number" min="0" value={rangeStart} onChange={(e) => setRangeStart(e.target.value)} />
                  <span>to</span>
                  <input className="input !w-24" type="number" min="0" value={rangeEnd} onChange={(e) => setRangeEnd(e.target.value)} />
                </div>
              )}
            </>
          )}

          {mode === 'single' && (
            <>
              <div className="flex gap-2">
                <input
                  className="input"
                  placeholder="Paste a YouTube URL..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && doPreview()}
                />
                <button className="btn-ghost whitespace-nowrap" onClick={doPreview} disabled={!url || loadingPreview}>
                  {loadingPreview ? 'Loading...' : 'Preview'}
                </button>
              </div>

              {preview && (
                <div className="flex gap-3 bg-ink rounded-xl p-3 border border-edge">
                  {preview.thumbnail && (
                    <img src={preview.thumbnail} alt="" className="w-36 h-20 object-cover rounded-lg" />
                  )}
                  <div className="min-w-0">
                    <div className="font-medium truncate">{preview.title}</div>
                    <div className="text-sm text-gray-400">{preview.channel} · {fmtDuration(preview.duration)}</div>
                    {preview.too_long && (
                      <div className="text-sm text-amber-400 mt-1">
                        Over {preview.max_hours}h — select a time range below.
                      </div>
                    )}
                  </div>
                </div>
              )}

              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useRange} onChange={(e) => setUseRange(e.target.checked)} />
                Time-range mode (process only minutes X–Y)
              </label>
              {useRange && (
                <div className="flex items-center gap-2 text-sm">
                  <span>From minute</span>
                  <input className="input !w-24" type="number" min="0" value={rangeStart} onChange={(e) => setRangeStart(e.target.value)} />
                  <span>to</span>
                  <input className="input !w-24" type="number" min="0" value={rangeEnd} onChange={(e) => setRangeEnd(e.target.value)} />
                </div>
              )}
            </>
          )}

          {mode === 'batch' && (
            <textarea
              className="input h-40 font-mono"
              placeholder={'One YouTube URL per line...\nhttps://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...'}
              value={batchUrls}
              onChange={(e) => setBatchUrls(e.target.value)}
            />
          )}

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={blurBg} onChange={(e) => setBlurBg(e.target.checked)} />
              Blurred background mode
            </label>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-400">Campaign:</span>
              <select className="input !w-auto" value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
                <option value="">None</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}{c.is_active ? ' (active)' : ''}</option>
                ))}
              </select>
            </div>
          </div>

          <button
            className="btn-primary w-full py-2.5"
            onClick={submit}
            disabled={
              uploading
              || (mode === 'single' && !url)
              || (mode === 'batch' && !batchUrls.trim())
              || (mode === 'upload' && !localFile)
            }
          >
            {uploading ? 'Uploading...' : 'Find viral clips'}
          </button>

          {error && <div className="text-sm text-red-400">{error}</div>}
          {submitted && (
            <div className="text-sm text-emerald-400">
              Queued! Watch progress on the right — clips land in the Clips tab.
            </div>
          )}
        </div>
      </div>

      <JobList jobs={jobs} />
    </div>
  )
}
