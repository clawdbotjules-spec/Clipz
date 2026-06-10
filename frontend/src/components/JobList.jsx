const STAGE_LABELS = {
  download: 'Downloading',
  transcribe: 'Transcribing',
  analyze: 'Finding viral moments',
  render: 'Rendering clips',
}

function JobRow({ job }) {
  const pct = Math.round(job.progress * 100)
  const color =
    job.status === 'failed' ? 'bg-red-500'
    : job.status === 'done' ? 'bg-emerald-500'
    : 'bg-accent'

  return (
    <div className="bg-ink border border-edge rounded-xl p-3 space-y-2">
      <div className="flex justify-between items-center text-sm">
        <span className="font-medium truncate">
          {job.kind === 'process_video' ? (job.params.url || 'Video') : `Re-render clip #${job.params.clip_id}`}
        </span>
        <span className={
          job.status === 'failed' ? 'text-red-400'
          : job.status === 'done' ? 'text-emerald-400'
          : 'text-amber-300'
        }>
          {job.status}
        </span>
      </div>
      {job.status === 'running' && (
        <>
          <div className="text-xs text-gray-400">
            {STAGE_LABELS[job.stage] || job.stage} — {job.message}
          </div>
          <div className="h-1.5 bg-edge rounded-full overflow-hidden">
            <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
          </div>
        </>
      )}
      {job.status === 'failed' && <div className="text-xs text-red-400">{job.error}</div>}
      {job.status === 'done' && job.result?.clip_ids && (
        <div className="text-xs text-gray-400">{job.result.clip_ids.length} clips created</div>
      )}
    </div>
  )
}

export default function JobList({ jobs }) {
  return (
    <div className="card">
      <h2 className="font-semibold mb-3">Queue</h2>
      {jobs.length === 0 ? (
        <p className="text-sm text-gray-500">No jobs yet. Paste a URL to get started.</p>
      ) : (
        <div className="space-y-2 max-h-[32rem] overflow-y-auto pr-1">
          {jobs.map((j) => <JobRow key={j.id} job={j} />)}
        </div>
      )}
    </div>
  )
}
