import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// Live job state: websocket push with polling fallback.
export function useJobs() {
  const [jobs, setJobs] = useState([])
  const wsOk = useRef(false)

  useEffect(() => {
    let alive = true
    api.jobs().then((j) => alive && setJobs(j)).catch(() => {})

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/jobs`)
    ws.onopen = () => { wsOk.current = true }
    ws.onclose = () => { wsOk.current = false }
    ws.onmessage = (ev) => {
      const update = JSON.parse(ev.data)
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.id === update.id)
        if (idx === -1) return [update, ...prev]
        const next = [...prev]
        next[idx] = update
        return next
      })
    }

    const poll = setInterval(() => {
      if (!wsOk.current) api.jobs().then((j) => alive && setJobs(j)).catch(() => {})
    }, 2500)

    return () => { alive = false; ws.close(); clearInterval(poll) }
  }, [])

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running')
  return { jobs, active }
}
