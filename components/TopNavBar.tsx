"use client";
import Link from 'next/link';
import React, { useState, useEffect } from "react";
import Image from "next/image";
import { useTheme } from "next-themes";

interface TopNavBarProps {
  features?: {
    showDomainSelector?: boolean;
    showViewModeSelector?: boolean;
    showPromptCaching?: boolean;
  };
  onReset?: () => void; 
}

const TopNavBar: React.FC<TopNavBarProps> = ({ features = {}, onReset }) => {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <>
      <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="font-bold text-xl flex gap-2 items-center">
          <Image
            src={theme === "dark" ? "/amazon-dark.png" : "/amazon.webp"}
            alt="Company Wordmark"
            width={50}
            height={30}
            className="dark:brightness-[1.15]"
          />
        </div>
        {/* ANTHROPIC logo removed as requested */}
      </div>
    </>
  );
};

export default TopNavBar;