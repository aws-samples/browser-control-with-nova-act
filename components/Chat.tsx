import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardFooter, CardTitle, CardDescription } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Paperclip, Settings, Moon, Sun, Trash2, Globe, Search, Code, ChevronDown, Cpu, MapPin } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
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
  isStopping?: boolean;
  isUserControlInProgress?: boolean;
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

interface ThinkingIndicatorProps {
  isStopping?: boolean;
}

const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = ({ isStopping = false }) => {
    return (
      <div className={`flex flex-col space-y-3 p-4 rounded-lg border shadow-soft animate-expand-in ${
        isStopping 
          ? "bg-gradient-to-r from-orange-50 via-yellow-50 to-orange-100 dark:from-orange-950/30 dark:via-yellow-800/80 dark:to-orange-900 border-orange-100 dark:border-orange-900/50"
          : "bg-gradient-to-r from-blue-50 via-gray-50 to-gray-100 dark:from-blue-950/30 dark:via-gray-800/80 dark:to-gray-900 border-blue-100 dark:border-blue-900/50"
      }`}>
        <div className="flex items-center justify-between">
          <div className="text-gray-700 dark:text-gray-200 font-medium flex items-center">
            <div className="relative mr-3">
              <div className={`w-6 h-6 border-2 rounded-full animate-spin ${
                isStopping 
                  ? "border-orange-300 border-t-orange-600 dark:border-orange-700 dark:border-t-orange-400"
                  : "border-primary/30 border-t-primary"
              }`}></div>
              <div className={`absolute top-1/2 left-1/2 w-2 h-2 rounded-full transform -translate-x-1/2 -translate-y-1/2 ${
                isStopping 
                  ? "bg-orange-600 dark:bg-orange-400"
                  : "bg-primary"
              }`}></div>
            </div>
            <span className="font-semibold">
              {isStopping ? "Gracefully stopping agent..." : "Working on it..."}
            </span>
          </div>
        </div>
        
        <div className="space-y-2">
          <div className={`h-2 rounded-full w-3/4 animate-pulse ${
            isStopping 
              ? "bg-orange-200 dark:bg-orange-600"
              : "bg-gray-200 dark:bg-gray-600"
          }`}></div>
          <div className={`h-2 rounded-full w-1/2 animate-pulse ${
            isStopping 
              ? "bg-orange-200 dark:bg-orange-600"
              : "bg-gray-200 dark:bg-gray-600"
          }`}></div>
          <div className={`h-2 rounded-full w-5/6 animate-pulse ${
            isStopping 
              ? "bg-orange-200 dark:bg-orange-600"
              : "bg-gray-200 dark:bg-gray-600"
          }`}></div>
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
  isStopping = false,
  isUserControlInProgress = false,
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
  const [isModelDialogOpen, setIsModelDialogOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  
  // Function to open MCP settings modal
  const onMCPSettingsOpen = () => setIsSettingsOpen(true);

  return (
    <Card className="w-full lg:w-3/5 xl:w-2/3 md:w-3/5 flex flex-col h-full shadow-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
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
            {/* Modern Model & Region Selector */}
            <Dialog open={isModelDialogOpen} onOpenChange={setIsModelDialogOpen}>
              <DialogTrigger asChild>
                <Button 
                  variant="outline" 
                  className="h-8 px-3 text-xs bg-white/80 dark:bg-gray-800/80 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200 text-gray-700 dark:text-gray-300"
                >
                  <div className="flex items-center gap-2">
                    <Settings className="h-3.5 w-3.5" />
                    <span className="font-medium">Bedrock Settings</span>
                    <ChevronDown className="h-3 w-3" />
                  </div>
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                    Bedrock Settings
                  </DialogTitle>
                </DialogHeader>
                <div className="grid gap-6 py-4">
                  {/* Model Selection */}
                  <div className="space-y-3">
                    <label className="text-sm font-medium flex items-center gap-2">
                      <Cpu className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                      AI Model
                    </label>
                    <div className="grid gap-2">
                      {models.map((model) => (
                        <Button
                          key={model.id}
                          variant={selectedModel === model.id ? "default" : "outline"}
                          className={`justify-start h-auto p-3 ${
                            selectedModel === model.id 
                              ? "bg-blue-600 hover:bg-blue-700 text-white" 
                              : "hover:bg-blue-50 dark:hover:bg-blue-950/50"
                          }`}
                          onClick={() => setSelectedModel(model.id)}
                        >
                          <div className="text-left">
                            <div className="font-medium">{model.name}</div>
                            <div className="text-xs opacity-70 mt-1">
                              {model.id === 'anthropic.claude-3-5-sonnet-20241022-v2:0' && 'Most capable model for complex reasoning'}
                              {model.id === 'anthropic.claude-3-5-haiku-20241022-v1:0' && 'Fast and efficient for simple tasks'}
                              {model.id === 'us.anthropic.claude-sonnet-4-20250514-v1:0' && 'Latest model with enhanced capabilities'}
                            </div>
                          </div>
                        </Button>
                      ))}
                    </div>
                  </div>

                  {/* Region Selection */}
                  <div className="space-y-3">
                    <label className="text-sm font-medium flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-green-600 dark:text-green-400" />
                      AWS Region
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {regions.map((region) => (
                        <Button
                          key={region.id}
                          variant={selectedRegion === region.id ? "default" : "outline"}
                          className={`justify-start ${
                            selectedRegion === region.id 
                              ? "bg-green-600 hover:bg-green-700 text-white" 
                              : "hover:bg-green-50 dark:hover:bg-green-950/50"
                          }`}
                          onClick={() => setSelectedRegion(region.id)}
                        >
                          <MapPin className="h-3.5 w-3.5 mr-2" />
                          {region.name}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button onClick={() => setIsModelDialogOpen(false)}>
                    Done
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            
            <Button
              variant="outline"
              size="sm"
              onClick={onMCPSettingsOpen}
              title="Configure Tool Settings"
              className="h-8 text-xs flex gap-1 items-center bg-white/80 dark:bg-gray-800/80 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200 text-gray-700 dark:text-gray-300">
              <Code className="h-3.5 w-3.5" />
              <span className="font-medium">Tool Settings</span>
            </Button>
            
            {/* Theme button moved from footer to header */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="h-8 text-xs flex gap-1 items-center bg-white/80 dark:bg-gray-800/80 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200 text-gray-700 dark:text-gray-300"
                >
                  <div className="relative flex items-center justify-center w-3.5 h-3.5">
                    <Sun className="h-3.5 w-3.5 absolute rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                    <Moon className="h-3.5 w-3.5 absolute rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                  </div>
                  <span className="font-medium">Theme</span>
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
              className="h-8 text-xs flex gap-1 items-center bg-white/80 dark:bg-gray-800/80 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200 text-gray-700 dark:text-gray-300"
              title="Reset Chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="font-medium">Clear Chat</span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto p-5 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full max-w-lg mx-auto">
            <div className="mb-8">
              <Avatar className="w-12 h-12 mx-auto mb-4">
                <AvatarImage src="/bedrock-logo.png" alt="Web Browser Assistant Avatar" />
              </Avatar>
              <h2 className="text-xl font-semibold mb-2 text-gray-900 dark:text-gray-50 text-center">Web Browser Assistant</h2>
              <p className="text-gray-600 dark:text-gray-400 text-center text-sm">Navigate the web and interact with websites</p>
            </div>
            
            <div className="grid grid-cols-1 gap-3 w-full">
              <div className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="w-8 h-8 flex items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/30">
                  <Globe className="text-blue-600 dark:text-blue-400 w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 text-sm">Web Navigation</h3>
                  <p className="text-gray-600 dark:text-gray-400 text-xs">Visit websites and navigate pages</p>
                </div>
              </div>
              
              <div className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="w-8 h-8 flex items-center justify-center rounded-lg bg-green-50 dark:bg-green-900/30">
                  <Search className="text-green-600 dark:text-green-400 w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 text-sm">Web Research</h3>
                  <p className="text-gray-600 dark:text-gray-400 text-xs">Find information and extract data</p>
                </div>
              </div>
              
              <div className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="w-8 h-8 flex items-center justify-center rounded-lg bg-purple-50 dark:bg-purple-900/30">
                  <Code className="text-purple-600 dark:text-purple-400 w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 text-sm">Web Automation</h3>
                  <p className="text-gray-600 dark:text-gray-400 text-xs">Fill forms and automate tasks</p>
                </div>
              </div>
            </div>
            
            <div className="mt-6 text-xs text-gray-500 dark:text-gray-500 text-center">
              Ask me to visit a website or help with web tasks
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
                <ThinkingIndicator isStopping={isStopping} />
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
                  disabled={isLoading || isUserControlInProgress}
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-8 w-8 text-gray-500"
                >
                  <Paperclip className="h-5 w-5" />
                </Button>
                <Textarea
                  value={input}
                  onChange={onInputChange}
                  onKeyDown={onKeyDown}
                  placeholder={isUserControlInProgress ? "User Control in progress..." : "Ask me to visit websites or help with web tasks..."}
                  disabled={isLoading || isUserControlInProgress}
                  className="min-h-[48px] h-[48px] resize-none pl-12 py-3 flex items-center rounded-lg border-gray-300 dark:border-gray-700 focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors duration-200"
                  rows={1}
                />
              </div>
              <Button 
                type="submit" 
                disabled={isLoading || isThinking || isUserControlInProgress || (!input.trim() && !currentUpload)} 
                className="h-[48px] bg-primary hover:bg-primary/90 text-white px-4 rounded-lg shadow-sm hover:shadow-md transition-all duration-200"
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