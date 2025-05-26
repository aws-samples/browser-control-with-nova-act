import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge"; // 올바른 Badge 컴포넌트 import
import { ChartColumnBig, Brain, Wrench, BarChart, Settings, CheckCircle, User, RefreshCw, Globe, Cog, Clock, Zap } from "lucide-react";
import type { AnalyzeAPIResponse } from '@/types/chat';
import useThoughtProcess from '@/hooks/useThoughtProcess';
import { useAutoScroll } from '@/hooks/useAutoScroll';

interface ThoughtProcessProps {
  queryDetails: AnalyzeAPIResponse[];
  currentQueryIndex: number;
  userInput: string;
  sessionId?: string;
}

const ThoughtProcess: React.FC<ThoughtProcessProps> = React.memo(({ 
  queryDetails, 
  sessionId
}) => {
  const { thoughts, connected, error, isComplete, screenshots } = useThoughtProcess(sessionId);
  const thoughtsEndRef = useAutoScroll([thoughts, connected, error]);
  
  const ExpandableUrl = ({ url }) => {
    const [expanded, setExpanded] = useState(false);
    
    const displayUrl = expanded 
      ? url 
      : url.length > 50 ? `${url.substring(0, 47)}...` : url;
    
    return (
      <div className="mt-1 flex flex-col w-full">
        <div 
          className="bg-gray-100 dark:bg-gray-800 text-xs py-1.5 px-2 rounded border"
        >
          <div className="flex justify-between items-start">
            <span className="font-medium mr-2 flex-shrink-0">URL:</span>
            <div className="flex-grow">
              <div className={`${expanded ? "whitespace-pre-wrap break-all" : "text-ellipsis whitespace-nowrap overflow-hidden"}`}>
                {displayUrl}
              </div>
            </div>
            <button 
              className="ml-2 text-blue-500 hover:text-blue-700 flex-shrink-0"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Collapse" : "Expand"}
            </button>
          </div>
          {expanded && (
            <div className="mt-2 pl-2 text-xs text-gray-500 flex">
              <button 
                className="text-blue-500 hover:text-blue-700"
                onClick={() => {
                  navigator.clipboard.writeText(url);
                }}
              >
                Copy URL
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };  
  
  const nodeColorMap: Record<string, {bg: string, icon: React.ReactNode, border: string}> = {
    "Agent": { 
      bg: "bg-cyan-50/40 dark:bg-cyan-900/20", 
      border: "border-cyan-200 dark:border-cyan-800",
      icon: <Brain className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
    },
    "Browser": { 
      bg: "bg-green-50/40 dark:bg-green-900/20", 
      border: "border-green-200 dark:border-green-800",
      icon: <Globe className="h-5 w-5 text-green-600 dark:text-green-400" />
    },
    "NovaAct": { 
      bg: "bg-purple-50/40 dark:bg-purple-900/20", 
      border: "border-purple-200 dark:border-purple-800",
      icon: <Wrench className="h-5 w-5 text-purple-600 dark:text-purple-400" />
    },
    "Others": { 
      bg: "bg-orange-50/40 dark:bg-orange-900/20", 
      border: "border-orange-200 dark:border-orange-800",
      icon: <Cog className="h-5 w-5 text-orange-600 dark:text-orange-400" />
    },
    "User": { 
      bg: "bg-blue-50/40 dark:bg-blue-900/20", 
      border: "border-blue-200 dark:border-blue-800",
      icon: <User className="h-5 w-5 text-blue-600 dark:text-blue-400" />
    },
    "Answer": { 
      bg: "bg-emerald-50/40 dark:bg-emerald-900/20", 
      border: "border-emerald-200 dark:border-emerald-800",
      icon: <CheckCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
    },
    "User Control": { 
      bg: "bg-indigo-50/40 dark:bg-indigo-900/20", 
      border: "border-indigo-200 dark:border-indigo-800",
      icon: <User className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
    },
    "default": { 
      bg: "bg-secondary/30 dark:bg-gray-800/60", 
      border: "border-secondary/50 dark:border-gray-700",
      icon: <Brain className="h-5 w-5 text-primary dark:text-primary" />
    }
  };
  

  return (
    <Card className="w-full lg:w-2/5 xl:w-1/3 md:w-2/5 flex flex-col h-full overflow-hidden shadow-sm border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <CardHeader className="py-3 px-5 border-b border-gray-100 dark:border-gray-800 shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Thought Process</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7 text-gray-500" title="Refresh">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto min-h-0 p-4">
        {(sessionId) && (
          <div className="mb-3 px-2 py-1 rounded text-xs text-gray-500 dark:text-gray-400">
            {sessionId && <div>Session: {sessionId}</div>}
            <div>Status: {connected ? 'Connected' : 'Disconnected'}</div>
            {error && <div className="text-red-500">Error: {error}</div>}
          </div>
        )}
        {sessionId && thoughts.length > 0 ? (
          <div className="flex flex-col">
            <div className="flex items-center justify-between mb-4 bg-gradient-to-r from-gray-50 to-transparent dark:from-gray-800/50 dark:to-transparent py-1 px-2 rounded-md">
              <h3 className="font-medium text-sm text-gray-700 dark:text-gray-300">Execution Path</h3>
            </div>
            
            {thoughts.map((thought, index) => {
              let nodeName = thought.node;
              if (nodeName === "Router" || nodeName === "LLM Router" || nodeName === "Data Analyzer") {
                nodeName = "Reasoning";
              }            
              if (thought.type === "question") {
                nodeName = "User";
              }
              if (!nodeName) {
                nodeName = thought.from_router ? 'Reasoning' : 
                          thought.category === 'tool' ? 'Tool Executor' :
                          thought.category === 'result' ? 'Answer' : 'default';
              }

              if (thought.category === 'result') {
                nodeName = 'Answer';
              }

              // User Control 카테고리는 별도 노드로 표시
              if (thought.category === 'user_control') {
                nodeName = 'User Control';
              }

              const nodeStyle = nodeColorMap[nodeName] || nodeColorMap.default;
              
              const categoryStyle = thought.category === 'error' ? 
                { bg: "bg-red-50/40 dark:bg-red-950/30", border: "border-red-200 dark:border-red-900" } : {};
              
              if (nodeName === 'User') {
                categoryStyle.bg = "bg-blue-50/50 dark:bg-blue-950/30";
                categoryStyle.border = "border-blue-200 dark:border-blue-900";
              }
              
              const isAnswerNode = nodeName === 'Answer';
              const isVisualizationNode = nodeName === 'Visualization' && thought.category === 'visualization_data';
              const isUserControlNode = nodeName === 'User Control' && thought.category === 'user_control';
              
              // Show separator after User Control completion (success or failure) 
              const isUserControlComplete = isUserControlNode && 
                (thought.content.includes('✅') || thought.content.includes('❌'));
              
              // Show separator BEFORE User Control starts (when previous node is not User Control)
              const isUserControlStart = isUserControlNode && 
                thought.content.includes('Starting') && 
                index > 0 && 
                thoughts[index - 1].category !== 'user_control';
              
              const showSeparatorBefore = isUserControlStart;
              const showSeparatorAfter = (isAnswerNode || isVisualizationNode || isUserControlComplete) && 
                index < thoughts.length - 1 && 
                thoughts[index + 1].node !== 'Answer' && 
                thoughts[index + 1].node !== 'Visualization' && 
                thoughts[index + 1].node !== 'User Control' &&
                thoughts[index + 1].category !== 'result' && 
                thoughts[index + 1].category !== 'visualization_data' &&
                thoughts[index + 1].category !== 'user_control';
              
              // Modified content to remove URL prefix if there's a screenshot
              let displayContent = thought.content;
              if (thought.technical_details?.screenshotId && thought.technical_details?.url) {
                displayContent = displayContent.replace(`Browser screenshot from: ${thought.technical_details.url}`, 'Browser screenshot');
                displayContent = displayContent.replace(`Navigation result for: ${thought.technical_details.url}`, 'Navigation result');
              }
              
              return (
                <React.Fragment key={index}>
                  {/* Show separator BEFORE User Control starts */}
                  {showSeparatorBefore && (
                    <div className="my-6 py-2 px-3 bg-gradient-to-r from-indigo-50/50 to-transparent dark:from-indigo-900/30 dark:to-transparent rounded-md flex items-center gap-2 animate-fade-in-up hover:from-indigo-100 hover:to-transparent dark:hover:from-indigo-800/30 transition-all duration-300">
                      <div className="p-1.5 rounded-full bg-indigo-50 dark:bg-indigo-900/50 animate-pulse-glow">
                        <RefreshCw className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-400" />
                      </div>
                      <span className="text-sm font-medium text-indigo-600 dark:text-indigo-400">User Control</span>
                    </div>
                  )}

                  <Card 
                    className={`mb-4 p-3 border thought-node ${nodeStyle.bg} ${nodeStyle.border}`}
                  >
                    <div className="flex items-start gap-3">
                      <div>
                        {nodeStyle.icon}
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between items-center mb-1">
                          <div className="flex items-center gap-2">
                            <h4 className="font-medium text-sm text-gray-800 dark:text-gray-200">
                              {nodeName}
                            </h4>
                            {thought.timestamp && (
                              <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center">
                                <Clock className="w-3 h-3 mr-1" />
                                {new Date(thought.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                          {thought.technical_details?.processing_time_sec && (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs border border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800 text-blue-600 dark:text-blue-400 rounded">
                              <Zap className="w-3 h-3 mr-1" /> {thought.technical_details.processing_time_sec}s
                            </span>
                          )}
                            {thought.category && thought.category !== 'user_input' && (
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                thought.category === 'user_control' 
                                  ? 'text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900' 
                                  : 'text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800'
                              }`}>
                                {thought.category === 'user_control' ? 'User Control' : thought.category}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                          {displayContent}
                          
                          {/* Screenshot rendering with ExpandableUrl */}
                          {thought.technical_details?.screenshotId && 
                           screenshots[thought.technical_details.screenshotId] && (
                            <div className="mt-3 border rounded overflow-hidden flex flex-col">
                              <img 
                                src={`data:image/jpeg;base64,${screenshots[thought.technical_details.screenshotId]}`} 
                                alt="Browser screenshot" 
                                className="w-full h-auto"
                              />
                              {thought.technical_details.url && (
                                <ExpandableUrl url={thought.technical_details.url} />
                              )}
                            </div>
                          )}
                          
                          {/* Technical details */}
                          {thought.technical_details && !thought.technical_details.screenshotId && (
                            <details className="mt-2">
                              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                                Technical details
                              </summary>
                              <div className="mt-2 text-xs bg-gray-50 dark:bg-gray-800 p-2 rounded whitespace-pre-wrap">
                                {JSON.stringify(
                                  {...thought.technical_details, 
                                    screenshot: thought.technical_details.screenshot ? 
                                      '{Screenshot data omitted}' : 
                                      undefined
                                  }, 
                                  null, 2
                                )}
                              </div>
                            </details>
                          )}
                        </div>
                      </div>
                    </div>
                  </Card>              
                
                {showSeparatorAfter && (
                  <div className="my-6 py-2 px-3 bg-gradient-to-r from-blue-50/50 to-transparent dark:from-blue-900/30 dark:to-transparent rounded-md flex items-center gap-2 animate-fade-in-up hover:from-blue-100 hover:to-transparent dark:hover:from-blue-800/30 transition-all duration-300">
                    <div className="p-1.5 rounded-full bg-blue-50 dark:bg-blue-900/50 animate-pulse-glow">
                      <RefreshCw className="h-3.5 w-3.5 text-blue-500 dark:text-blue-400" />
                    </div>
                    <span className="text-sm font-medium text-blue-600 dark:text-blue-400">Execution Path</span>
                  </div>
                )}
              </React.Fragment>
              );
            })}
            
            <div ref={thoughtsEndRef} className="h-4" />
          </div>
        ) : queryDetails.length > 0 ? (
          <div className="flex flex-col">
            {queryDetails.map((detail, index) => (
              <Card key={index} className="mb-4 p-4">
              <CardTitle className="text-base mb-3">Query {index + 1}</CardTitle>
                <div className="space-y-3">
                  <div>
                    <h3 className="font-medium mb-1 text-sm">Question:</h3>
                    <p className="text-sm text-gray-700 dark:text-gray-300">{detail.originalQuestion}</p>
                  </div>
                  <div>
                    <h3 className="font-medium mb-1 text-sm">SQL Query:</h3>
                    <pre className="bg-gray-50 dark:bg-gray-800 p-2 rounded text-sm overflow-x-auto">{detail.query}</pre>
                  </div>
                  <div>
                    <h3 className="font-medium mb-1 text-sm">Explanation:</h3>
                    <p className="text-sm text-gray-700 dark:text-gray-300">{detail.explanation}</p>
                  </div>
                  <div>
                    <h3 className="font-medium mb-1 text-sm">Results:</h3>
                    <pre className="bg-gray-50 dark:bg-gray-800 p-2 rounded text-sm overflow-x-auto">
                      {JSON.stringify(detail.result, null, 2)}
                    </pre>
                  </div>
                </div>
              </Card>
            ))}
            <div ref={thoughtsEndRef} className="h-4" />
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-4">
            <div className="flex flex-col items-center justify-center gap-4 max-w-xs">
              <ChartColumnBig className="w-8 h-8 text-gray-300 dark:text-gray-600" />
              <div className="space-y-2">
                <CardTitle className="text-lg font-medium">No Thought Process Yet</CardTitle>
                <CardDescription className="text-base text-gray-500 dark:text-gray-400">
                  When you ask a question, the reasoning process will appear here.
                </CardDescription>
              </div>
              <div className="mt-4 text-sm text-gray-400 dark:text-gray-500">
                Waiting for your first question...
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
});

export default ThoughtProcess;