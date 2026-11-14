import { useEffect, useState } from 'react'

const repository = 'https://github.com/gbarbozamar/field-shift-rotation-twin'

export function App() {
  const [route, setRoute] = useState(window.location.hash)
  useEffect(() => {
    const navigate = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  const status = route === '#/status'

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace" onClick={event => { event.preventDefault(); document.getElementById('workspace')?.focus() }}>Skip to content</a>
      <header className="site-header">
        <a className="wordmark" href="#/" aria-label="Field Shift Rotation Twin home">
          <span className="brand-mark" aria-hidden="true">F<span>S</span></span>
          <span>Field Shift<span className="wordmark-subtitle">Rotation Twin</span></span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#/" aria-current={!status ? 'page' : undefined}>Overview</a>
          <a href="#/status" aria-current={status ? 'page' : undefined}>Status</a>
        </nav>
      </header>

      <main id="workspace" tabIndex={-1}>
        <div className="section-label"><span className="status-dot" />Research prototype</div>
        {status ? (
          <section className="workspace-content" aria-labelledby="page-title">
            <p className="eyebrow">Workspace status</p>
            <h1 id="page-title">What is available.</h1>
            <p className="intro">The application shell is ready. Calculation modules are still being developed.</p>
            <dl className="availability-list">
              <div><dt>Application shell</dt><dd className="available">Available</dd></div>
              <div><dt>Rotation analysis</dt><dd>Not available yet</dd></div>
              <div><dt>Climate data</dt><dd>Not available yet</dd></div>
              <div><dt>Saved cases</dt><dd>Not available yet</dd></div>
            </dl>
            <a className="text-link" href={repository}>Follow development on GitHub <span aria-hidden="true">↗</span></a>
          </section>
        ) : (
          <section className="workspace-content" aria-labelledby="page-title">
            <p className="eyebrow">Field Shift Rotation Twin</p>
            <h1 id="page-title">Rotation<br />workspace.</h1>
            <p className="intro">An open-source research prototype for comparing crop rotations against the observed climate record.</p>
            <div className="prototype-notice" role="status">
              <span className="notice-label">Application shell</span>
              <p>Rotation calculations are not available yet.</p>
            </div>
            <a className="primary-link" href="#/status">View workspace status <span aria-hidden="true">→</span></a>
          </section>
        )}
        <div className="field-lines" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
      </main>

      <footer className="site-footer">
        <p>This is a research prototype made for a hackathon. It is not agronomic advice and it does not replace a professional soil-use plan.</p>
        <a href={repository}>Source code ↗</a>
      </footer>
    </div>
  )
}
