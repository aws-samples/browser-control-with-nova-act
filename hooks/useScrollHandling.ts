import { useRef, useEffect, useState } from 'react';
import type { Message } from '@/types/chat';

interface UseScrollHandlingProps {
  messages: Message[];
  isLoading: boolean;
}

export const useScrollHandling = ({ messages, isLoading }: UseScrollHandlingProps) => {
  const [currentQueryIndex, setCurrentQueryIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!messagesEndRef.current) return;

    const scrollToBottom = () => {
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "end",
        });
      });
    };

    const timeoutId = setTimeout(scrollToBottom, 100);
    return () => clearTimeout(timeoutId);
  }, [messages, isLoading]);

  useEffect(() => {
    if (!messagesEndRef.current) return;

    const observer = new ResizeObserver(() => {
      messagesEndRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    });
    
    observer.observe(messagesEndRef.current);
    return () => observer.disconnect();
  }, []);

  return {
    currentQueryIndex,
    messagesEndRef,
  };
};
