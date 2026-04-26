"use client";

import { useState } from "react";
import { Terminal, Search, Play, FileCode2, CheckCircle2, AlertCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function Home() {
  const [company, setCompany] = useState("");
  const [targetYear, setTargetYear] = useState(2024);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<any>(null);

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, msg]);
  };

  const handleAnalyze = async () => {
    if (!company) return;
    setLoading(true);
    setResult(null);
    setLogs(["[System] Booting Agentic Pipeline..."]);
    
    // Simulate real-time logs before the backend actually responds
    // In a real production environment we would use SSE/WebSockets
    setTimeout(() => addLog(`[Researcher] Target: ${company}. Searching DDG and Scraping URLs...`), 1000);
    setTimeout(() => addLog(`[Researcher] Found historical contexts and ${targetYear} projections.`), 3000);
    setTimeout(() => addLog(`[Generator] Generating PxQ revenue model baseline...`), 6000);
    setTimeout(() => addLog(`[Evaluator] Validating 2023 Ground Truth against generated logic...`), 9000);
    setTimeout(() => addLog(`[Evaluator] Computing Loss Function...`), 12000);

    try {
      const response = await fetch("https://contest-beta.vercel.app/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_name: company, target_year: targetYear, validation_year: 2023 }),
      });
      const data = await response.json();
      
      if (data.status === "success") {
        addLog(`[Tech Evaluator] Finalizing Output formatting...`);
        setResult(data.data);
      } else {
        addLog(`[Error] Analysis failed: ${data.detail}`);
      }
    } catch (err) {
      addLog(`[Error] Network request failed. Backend may not be running.`);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#0d1117] text-[#c9d1d9] p-8 font-mono">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Left Panel: Inputs and Terminal */}
        <div className="space-y-6">
          <div className="flex items-center space-x-3 mb-8">
            <div className="w-10 h-10 bg-[#238636] rounded-xl flex items-center justify-center">
              <FileCode2 className="text-white w-6 h-6" />
            </div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Octo-Fin Agent</h1>
          </div>

          <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center">
              <Search className="w-5 h-5 mr-2 text-[#58a6ff]" /> Target Configuration
            </h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#8b949e] mb-1">Company Name</label>
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="e.g. SK하이닉스 or 한미반도체"
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-4 py-2 text-white focus:outline-none focus:border-[#58a6ff] focus:ring-1 focus:ring-[#58a6ff]"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-[#8b949e] mb-1">Target Year</label>
                <input
                  type="number"
                  value={targetYear}
                  onChange={(e) => setTargetYear(Number(e.target.value))}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-4 py-2 text-white focus:outline-none focus:border-[#58a6ff] focus:ring-1 focus:ring-[#58a6ff]"
                />
              </div>

              <button
                onClick={handleAnalyze}
                disabled={loading || !company}
                className="w-full mt-4 bg-[#238636] hover:bg-[#2ea043] disabled:opacity-50 text-white font-semibold py-2 px-4 rounded-md flex items-center justify-center transition-colors"
              >
                {loading ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                  >
                    <Play className="w-5 h-5" />
                  </motion.div>
                ) : (
                  <>Execute Pipeline <Play className="w-4 h-4 ml-2" /></>
                )}
              </button>
            </div>
          </div>

          <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden shadow-xl">
            <div className="bg-[#21262d] border-b border-[#30363d] px-4 py-2 flex items-center">
              <Terminal className="w-4 h-4 text-[#8b949e] mr-2" />
              <span className="text-sm font-medium text-[#8b949e]">Agent Action Terminal</span>
            </div>
            <div className="p-4 h-64 overflow-y-auto font-mono text-sm space-y-2">
              <AnimatePresence>
                {logs.map((log, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`flex ${log.includes('[Error]') ? 'text-[#f85149]' : log.includes('Evaluator') ? 'text-[#a5d6ff]' : 'text-[#7ee787]'}`}
                  >
                    <span className="mr-2 text-[#8b949e]">{`>`}</span>
                    <span>{log}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
              {loading && (
                <motion.div
                  animate={{ opacity: [1, 0.5, 1] }}
                  transition={{ repeat: Infinity, duration: 1.5 }}
                  className="w-2 h-4 bg-[#7ee787] inline-block ml-4"
                />
              )}
            </div>
          </div>
        </div>

        {/* Right Panel: Code-Block Style Output */}
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl shadow-xl h-full flex flex-col overflow-hidden">
           <div className="bg-[#21262d] border-b border-[#30363d] px-4 py-2 flex items-center justify-between">
              <div className="flex space-x-2">
                <div className="w-3 h-3 rounded-full bg-[#f85149]"></div>
                <div className="w-3 h-3 rounded-full bg-[#d29922]"></div>
                <div className="w-3 h-3 rounded-full bg-[#2ea043]"></div>
              </div>
              <span className="text-sm font-medium text-[#8b949e]">octo-fin-output.json</span>
           </div>
           
           <div className="p-6 overflow-y-auto flex-1 text-sm bg-[#0d1117] text-[#c9d1d9] leading-relaxed relative">
              {result ? (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <div className="mb-6 pb-4 border-b border-[#30363d]">
                    <h3 className="text-xl font-bold text-white mb-2 flex items-center">
                      <CheckCircle2 className="w-5 h-5 text-[#238636] mr-2" />
                      Analysis Complete
                    </h3>
                    <p className="text-[#8b949e]">{result.executive_summary}</p>
                  </div>
                  
                  <div className="space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                       <div className="bg-[#21262d] border border-[#30363d] rounded-lg p-4">
                         <p className="text-[#8b949e] text-xs uppercase tracking-wider mb-1">Estimated Revenue</p>
                         <p className="text-2xl font-bold text-[#7ee787]">{result.financial_data?.estimated_revenue_krw || "N/A"} KRW</p>
                       </div>
                       <div className="bg-[#21262d] border border-[#30363d] rounded-lg p-4">
                         <p className="text-[#8b949e] text-xs uppercase tracking-wider mb-1">Operating Profit</p>
                         <p className="text-2xl font-bold text-[#58a6ff]">{result.financial_data?.estimated_op_krw || "N/A"} KRW</p>
                       </div>
                    </div>

                    <div>
                      <h4 className="text-white font-semibold mb-2 border-b border-[#30363d] pb-1">Key Drivers (P & Q Logic)</h4>
                      <ul className="list-disc list-inside text-[#c9d1d9] space-y-1">
                        {result.financial_data?.key_drivers?.map((driver: string, idx: number) => (
                          <li key={idx}>{driver}</li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <h4 className="text-white font-semibold mb-2 border-b border-[#30363d] pb-1">Citations & Sources</h4>
                      <div className="space-y-2">
                        {result.citations?.map((cite: any, idx: number) => (
                          <a key={idx} href={cite.url} target="_blank" rel="noopener noreferrer" className="block bg-[#161b22] border border-[#30363d] p-3 rounded hover:border-[#58a6ff] transition-colors">
                            <span className="text-[#a5d6ff] font-medium block">[{cite.id}] {cite.text}</span>
                            <span className="text-xs text-[#8b949e] truncate block mt-1">{cite.url}</span>
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                </motion.div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-[#8b949e] opacity-50">
                   <FileCode2 className="w-16 h-16 mb-4" />
                   <p>Awaiting execution...</p>
                </div>
              )}
           </div>
        </div>

      </div>
    </div>
  );
}
