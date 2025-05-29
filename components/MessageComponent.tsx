import React, { memo, useState } from 'react';
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChartLine, Copy, Check, Clock, Zap } from "lucide-react";
import FilePreview from "@/components/FilePreview";
import { ChartRenderer } from "@/components/ChartRenderer";
import { Message } from '@/types/chat'; 

interface MessageComponentProps {
  message: Message;
}

// Format special backend message patterns for chat
const formatSpecialChatMessage = (text: string): React.ReactNode | null => {
  // Successfully navigated to ... The page title is ...
  const navigationMatch = text.match(/Successfully navigated to (.*?)\. The page title is: (.*?)\.?$/);
  if (navigationMatch) {
    return (
      <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-lg p-3 my-2">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
          <span className="font-medium text-green-800 dark:text-green-300 text-sm">Navigation Success</span>
        </div>
        <div className="space-y-1 text-sm">
          <div>
            <span className="text-gray-600 dark:text-gray-400">URL: </span>
            <span className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded break-all">{navigationMatch[1]}</span>
          </div>
          <div>
            <span className="text-gray-600 dark:text-gray-400">Title: </span>
            <span className="font-medium">{navigationMatch[2]}</span>
          </div>
        </div>
      </div>
    );
  }

  // Action completed successfully (more specific patterns)
  if (text.match(/Browser initialization completed successfully/i)) {
    return (
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 my-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
          <span className="font-medium text-blue-800 dark:text-blue-300 text-sm">Action Completed</span>
        </div>
        <div className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          Browser initialization
        </div>
      </div>
    );
  }

  // Simple "Action completed" message
  if (text.trim().toLowerCase() === "action completed") {
    return (
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 my-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
          <span className="font-medium text-blue-800 dark:text-blue-300 text-sm">Action Completed</span>
        </div>
        <div className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          Task execution finished successfully
        </div>
      </div>
    );
  }

  // Generic action completed
  const actionMatch = text.match(/(.*?)\s+(completed successfully)/i);
  if (actionMatch && actionMatch[1].trim().length > 0) {
    return (
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 my-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
          <span className="font-medium text-blue-800 dark:text-blue-300 text-sm">Action Completed</span>
        </div>
        <div className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          {actionMatch[1]}
        </div>
      </div>
    );
  }


  return null;
};

const formatText = (text: string): React.ReactNode => {
  // Check for special message patterns first
  const specialFormat = formatSpecialChatMessage(text);
  if (specialFormat) {
    return specialFormat;
  }

  const lines = text.split('\n');
  
  return (
    <>
      {lines.map((line, idx) => {
        // Handle headers (# Header, ## Subheader)
        if (line.startsWith('# ')) {
          return <h1 key={idx} className="text-xl font-medium my-2">{line.substring(2)}</h1>;
        }
        if (line.startsWith('## ')) {
          return <h2 key={idx} className="text-lg font-medium my-2">{line.substring(3)}</h2>;
        }
        
        // Handle bullet points (* Item or - Item)
        if (line.startsWith('* ') || line.startsWith('- ')) {
          return (
            <div key={idx} className="ml-2 flex items-start my-1">
              <span className="mr-2 pt-0.5">•</span>
              <span dangerouslySetInnerHTML={{ __html: formatSpecialText(line.substring(2)) }} />
            </div>
          );
        }
        
        // Handle empty lines
        if (!line.trim()) {
          return <div key={idx} className="h-2"></div>;
        }
        
        // Regular text
        return (
          <p key={idx} className="my-1.5 leading-relaxed" 
            dangerouslySetInnerHTML={{ __html: formatSpecialText(line) }} 
          />
        );
      })}
    </>
  );
};

const formatSpecialText = (text: string): string => {
  // Bold formatting
  let result = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // Dollar amount formatting
  result = result.replace(/(\$\d{1,3}(,\d{3})*(\.\d+)?)/g, '<strong>$1</strong>');
  
  // Percentage formatting
  result = result
    .replace(/\(([+]\d+\.?\d*%)\)/g, '<span style="color: #16a34a;">($1)</span>')
    .replace(/\(([-]\d+\.?\d*%)\)/g, '<span style="color: #dc2626;">($1)</span>');
    
  return result;
};

const MessageComponentBase: React.FC<MessageComponentProps> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  
  const hasText = (content: any): content is { text: string } => {
    return 'text' in content && typeof content.text === 'string';
  };

  const textContent = message.content.find(hasText);
  if (!textContent) {
    return null;
  }
  
  const handleCopy = () => {
    if (!textContent) return;
    navigator.clipboard.writeText(textContent.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-start gap-3 my-4 group">
      {message.role === "assistant" && (
        <Avatar className="w-8 h-8">
          <AvatarImage src="/bedrock-logo.png" alt="AI Assistant Avatar" />
          <AvatarFallback>AI</AvatarFallback>
        </Avatar>
      )}
      <div
        className={`flex flex-col max-w-[85%] ${
          message.role === "user" ? "ml-auto" : ""
        } ${message.role === "user" ? "items-end" : "items-start"}`}
      >

        {message.timestamp && (
          <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mb-1">
            <Clock className="w-3 h-3" />
            {new Date(message.timestamp).toLocaleTimeString([], { 
              hour: '2-digit', 
              minute: '2-digit', 
              second: '2-digit',
              hour12: false 
            })}
          </div>
        )}
        
        <div className="relative">
          <div
            className={`p-4 text-base leading-relaxed shadow-sm ${
              message.role === "user"
                ? "bg-primary text-white rounded-lg rounded-tr-sm"
                : "bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg rounded-tl-sm hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors duration-200"
            }`}
          >
          {message.role === "assistant" ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                {message.visualization && (
                  <Badge variant="secondary" className="inline-flex px-2 py-1 mb-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                    <ChartLine className="w-3.5 h-3.5 mr-1" /> Chart
                  </Badge>
                )}
                {message.technical_details?.processing_time_sec && (
                  <Badge variant="outline" className="inline-flex px-2 py-0.5 border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800 text-blue-600 dark:text-blue-400 rounded">
                    <Zap className="w-3.5 h-3.5 mr-1" /> {message.technical_details.processing_time_sec}s
                  </Badge>
                )}
              </div>
              <div className="markdown-content">
                {formatText(textContent.text)}
              </div>
              
              {message.visualization && (
                <div className="mt-4">
                  <ChartRenderer 
                    chartType={message.visualization.chartType}
                    chartData={message.visualization.chartData}
                    chartTitle={message.visualization.chartTitle || "Financial Chart"}
                  />
                </div>
              )}
            </div>
          ) : (
            <span className="font-medium">{textContent.text}</span>
          )}
          </div>
          {/* Message actions */}
          {message.role === "assistant" && (
            <div className="absolute -bottom-2 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button size="icon" variant="ghost" className="h-6 w-6 bg-white dark:bg-gray-700 rounded-full shadow-sm" onClick={handleCopy}>
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              </Button>
            </div>
          )}
        </div>
        {message.file && (
          <div className="mt-2">
            <FilePreview file={message.file} size="small" />
          </div>
        )}
      </div>
    </div>
  );
};

export const MessageComponent = memo(MessageComponentBase, (prevProps, nextProps) => {
  return prevProps.message.id === nextProps.message.id;
});