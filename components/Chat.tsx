import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardFooter, CardTitle, CardDescription } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Paperclip, Settings, Moon, Sun, Trash2, Globe, Search, Code } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import FilePreview from "@/components/FilePreview";
import { MessageComponent } from "@/components/MessageComponent";
import type { Message, Model, FileUpload } from '@/types/chat';
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { useTheme } from "next-themes";
import MCPServerSettings from "@/components/MCPServerSettings";

interface ChatProps {
  messages: Message[];
  input: string;
  isLoading: boolean;
  currentUpload: FileUpload | null;
  selectedModel: string;
  selectedRegion: string;
  models: Model[];
  regions: { id: string; name: string }[];
  isThinking: boolean;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  setSelectedModel: (modelId: string) => void;
  setSelectedRegion: (regionId: string) => void;
  setCurrentUpload: (upload: FileUpload | null) => void;
  onReset?: () => void;
}

const ThinkingIndicator: React.FC = () => {
    return (
      <div className="flex flex-col space-y-3 p-4 bg-gradient-to-r from-blue-50 via-gray-50 to-gray-100 dark:from-blue-950/30 dark:via-gray-800/80 dark:to-gray-900 rounded-lg border border-blue-100 dark:border-blue-900/50 shadow-soft animate-expand-in">
        <div className="flex items-center justify-between">
          <div className="text-gray-700 dark:text-gray-200 font-medium flex items-center">
            <div className="relative mr-3">
              <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin"></div>
              <div className="absolute top-1/2 left-1/2 w-2 h-2 bg-primary rounded-full transform -translate-x-1/2 -translate-y-1/2"></div>
            </div>
            <span className="font-semibold">Working on it...</span>
          </div>
        </div>
        
        <div className="space-y-2">
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-3/4 animate-pulse"></div>
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-1/2 animate-pulse"></div>
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-5/6 animate-pulse"></div>
        </div>
      </div>
    );
  };   

