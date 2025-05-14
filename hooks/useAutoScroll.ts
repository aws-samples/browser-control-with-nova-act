// hooks/useAutoScroll.ts
import { useRef, useEffect } from 'react';

export const useAutoScroll = <T extends any[]>(dependencies: T) => {
  const endRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    const scrollToBottom = () => {
      if (!endRef.current) return;

      // Use requestAnimationFrame for smoother scrolling
      requestAnimationFrame(() => {
        endRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "end",
        });
      });
    };

    // Delay to ensure DOM has updated
    const timeoutId = setTimeout(scrollToBottom, 100);
    return () => clearTimeout(timeoutId);
  }, [...dependencies]);

  // Watch for size changes and adjust scroll
  useEffect(() => {
    if (!endRef.current) return;

    const observer = new ResizeObserver(() => {
      endRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    });
    
    observer.observe(endRef.current);
    return () => observer.disconnect();
  }, []);

  return endRef;
};
