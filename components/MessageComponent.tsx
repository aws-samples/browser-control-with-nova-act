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

const formatText = (text: string): React.ReactNode => {
  const cleanedText = text.replace(/\n\nProcessing time: \d+\.\d+s/, '');
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
            className={`p-4 text-base shadow-soft ${
              message.role === "user"
                ? "bg-primary text-white rounded-lg rounded-tr-sm"
                : "bg-gray-50 dark:bg-gray-800/90 border border-gray-200 dark:border-gray-700 rounded-lg rounded-tl-sm hover-lift"
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