const Chat: React.FC<ChatProps> = ({
  messages,
  input,
  isLoading,
  currentUpload,
  selectedModel,
  selectedRegion,
  models,
  regions,
  isThinking,
  fileInputRef,  
  onInputChange,
  onKeyDown,
  onSubmit,
  onFileSelect,
  setSelectedModel,
  setSelectedRegion,
  setCurrentUpload,
  onReset,
}) => {
  // Auto-scroll when messages change or thinking status changes
  const messagesEndRef = useAutoScroll([messages, isLoading, isThinking]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  
  // Function to open MCP settings modal
  const onMCPSettingsOpen = () => setIsSettingsOpen(true);

  return (
    <Card className="w-full lg:w-3/5 xl:w-2/3 md:w-3/5 flex flex-col h-full shadow-sm border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <CardHeader className="py-3 px-5 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            {messages.length > 0 && (
              <>
                <Avatar className="w-8 h-8">
                  <AvatarImage src="/bedrock-logo.png" alt="Web Browser Assistant Avatar" />
                  <AvatarFallback>AI</AvatarFallback>
                </Avatar>
                <div>
                  <CardTitle className="text-base">Assistant</CardTitle>
                  <CardDescription className="text-xs">Powered by Bedrock</CardDescription>
                </div>
              </>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1 hidden"></div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="h-8 text-sm">
                  {regions.find((r) => r.id === selectedRegion)?.name}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {regions.map((region) => (
                  <DropdownMenuItem key={region.id} onSelect={() => setSelectedRegion(region.id)}>
                    {region.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="h-8 text-sm">
                  {models.find((m) => m.id === selectedModel)?.name}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {models.map((model) => (
                  <DropdownMenuItem key={model.id} onSelect={() => setSelectedModel(model.id)}>
                    {model.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            
            <Button
              variant="outline"
              size="sm"
              onClick={onMCPSettingsOpen}
              title="MCP Server Settings"
              className="h-8 text-xs flex gap-1 items-center">
              <Settings className="h-3.5 w-3.5" />
              <span>Tool</span>
            </Button>
            
            {/* Theme button moved from footer to header */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 text-xs flex gap-1 items-center">
                  <div className="relative flex items-center justify-center w-3.5 h-3.5">
                    <Sun className="h-3.5 w-3.5 absolute rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                    <Moon className="h-3.5 w-3.5 absolute rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                  </div>
                  <span>Theme</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setTheme("light")}>
                  Light
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("dark")}>
                  Dark
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("system")}>
                  System
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            
            {/* Clear Chat button moved from footer to header */}
            <Button
              variant="outline"
              size="sm"
              onClick={onReset}
              className="h-8 text-xs flex gap-1 items-center"
              title="Reset Chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Clear Chat</span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto p-5 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full animate-fade-in-up max-w-md mx-auto">
            <div className="relative mb-6 group">
              <div className="absolute -inset-1 bg-gradient-to-r from-primary to-blue-600 rounded-full opacity-75 blur-sm group-hover:opacity-100 transition duration-500 group-hover:duration-200"></div>
              <Avatar className="w-16 h-16 relative">
                <AvatarImage src="/bedrock-logo.png" alt="Web Browser Assistant Avatar" width={64} height={64} className="animate-pulse-subtle" />
              </Avatar>
            </div>
            <h2 className="text-2xl font-medium mb-2 text-gray-900 dark:text-gray-50 tracking-tight heading-font animate-fade-in">Web Browser Assistant</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-10 text-center animate-fade-in delay-100">Navigate the web and interact with websites.</p>
            
            <div className="grid grid-cols-1 gap-5 w-full">
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-100">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-blue-50 dark:bg-blue-900/30">
                  <Globe className="text-blue-500 dark:text-blue-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Web Navigation</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Visit websites, navigate pages, and interact with web content.</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-200">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-green-50 dark:bg-green-900/30">
                  <Search className="text-green-500 dark:text-green-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Web Research</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Find information and extract data from websites.</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-300">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-purple-50 dark:bg-purple-900/30">
                  <Code className="text-purple-500 dark:text-purple-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Web Automation</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Fill forms, click buttons, and automate web tasks.</p>
                </div>
              </div>
            </div>
            
            <div className="mt-10 text-sm text-gray-400 dark:text-gray-500 text-center">
              Tip: Try asking to visit a specific website or perform web tasks.
            </div>
          </div>
        ) : (
          <div className="space-y-4 min-h-full">
            {messages.map((message) => (
              <div key={message.id}>
                <MessageComponent message={message} />
              </div>
            ))}
            {isThinking && (
              <div className="animate-fade-in-up">
                <ThinkingIndicator />
              </div>
            )}
            <div ref={messagesEndRef} className="h-4" />
          </div>
        )}
      </CardContent>

      <CardFooter className="p-4 border-t border-gray-100 dark:border-gray-800">
        <form onSubmit={onSubmit} className="w-full">
          <div className="flex flex-col space-y-2">
            {currentUpload && (
              <FilePreview file={currentUpload} onRemove={() => setCurrentUpload(null)} />
            )}
            <div className="flex items-end space-x-2">
              <div className="flex-1 relative">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-8 w-8 text-gray-500"
                >
                  <Paperclip className="h-5 w-5" />
                </Button>
                <Textarea
                  value={input}
                  onChange={onInputChange}
                  onKeyDown={onKeyDown}
                  placeholder="Ask me to visit websites or help with web tasks..."
                  disabled={isLoading}
                  className="min-h-[48px] h-[48px] resize-none pl-12 py-3 flex items-center rounded-lg border-gray-300 dark:border-gray-700"
                  rows={1}
                />
              </div>
              <Button 
                type="submit" 
                disabled={isLoading || isThinking || (!input.trim() && !currentUpload)} 
                className="h-[48px] btn-hover bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 dark:from-blue-600 dark:to-blue-700 dark:hover:from-blue-700 dark:hover:to-blue-800 text-white px-5 rounded-lg shadow-md hover:shadow-lg transition-all duration-300"
              >
                <Send className="h-4 w-4 mr-1" />
                <span className="hidden sm:inline">Send</span>
              </Button>
            </div>
          </div>
          <div className="flex justify-end mt-2 text-xs text-gray-400 dark:text-gray-500">
            <div className="flex items-center space-x-3">
              <span><kbd className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">Enter</kbd> Send</span>
              <span><kbd className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">Shift+Enter</kbd> New line</span>
            </div>
          </div>
          <input type="file" ref={fileInputRef} className="hidden" onChange={onFileSelect} />
          {/* Theme and Clear Chat buttons removed from here - moved to header */}
        </form>
      </CardFooter>
      
      {/* MCP Settings Modal */}
      <MCPServerSettings 
        isOpen={isSettingsOpen} 
        onClose={() => setIsSettingsOpen(false)} 
      />
    </Card>
  );
};

export default Chat;