import { useState } from 'react';
import { navigation } from './navigation';

export function App() {
  const [active, setActive] = useState(navigation[0].label);
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">N</span><div><strong>Nexora</strong><small>INCIDENT INTELLIGENCE</small></div></div>
      <div className="workspace-label">TEAM 4 WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map((item, i) => <button key={item.label} className={`nav-item ${active === item.label ? 'active' : ''}`} onClick={() => setActive(item.label)}><span className="nav-index">{String(i + 1).padStart(2, '0')}</span>{item.label}</button>)}</nav>
      <div className="sidebar-bottom"><span className="status-dot"/> Local development <span className="version">v0.1.0</span></div>
    </aside>
    <main className="main"><header className="topbar"><span>Incident management <b>/</b> {active}</span><span className="avatar">T4</span></header>
      <section className="content"><div className="eyebrow">TEAM 4 · INCIDENT MANAGEMENT & RCA</div><h1>{active}</h1><p className="intro">A focused workspace for incident investigation, evidence, and human-guided resolution.</p>
        <div className="welcome-card"><div className="card-icon">✳</div><div><span className="pill">FOUNDATION READY</span><h2>Your investigation workspace</h2><p>This area is ready for the {active.toLowerCase()} experience. The backend foundation exposes a health endpoint and versioned API for the next implementation steps.</p><div className="card-meta"><span><i className="green-dot"/> API foundation</span><span><i className="green-dot"/> PostgreSQL ready to connect</span></div></div></div>
        <div className="section-heading"><div><span className="eyebrow">THE INVESTIGATION FLOW</span><h2>From signal to resolution</h2></div><span className="muted">Modular monolith · Team 4</span></div>
        <div className="flow-grid">{['Capture the incident','Build the evidence','Evaluate root causes','Review and resolve'].map((title, i) => <article className="flow-card" key={title}><span className="flow-num">0{i + 1}</span><h3>{title}</h3><p>{['Record context and establish a clear timeline.','Collect findings and keep every source traceable.','Compare supporting and contradicting evidence.','Keep people in control of approvals and closure.'][i]}</p><span className="flow-line"/></article>)}</div>
        <div className="note"><strong>Setup scaffold</strong><span>Incident workflows, live AI analysis, and persistence are not implemented yet. This interface is a navigation and layout foundation.</span></div>
      </section>
    </main>
  </div>;
}
