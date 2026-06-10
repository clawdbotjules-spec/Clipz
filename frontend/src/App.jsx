import { useState } from 'react'
import IngestPanel from './components/IngestPanel'
import ClipsPage from './components/ClipsPage'
import CampaignsPage from './components/CampaignsPage'
import TrackerPage from './components/TrackerPage'
import SettingsPage from './components/SettingsPage'
import { useJobs } from './hooks/useJobs'

const TABS = ['Create', 'Clips', 'Campaigns', 'Tracker', 'Settings']

export default function App() {
  const [tab, setTab] = useState('Create')
  const { jobs, active } = useJobs()

  return (
    <div className="min-h-screen">
      <header className="border-b border-edge bg-panel/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
          <h1 className="text-lg font-bold">
            <span className="text-accent">Clip</span>Forge
          </h1>
          <nav className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-lg text-sm ${
                  tab === t ? 'bg-accent text-black font-semibold' : 'text-gray-300 hover:bg-edge'
                }`}
              >
                {t}
                {t === 'Create' && active.length > 0 && (
                  <span className="ml-1.5 inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {tab === 'Create' && <IngestPanel jobs={jobs} onDone={() => setTab('Clips')} />}
        {tab === 'Clips' && <ClipsPage jobs={jobs} />}
        {tab === 'Campaigns' && <CampaignsPage />}
        {tab === 'Tracker' && <TrackerPage />}
        {tab === 'Settings' && <SettingsPage />}
      </main>
    </div>
  )
}
