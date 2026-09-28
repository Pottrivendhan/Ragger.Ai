import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  Play,
  Sparkles,
  Layers,
  Database,
  Cpu,
  Bot,
  ShieldCheck,
  Lock,
  FileCheck,
  CheckCircle2,
  FolderLock,
  Workflow,
  Search,
  BookOpen,
  GitBranch,
  Clock,
} from 'lucide-react';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';
import raggerFullLogo from '../../assets/ragger.ai_full_logo.png';

interface LandingViewProps {
  onGetStarted: () => void;
  onSignIn: () => void;
}

export const LandingView: React.FC<LandingViewProps> = ({ onGetStarted, onSignIn }) => {
  const [activeSection, setActiveSection] = useState<string>('hero');
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Smooth scroll helper for landing page sections
  const scrollToSection = (sectionId: string) => {
    setActiveSection(sectionId);
    if (window.history.pushState) {
      window.history.pushState(null, '', `#${sectionId}`);
    }
    const elem = document.getElementById(sectionId);
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Support direct URL hash loading on mount (e.g. #pricing)
  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash) {
      setTimeout(() => {
        scrollToSection(hash);
      }, 150);
    }
  }, []);

  // IntersectionObserver to dynamically highlight the current visible section
  useEffect(() => {
    const sectionIds = ['product', 'solutions', 'security', 'pricing'];
    const container = scrollContainerRef.current;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        });
      },
      {
        root: container,
        rootMargin: '-20% 0px -60% 0px',
        threshold: 0.1,
      }
    );

    sectionIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={scrollContainerRef}
      style={{
        position: 'relative',
        height: '100%',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        overflowX: 'hidden',
        scrollBehavior: 'smooth',
      }}
    >
      {/* Top Navbar (Visually unchanged, now fully functional with section links) */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 48px',
          maxWidth: 1320,
          width: '100%',
          margin: '0 auto',
          background: 'rgba(248, 250, 252, 0.92)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(15, 23, 42, 0.05)',
        }}
      >
        {/* Brand identity */}
        <div
          onClick={() => {
            if (scrollContainerRef.current) {
              scrollContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
            }
          }}
          style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, cursor: 'pointer' }}
          title="Ragger.ai Home"
        >
          <img
            src={raggerBoxLogo}
            alt="Ragger.ai Box Logo"
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              objectFit: 'contain',
              boxShadow: '0 2px 8px rgba(79, 70, 229, 0.15)',
            }}
          />
          <img
            src={raggerFullLogo}
            alt="Ragger.ai Full Logo"
            style={{
              height: 32,
              objectFit: 'contain',
            }}
          />
        </div>

        {/* Functional Navigation Buttons */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => scrollToSection('product')}
            className={`landing-nav-item ${activeSection === 'product' ? 'active' : ''}`}
            id="nav-link-product"
          >
            Product
          </button>
          <button
            type="button"
            onClick={() => scrollToSection('solutions')}
            className={`landing-nav-item ${activeSection === 'solutions' ? 'active' : ''}`}
            id="nav-link-solutions"
          >
            Solutions
          </button>
          <button
            type="button"
            onClick={() => scrollToSection('security')}
            className={`landing-nav-item ${activeSection === 'security' ? 'active' : ''}`}
            id="nav-link-security"
          >
            Security
          </button>
          <button
            type="button"
            onClick={() => scrollToSection('pricing')}
            className={`landing-nav-item ${activeSection === 'pricing' ? 'active' : ''}`}
            id="nav-link-pricing"
          >
            Pricing
          </button>

          <button
            onClick={onSignIn}
            className="landing-btn-signin"
            id="btn-landing-signin"
          >
            Sign in
          </button>
          <button onClick={onGetStarted} className="btn-primary" style={{ padding: '8px 20px', fontSize: 13 }}>
            Get started
          </button>
        </nav>
      </header>

      {/* ================================================================
          HERO SECTION (Identical visual orbital core, perfectly preserved)
         ================================================================ */}
      <section
        id="hero"
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: '24px 24px 60px',
          maxWidth: 1120,
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* Pill Badge */}
        <div
          className="badge-pill badge-pill-blue"
          style={{ marginBottom: 20, padding: '6px 16px', background: 'rgba(239, 246, 255, 0.9)' }}
        >
          <Sparkles size={13} color="#2563EB" />
          <span style={{ fontSize: 13, fontWeight: 600 }}>Your Data. Real Understanding.</span>
        </div>

        {/* Hero Title */}
        <h1 className="hero-title" style={{ marginBottom: 18 }}>
          Turn Your <span style={{ background: 'linear-gradient(135deg, #0F172A 20%, #4F46E5 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Data</span><br />
          Into Intelligence
        </h1>

        {/* Subtitle */}
        <p className="hero-subtitle" style={{ marginBottom: 28 }}>
          Build powerful RAG systems from your documents, launch private AI agents, and chat with your knowledge — all in one seamless platform.
        </p>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 50 }}>
          <button onClick={onGetStarted} className="btn-primary" style={{ padding: '12px 28px', fontSize: 15 }}>
            <span>Get Started</span>
            <ArrowRight size={16} />
          </button>
          <button onClick={() => scrollToSection('product')} className="btn-secondary" style={{ padding: '12px 24px', fontSize: 15 }}>
            <Play size={15} fill="#0F172A" />
            <span>Explore Platform</span>
          </button>
        </div>

        {/* Center Visual Stage with Fixed R Logo & Circular Orbit of File Badges */}
        <div className="hero-orbit-stage">
          {/* Subtle Radial Glow behind Center R */}
          <div className="hero-center-glow" />

          {/* Concentric Subtle Orbit Rings */}
          <div className="orbit-ring-guide orbit-ring-primary" />
          <div className="orbit-ring-guide orbit-ring-secondary" />
          <div className="orbit-ring-guide orbit-ring-outer" />

          {/* Permanently Fixed Center R Logo (NEVER rotates or drifts) */}
          <div className="hero-center-core">
            <div className="hero-center-orb">
              <img
                src={raggerBoxLogo}
                alt="Ragger AI Core"
                style={{
                  width: 54,
                  height: 54,
                  borderRadius: 14,
                  objectFit: 'contain',
                }}
              />
            </div>
          </div>

          {/* Rotating Orbital Track (Smooth 36s continuous rotation) */}
          <div className="orbit-track">
            {[
              { ext: 'PDF', color: '#DC2626', bg: '#FEE2E2', angleDeg: 270 },
              { ext: 'DOCX', color: '#2563EB', bg: '#DBEAFE', angleDeg: 330 },
              { ext: 'CSV', color: '#059669', bg: '#D1FAE5', angleDeg: 30 },
              { ext: 'TXT', color: '#7C3AED', bg: '#F3E8FF', angleDeg: 90 },
              { ext: 'PPTX', color: '#EA580C', bg: '#FFEDD5', angleDeg: 150 },
              { ext: 'SVG', color: '#D97706', bg: '#FEF3C7', angleDeg: 210 },
            ].map((item) => {
              const rad = (item.angleDeg * Math.PI) / 180;
              const cos = Math.cos(rad);
              const sin = Math.sin(rad);

              return (
                <div
                  key={item.ext}
                  className="orbit-item-slot"
                  style={{
                    transform: `translate(calc(${cos} * var(--orbit-radius)), calc(${sin} * var(--orbit-radius)))`,
                  }}
                >
                  <div className="orbit-badge-card" id={`orbit-badge-${item.ext.toLowerCase()}`}>
                    <span
                      style={{
                        background: item.bg,
                        color: item.color,
                        fontSize: 10,
                        fontWeight: 800,
                        padding: '2px 6px',
                        borderRadius: 4,
                        letterSpacing: '0.04em',
                      }}
                    >
                      {item.ext}
                    </span>
                    <span style={{ color: '#0F172A', fontWeight: 600 }}>{item.ext}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Feature Strip */}
        <div
          style={{
            marginTop: 48,
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 32,
            width: '100%',
            maxWidth: 780,
            paddingTop: 32,
            borderTop: '1px solid rgba(15, 23, 42, 0.06)',
            textAlign: 'left',
          }}
        >
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>Any Document</div>
            <div style={{ fontSize: 12, color: '#64748B' }}>Upload your files</div>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>Any Format</div>
            <div style={{ fontSize: 12, color: '#64748B' }}>We understand</div>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>Your Intelligence</div>
            <div style={{ fontSize: 12, color: '#64748B' }}>You stay in control</div>
          </div>
        </div>
      </section>

      {/* ================================================================
          SECTION 1: PRODUCT
         ================================================================ */}
      <section id="product" className="landing-section">
        <div className="landing-section-header">
          <div className="landing-section-pill" style={{ background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' }}>
            <Layers size={13} />
            <span>PLATFORM CAPABILITIES</span>
          </div>
          <h2 className="landing-section-title">The Complete Local RAG Architecture</h2>
          <p className="landing-section-desc">
            From raw files to compiled vector builds and grounded conversational assistants, Ragger.ai handles every step of your knowledge lifecycle locally.
          </p>
        </div>

        <div className="landing-grid-3">
          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#EFF6FF', color: '#2563EB' }}>
              <Database size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Automated Intake & Profiling</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Upload PDFs, DOCX, CSVs, and text files. Ragger extracts text, preserves structure, and performs statistical document profiling in real time.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#F5F3FF', color: '#7C3AED' }}>
              <Workflow size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Architecture Recommendation</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Heuristic and LLM analysis evaluate your documents to recommend optimal chunking strategies, embedding dimensions, and retrieval index structures.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#ECFDF5', color: '#059669' }}>
              <GitBranch size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Versioned RAG Library</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Every build is an immutable knowledge artifact. Inspect chunk distributions, rollback active versions, and compare differences across builds.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#FFFBEB', color: '#D97706' }}>
              <Cpu size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Local GGUF LLM Execution</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Generate responses locally with zero external network leakage. Full hardware-accelerated token streaming with verifiable runtime telemetry.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#FEF2F2', color: '#DC2626' }}>
              <FileCheck size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Evidence Gate & Citations</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Rigorous grounding checks evaluate evidence sufficiency before generation. Every cited fact includes source document and page number provenance.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#F0FDF4', color: '#16A34A' }}>
              <Bot size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>AI Agent Workspace</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Configure specialized AI assistants, attach multiple RAG knowledge bases on-the-fly with multi-RAG fusion, and conduct persistent conversations.
            </p>
          </div>
        </div>
      </section>

      {/* ================================================================
          SECTION 2: SOLUTIONS
         ================================================================ */}
      <section id="solutions" className="landing-section" style={{ background: 'rgba(241, 245, 249, 0.45)', borderRadius: 24 }}>
        <div className="landing-section-header">
          <div className="landing-section-pill" style={{ background: '#F5F3FF', color: '#7C3AED', border: '1px solid #DDD6FE' }}>
            <Workflow size={13} />
            <span>SOLUTIONS & WORKFLOWS</span>
          </div>
          <h2 className="landing-section-title">Designed for Real-World Knowledge Work</h2>
          <p className="landing-section-desc">
            Organize complex data libraries into accessible, queryable AI assistants without vendor lock-in or cloud dependencies.
          </p>
        </div>

        <div className="landing-grid-2">
          <div className="landing-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div className="landing-card-icon" style={{ background: '#EFF6FF', color: '#2563EB', marginBottom: 0 }}>
                <BookOpen size={20} />
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', margin: 0 }}>Document Knowledge Retrieval</h3>
            </div>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6, marginBottom: 16 }}>
              Turn dense handbooks, technical standards, policies, and educational curriculum into high-precision question-answering systems with exact page citations.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Textbooks</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Policy Manuals</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Technical Specs</span>
            </div>
          </div>

          <div className="landing-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div className="landing-card-icon" style={{ background: '#F5F3FF', color: '#7C3AED', marginBottom: 0 }}>
                <Layers size={20} />
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', margin: 0 }}>Multi-Knowledge Synthesis</h3>
            </div>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6, marginBottom: 16 }}>
              Attach distinct knowledge bases to a single agent. Multi-RAG query planning retrieves evidence across disparate sources with Reciprocal Rank Fusion.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Cross-Department</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Multi-RAG Fusion</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Zero Bleed</span>
            </div>
          </div>

          <div className="landing-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div className="landing-card-icon" style={{ background: '#ECFDF5', color: '#059669', marginBottom: 0 }}>
                <Search size={20} />
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', margin: 0 }}>Academic & Legal Research</h3>
            </div>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6, marginBottom: 16 }}>
              Rigorously grounded responses ensure zero hallucinated legal clauses or research claims. The Evidence Gate fails closed when knowledge is insufficient.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Evidence Verification</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Zero Hallucination</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Exact Provenance</span>
            </div>
          </div>

          <div className="landing-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div className="landing-card-icon" style={{ background: '#FFFBEB', color: '#D97706', marginBottom: 0 }}>
                <Bot size={20} />
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', margin: 0 }}>Autonomous Knowledge Assistants</h3>
            </div>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6, marginBottom: 16 }}>
              Tailor unique assistant personas with dedicated system directives and grounded conversational history, ready to assist your team locally.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Agent Profiles</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Local LLM</span>
              <span className="badge-pill" style={{ background: '#F1F5F9', color: '#475569', fontSize: 11 }}>Session Isolation</span>
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================
          SECTION 3: SECURITY
         ================================================================ */}
      <section id="security" className="landing-section">
        <div className="landing-section-header">
          <div className="landing-section-pill" style={{ background: '#ECFDF5', color: '#059669', border: '1px solid #A7F3D0' }}>
            <ShieldCheck size={13} />
            <span>SECURITY ARCHITECTURE</span>
          </div>
          <h2 className="landing-section-title">Built on Strict Privacy & Isolation</h2>
          <p className="landing-section-desc">
            Ragger.ai enforces security through architecture. Your data, embeddings, and inference remain entirely on your local machine.
          </p>
        </div>

        <div className="landing-grid-3">
          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#ECFDF5', color: '#059669' }}>
              <Lock size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Local-First Execution</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              All parsing, chunking, vector indexing, and GGUF generation run on your workstation. No external API keys or cloud server dependencies required.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#EFF6FF', color: '#2563EB' }}>
              <FolderLock size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Account Data Isolation</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Every local account has an isolated workspace. Knowledge bases, conversations, notes, and agents created by Account A are completely invisible to Account B.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#F5F3FF', color: '#7C3AED' }}>
              <FileCheck size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Verified Citations & Provenance</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Answers are bound to extracted chunk IDs, file hashes, and page numbers. Ragger eliminates hallucinated attributions before displaying results.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#FEF2F2', color: '#DC2626' }}>
              <ShieldCheck size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Strict Evidence Gate</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              When questions fall outside the scope of attached knowledge bases, Ragger fails closed instead of guessing, preventing misinformation.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#FFFBEB', color: '#D97706' }}>
              <Database size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Weight-Free Portable RAGPacks</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Exportable .ragpack packages bundle vector indexes and text chunks without distributing model weights, ensuring lightweight and safe portability.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: '#F0FDF4', color: '#16A34A' }}>
              <CheckCircle2 size={22} />
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>Safe Deletion Cascades</h3>
            <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>
              Deleting a RAG artifact safely detaches all references from AI agents and cleans up storage without leaving orphaned files or broken references.
            </p>
          </div>
        </div>
      </section>

      {/* ================================================================
          SECTION 4: PRICING
         ================================================================ */}
      <section id="pricing" className="landing-section" style={{ borderTop: '1px solid rgba(15, 23, 42, 0.06)' }}>
        <div className="landing-section-header">
          <div className="landing-section-pill" style={{ background: '#F1F5F9', color: '#475569', border: '1px solid #E2E8F0' }}>
            <Clock size={13} />
            <span>TRANSPARENT TIERS</span>
          </div>
          <h2 className="landing-section-title">Local & Self-Hosted</h2>
          <p className="landing-section-desc">
            Ragger.ai is designed to run locally on your hardware. Enterprise and cloud management plans will be announced soon.
          </p>
        </div>

        <div style={{ maxWidth: 860, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 24 }}>
          {/* Community / Local Desktop Tier */}
          <div className="landing-card" style={{ border: '2px solid #2563EB', position: 'relative' }}>
            <div
              style={{
                position: 'absolute',
                top: -12,
                right: 20,
                background: '#2563EB',
                color: '#FFFFFF',
                fontSize: 11,
                fontWeight: 700,
                padding: '3px 10px',
                borderRadius: 9999,
                letterSpacing: '0.04em',
              }}
            >
              CURRENT RELEASE
            </div>
            <h3 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A', marginBottom: 4 }}>Local Desktop Edition</h3>
            <p style={{ fontSize: 13, color: '#64748B', marginBottom: 20 }}>Complete local privacy on Windows & macOS</p>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#0F172A', marginBottom: 20 }}>
              Free <span style={{ fontSize: 14, fontWeight: 500, color: '#64748B' }}>/ Community Preview</span>
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 28px 0', display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13, color: '#334155' }}>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#2563EB" /> Unlimited Local Documents
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#2563EB" /> Local GGUF LLM Generation
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#2563EB" /> Multi-RAG AI Agent Workspace
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#2563EB" /> Strict Grounding & Citation Validation
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#2563EB" /> Full Account Data Isolation
              </li>
            </ul>
            <button onClick={onGetStarted} className="btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
              <span>Launch Desktop App</span>
              <ArrowRight size={15} />
            </button>
          </div>

          {/* Enterprise / Team Edition (Coming Soon) */}
          <div className="landing-card" style={{ background: '#F8FAFC' }}>
            <h3 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A', marginBottom: 4 }}>Enterprise & Team</h3>
            <p style={{ fontSize: 13, color: '#64748B', marginBottom: 20 }}>Centralized team collaboration & compliance</p>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#0F172A', marginBottom: 20 }}>
              Coming Soon
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 28px 0', display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13, color: '#64748B' }}>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#94A3B8" /> Shared Team Knowledge Artifacts
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#94A3B8" /> Role-Based Access Controls
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#94A3B8" /> Centralized Vector Repositories
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#94A3B8" /> Automated Benchmark Pipelines
              </li>
              <li style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={16} color="#94A3B8" /> Dedicated Priority Support
              </li>
            </ul>
            <button
              disabled
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '10px 16px',
                borderRadius: 10,
                background: '#E2E8F0',
                color: '#64748B',
                border: 'none',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'not-allowed',
              }}
            >
              Plans will be announced soon
            </button>
          </div>
        </div>
      </section>

      {/* ================================================================
          FOOTER
         ================================================================ */}
      <footer
        style={{
          borderTop: '1px solid rgba(15, 23, 42, 0.08)',
          background: '#FFFFFF',
          padding: '40px 48px 32px',
          marginTop: 'auto',
        }}
      >
        <div
          style={{
            maxWidth: 1120,
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 20,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src={raggerBoxLogo} alt="Ragger" style={{ width: 28, height: 28, borderRadius: 8 }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>Ragger.ai</span>
            <span style={{ fontSize: 12, color: '#94A3B8' }}>— Turn Your Data Into Intelligence</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 24, fontSize: 13, color: '#64748B' }}>
            <span onClick={() => scrollToSection('product')} style={{ cursor: 'pointer' }}>Product</span>
            <span onClick={() => scrollToSection('solutions')} style={{ cursor: 'pointer' }}>Solutions</span>
            <span onClick={() => scrollToSection('security')} style={{ cursor: 'pointer' }}>Security</span>
            <span onClick={() => scrollToSection('pricing')} style={{ cursor: 'pointer' }}>Pricing</span>
          </div>
        </div>

        <div style={{ maxWidth: 1120, margin: '24px auto 0', paddingTop: 20, borderTop: '1px solid rgba(15, 23, 42, 0.04)', textAlign: 'center', fontSize: 12, color: '#94A3B8' }}>
          &copy; {new Date().getFullYear()} Ragger.ai. All rights reserved. Local & Private RAG System.
        </div>
      </footer>
    </div>
  );
};

