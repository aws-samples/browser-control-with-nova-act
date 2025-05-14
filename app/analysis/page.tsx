"use client";
import React, { useState } from "react";
import Chat from '@/components/Chat';
import ThoughtProcess from '@/components/ThoughtProcess';
import { useChat } from "@/hooks/useChat";
import { models, regions } from '@/constants';
import TopNavBar from "@/components/TopNavBar";

export default function AIChat() {
  const [selectedRegion, setSelectedRegion] = useState("us-west-2");
  const [selectedModel, setSelectedModel] = useState(
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
  );
  const {
    messages,
    input,
    isLoading,
    isThinking,
    currentUpload,
    queryDetails,
    sessionId, 
    actions,
    fileInputRef
  } = useChat(selectedModel, selectedRegion);
  
  const navFeatures = {
    showDomainSelector: false, 
    showViewModeSelector: false, 
    showPromptCaching: false
  };

  return (
    <div className="flex flex-col h-screen">
      <TopNavBar
        features={navFeatures}
        onReset={actions.handleReset}
      />
      
      <div className="bg-gradient-to-b from-gray-50/80 via-white to-blue-50/30 dark:from-gray-900 dark:via-gray-900/95 dark:to-blue-950/10">
        <div className="flex-1 flex p-4 pt-0 gap-4 h-[calc(100vh-4rem)] justify-between">
        <Chat
          messages={messages}
          input={input}
          isLoading={isLoading}
          currentUpload={currentUpload}
          selectedModel={selectedModel}
          selectedRegion={selectedRegion}
          models={models}
          regions={regions}
          isThinking={isThinking}
          fileInputRef={fileInputRef}
          onInputChange={actions.handleInputChange}
          onKeyDown={actions.handleKeyDown}
          onSubmit={actions.handleSubmit}
          onFileSelect={actions.handleFileSelect}
          setSelectedModel={setSelectedModel}
          setSelectedRegion={setSelectedRegion}
          setCurrentUpload={actions.setCurrentUpload}
          onReset={actions.handleReset}
        />
  
        <ThoughtProcess 
          queryDetails={queryDetails}
          currentQueryIndex={0}
          userInput={input}
          sessionId={sessionId} 
        />
        </div>
      </div>
    </div>
  );
}
