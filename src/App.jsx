import React, { useEffect, useRef, useState } from 'react';
import { 
  Brain, 
  Search, 
  Database, 
  Activity, 
  FileText, 
  GitFork, 
  ChevronDown, 
  Terminal, 
  Send, 
  RefreshCw,
  FolderOpen,
  ArrowRight,
  Sparkles
} from 'lucide-react';
import CanvasScroll from './CanvasScroll';

function App() {
  const scrollContainerRef = useRef(null);
  
  // Interactive application states
  const [scrollProgress, setScrollProgress] = useState(0);
  const [serverOnline, setServerOnline] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [chatAnswer, setChatAnswer] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);

  // Live data states
  const [stats, setStats] = useState({
    total_notes: 124,
    total_chunks: 1140,
    total_categories: 8,
    total_links: 342
  });
  const [notes, setNotes] = useState([
    { name: 'zettelkasten_intro.md', category: 'Projects', date: 'Just now' },
    { name: 'para_framework.md', category: 'Areas', date: '10 mins ago' },
    { name: 'daily_brief.md', category: 'Archives', date: '1 hour ago' },
    { name: 'embedding_vectors.md', category: 'Resources', date: '3 hours ago' },
  ]);

  // Ping API and fetch live metrics
  useEffect(() => {
    const fetchData = async () => {
      try {
        const overviewRes = await fetch('/api/overview');
        if (overviewRes.ok) {
          const overviewData = await overviewRes.json();
          setStats({
            total_notes: overviewData.total_notes || 0,
            total_chunks: overviewData.total_chunks || 0,
            total_categories: overviewData.total_categories || 0,
            total_links: overviewData.total_links || 0
          });
          setServerOnline(true);
        }

        const notesRes = await fetch('/api/notes');
        if (notesRes.ok) {
          const notesData = await notesRes.json();
          // Map backend notes response structure
          if (Array.isArray(notesData)) {
            const formatted = notesData.slice(0, 5).map(note => ({
              name: note.filepath || note.name || 'untitled.md',
              category: note.category || 'Raw',
              date: note.updated_at || 'Synced'
            }));
            setNotes(formatted);
          }
        }
      } catch (err) {
        console.log("Vite App: Local server offline. Using premium mock vault data.");
        setServerOnline(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 10000); // Poll metrics
    return () => clearInterval(interval);
  }, []);

  // Handle interactive LLM chat query
  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setChatLoading(true);
    setChatAnswer(null);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery })
      });

      if (response.ok) {
        const data = await response.json();
        setChatAnswer(data.response || data.answer || "No response received.");
      } else {
        setChatAnswer("Error communicating with local LLM agent.");
      }
    } catch (err) {
      // Mock response if offline
      setTimeout(() => {
        setChatAnswer(`[LOCAL FALLBACK]: The query "${searchQuery}" was routed. Synthesizing semantic connections...

Your Second Brain contains detailed archives on Zettelkasten and PARA frameworks. To build a robust mind graph, connect these sections using the [[Note Name]] wiki-link syntax in your editor. Maintain metadata tags to help the Researcher organize your local context vector databases.`);
      }, 800);
    } finally {
      setChatLoading(false);
    }
  };

  // Helper function to map scroll sections opacity and transforms
  const getSectionStyles = (start, end) => {
    // Fades in slightly before start, fades out slightly after end
    const transitionWidth = 0.08;
    let opacity = 0;
    let translateY = 40;

    if (scrollProgress >= start && scrollProgress <= end) {
      opacity = 1;
      translateY = 0;
      
      // Handle entry crossfade (skip if start is 0)
      if (start > 0 && scrollProgress < start + transitionWidth) {
        const factor = (scrollProgress - start) / transitionWidth;
        opacity = factor;
        translateY = 40 * (1 - factor);
      }
      // Handle exit crossfade (skip if end is 1.0)
      else if (end < 1.0 && scrollProgress > end - transitionWidth) {
        const factor = (end - scrollProgress) / transitionWidth;
        opacity = factor;
        translateY = -40 * (1 - factor);
      }
    } else if (scrollProgress < start) {
      opacity = 0;
      translateY = 40;
    } else {
      opacity = 0;
      translateY = -40;
    }

    return {
      opacity,
      transform: `translateY(${translateY}px)`,
      pointerEvents: opacity > 0.1 ? 'auto' : 'none',
      transition: 'opacity 0.2s ease-out, transform 0.2s ease-out'
    };
  };

  return (
    <div ref={scrollContainerRef} className="relative w-full h-[320vh] bg-background">
      
      {/* Sticky Canvas Viewport */}
      <div className="sticky top-0 w-full h-screen overflow-hidden">
        <CanvasScroll 
          scrollContainerRef={scrollContainerRef} 
          onProgressUpdate={setScrollProgress} 
        />
        
        {/* Fixed Modern Navbar */}
        <header className="absolute top-0 left-0 w-full z-40 border-b border-white/5 bg-[#020204]/40 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <a href="#" className="flex items-center gap-2.5 font-title text-lg font-bold tracking-wide text-white">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple to-cyan flex items-center justify-center shadow-lg shadow-purple-glow">
                <Brain className="w-4 h-4 text-white" />
              </div>
              AI SECOND BRAIN
            </a>
            
            <div className="flex items-center gap-6">
              {/* Server connection badge */}
              <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-full border border-white/5">
                <span className={`w-2 h-2 rounded-full ${serverOnline ? 'bg-emerald animate-pulse shadow-[0_0_8px_var(--emerald)]' : 'bg-red-500'}`} />
                <span className="text-xs font-medium text-text-muted">
                  {serverOnline ? 'LOCAL CORE ONLINE' : 'STANDALONE MODE'}
                </span>
              </div>
              
              <a 
                href="/dashboard" 
                className="bg-gradient-to-r from-purple to-cyan text-white text-xs font-semibold px-4 py-2 rounded-lg hover:shadow-lg hover:shadow-purple-glow transition-all hover:-translate-y-[1px]"
              >
                Open Dashboard
              </a>
            </div>
          </div>
        </header>

        {/* ─── STAGE 1: CINEMATIC HERO (Progress 0.0 to 0.22) ─── */}
        <div 
          style={getSectionStyles(0, 0.22)}
          className="absolute inset-0 flex flex-col items-center justify-center text-center px-4"
        >
          <div className="glow-spot-purple absolute w-[40rem] h-[40rem] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 -z-10 pulse-glow" />
          
          <span className="text-xs font-bold tracking-[0.3em] text-purple uppercase mb-4 text-glow-purple">
            Quantum Synthesizer
          </span>
          <h1 className="font-title text-5xl md:text-7xl font-extrabold text-white leading-none tracking-tight max-w-4xl">
            SYNAPTIC CORE <br />
            <span className="bg-gradient-to-r from-cyan to-purple bg-clip-text text-transparent">
              DECISION ENGINE
            </span>
          </h1>
          <p className="text-base md:text-lg text-text-muted mt-6 max-w-xl font-light">
            Unlock absolute context synthesis. Scan, connect, and query your knowledge vaults on port 8000.
          </p>
          
          <div 
            onClick={() => {
              if (scrollContainerRef.current) {
                const scrollHeight = scrollContainerRef.current.scrollHeight - window.innerHeight;
                window.scrollTo({ top: scrollHeight * 0.35, behavior: 'smooth' });
              }
            }}
            className="mt-12 flex flex-col items-center gap-2 text-text-muted animate-bounce cursor-pointer hover:text-purple transition-colors"
          >
            <span className="text-xs font-semibold tracking-widest uppercase">Scroll to Index</span>
            <ChevronDown className="w-5 h-5 text-purple" />
          </div>
        </div>

        {/* ─── STAGE 2: METRICS & CONTEXT MAP (Progress 0.18 to 0.58) ─── */}
        <div 
          style={getSectionStyles(0.18, 0.58)}
          className="absolute inset-0 flex items-center justify-center px-6"
        >
          <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Left Column: Live Counters */}
            <div className="flex flex-col justify-center space-y-6">
              <div>
                <span className="text-xs font-bold tracking-widest text-cyan uppercase mb-2 block text-glow-cyan">
                  Vault Infrastructure
                </span>
                <h2 className="font-title text-3xl md:text-4xl font-bold text-white">
                  Real-Time Synthesis
                </h2>
                <p className="text-sm text-text-muted mt-2">
                  Semantic structures indexed, vectorized, and compiled locally.
                </p>
              </div>

              {/* Dynamic stats board */}
              <div className="grid grid-cols-2 gap-4">
                {[
                  { label: 'Indexed Notes', val: stats.total_notes, icon: FileText, color: 'purple' },
                  { label: 'Vector Chunks', val: stats.total_chunks, icon: Database, color: 'cyan' },
                  { label: 'Active Links', val: stats.total_links, icon: GitFork, color: 'purple' },
                  { label: 'Categories', val: stats.total_categories, icon: Activity, color: 'emerald' },
                ].map((item, idx) => (
                  <div key={idx} className="p-4 glass-panel rounded-xl flex flex-col relative overflow-hidden">
                    <div className={`absolute top-0 right-0 w-24 h-24 -mr-6 -mt-6 rounded-full opacity-5 bg-${item.color}`} />
                    <div className="flex items-center gap-2 mb-2">
                      <item.icon className={`w-4 h-4 text-${item.color}`} />
                      <span className="text-xs text-text-muted font-medium">{item.label}</span>
                    </div>
                    <span className="text-3xl font-bold text-white tracking-tight">{item.val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Column: Live Agents Monitor */}
            <div className="flex flex-col justify-center">
              <div className="glass-panel glass-panel-glow-purple p-6 rounded-2xl relative">
                <div className="flex items-center justify-between border-b border-white/5 pb-4 mb-4">
                  <div className="flex items-center gap-2.5">
                    <Activity className="w-5 h-5 text-purple" />
                    <h3 className="font-title font-semibold text-white">Autonomous Agents Status</h3>
                  </div>
                  <span className="text-xs font-mono bg-purple/10 text-purple border border-purple/20 px-2 py-0.5 rounded">
                    SYS-8000
                  </span>
                </div>

                <div className="space-y-4">
                  {[
                    { name: 'The Archivist', task: 'Monitoring Local Workspace directory', status: 'ACTIVE', color: 'text-purple bg-purple/10 border-purple/20' },
                    { name: 'The Researcher', task: 'Chunking markdown & updating vector store', status: 'VECTORIZING', color: 'text-cyan bg-cyan/10 border-cyan/20 animate-pulse' },
                    { name: 'The Task Master', task: 'Compiling checklists into daily brief', status: 'WAITING', color: 'text-text-muted bg-white/5 border-white/5' }
                  ].map((agent, index) => (
                    <div key={index} className="p-3 bg-white/5 border border-white/5 rounded-xl flex items-center justify-between">
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold text-white">{agent.name}</span>
                        <span className="text-xs text-text-muted mt-0.5">{agent.task}</span>
                      </div>
                      <span className={`text-[10px] font-mono font-bold px-2 py-1 rounded border ${agent.color}`}>
                        {agent.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* ─── STAGE 3: INTERACTIVE CORE QUERY (Progress 0.54 to 1.0) ─── */}
        <div 
          style={getSectionStyles(0.54, 1.0)}
          className="absolute inset-0 flex items-center justify-center px-6"
        >
          <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Left: Notes Explorer */}
            <div className="flex flex-col justify-center space-y-4">
              <div>
                <span className="text-xs font-bold tracking-widest text-purple uppercase mb-1.5 block text-glow-purple">
                  Explorer Core
                </span>
                <h2 className="font-title text-3xl font-bold text-white flex items-center gap-2">
                  <FolderOpen className="w-6 h-6 text-purple" />
                  Recent Ingestions
                </h2>
                <p className="text-xs text-text-muted mt-1">
                  Click to open any note inside the main glassmorphic editor interface.
                </p>
              </div>

              <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2">
                {notes.map((note, index) => (
                  <div 
                    key={index}
                    className="p-3.5 glass-panel rounded-xl flex items-center justify-between hover:bg-white/5 transition-all group cursor-pointer border-l-2 hover:border-l-purple"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center">
                        <FileText className="w-4 h-4 text-purple" />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-white group-hover:text-purple transition-colors truncate max-w-[200px]">
                          {note.name.split('/').pop()}
                        </span>
                        <span className="text-[10px] text-text-muted mt-0.5">{note.date}</span>
                      </div>
                    </div>
                    <span className="text-[10px] font-medium bg-white/5 text-text-muted border border-white/5 px-2.5 py-1 rounded-full uppercase">
                      {note.category}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: Agent Console Chat */}
            <div className="flex flex-col justify-center">
              <div className="glass-panel glass-panel-glow-cyan rounded-2xl p-6 flex flex-col h-[380px]">
                <div className="flex items-center gap-2.5 border-b border-white/5 pb-4 mb-4">
                  <Terminal className="w-5 h-5 text-cyan" />
                  <div>
                    <h3 className="font-title font-semibold text-white text-sm">Mind Link Terminal</h3>
                    <span className="text-[10px] text-text-muted">Direct LLM semantic querying</span>
                  </div>
                </div>

                {/* Response area */}
                <div className="flex-1 overflow-y-auto font-mono text-xs text-text-muted bg-black/40 rounded-xl p-4 border border-white/5 mb-4">
                  {chatLoading ? (
                    <div className="flex items-center gap-2 text-cyan">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Synthesizing semantic weights...</span>
                    </div>
                  ) : chatAnswer ? (
                    <div className="space-y-2 whitespace-pre-wrap text-white/95">
                      <div className="flex items-center gap-1.5 text-purple font-semibold">
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>ARCHIVIST INSIGHTS:</span>
                      </div>
                      {chatAnswer}
                    </div>
                  ) : (
                    <div className="text-center py-10">
                      <Terminal className="w-8 h-8 mx-auto text-white/10 mb-2" />
                      <span>Console idle. Query the neural database below to generate insights...</span>
                    </div>
                  )}
                </div>

                {/* Input form */}
                <form onSubmit={handleChatSubmit} className="flex gap-2">
                  <div className="relative flex-1">
                    <input 
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Ask the local core: 'What is PARA?'"
                      className="w-full h-11 bg-white/5 border border-white/10 rounded-xl px-4 text-sm text-white placeholder-text-muted focus:outline-none focus:border-cyan transition-colors pr-10"
                    />
                    <Search className="w-4 h-4 text-text-muted absolute right-3.5 top-3.5" />
                  </div>
                  <button 
                    type="submit"
                    disabled={chatLoading || !searchQuery.trim()}
                    className="h-11 w-11 rounded-xl bg-cyan hover:shadow-lg hover:shadow-cyan-glow text-black font-bold flex items-center justify-center transition-all disabled:opacity-40 disabled:hover:shadow-none"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}

export default App;
