async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch { /* non-json error body */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  // videos
  preview: (url) => request('/api/videos/preview', { method: 'POST', body: JSON.stringify({ url }) }),
  process: (payload) => request('/api/videos/process', { method: 'POST', body: JSON.stringify(payload) }),
  batch: (payload) => request('/api/videos/batch', { method: 'POST', body: JSON.stringify(payload) }),
  videos: () => request('/api/videos'),

  // jobs
  jobs: () => request('/api/jobs'),
  job: (id) => request(`/api/jobs/${id}`),

  // clips
  clips: (videoId) => request(videoId ? `/api/clips?video_id=${videoId}` : '/api/clips'),
  patchClip: (id, patch) => request(`/api/clips/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  trimClip: (id, deltaStart, deltaEnd) =>
    request(`/api/clips/${id}/trim`, { method: 'POST', body: JSON.stringify({ delta_start: deltaStart, delta_end: deltaEnd }) }),
  rerender: (id, textOnly = false) =>
    request(`/api/clips/${id}/rerender?text_only=${textOnly}`, { method: 'POST' }),
  regenerateCaptions: (id) => request(`/api/clips/${id}/regenerate-captions`, { method: 'POST' }),
  exportClip: (id, captionIndex = 0) => request(`/api/clips/${id}/export?caption_index=${captionIndex}`),
  postClip: (id, payload) => request(`/api/clips/${id}/post`, { method: 'POST', body: JSON.stringify(payload) }),
  deleteClip: (id) => request(`/api/clips/${id}`, { method: 'DELETE' }),

  // campaigns
  campaigns: () => request('/api/campaigns'),
  createCampaign: (data) => request('/api/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  updateCampaign: (id, data) => request(`/api/campaigns/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCampaign: (id) => request(`/api/campaigns/${id}`, { method: 'DELETE' }),
  uploadWatermark: async (id, file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`/api/campaigns/${id}/watermark`, { method: 'POST', body: form })
    if (!res.ok) throw new Error('Watermark upload failed')
    return res.json()
  },

  // settings + tiktok
  settings: () => request('/api/settings'),
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  tiktokAuthUrl: () => request('/api/tiktok/auth-url'),
  tiktokAccounts: () => request('/api/tiktok/accounts'),
  disconnectTiktok: (id) => request(`/api/tiktok/accounts/${id}`, { method: 'DELETE' }),
}
